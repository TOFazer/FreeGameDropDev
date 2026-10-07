"""Surveillance : dire « quelque chose va mal », là où les logs disent seulement
« quelque chose s'est passé ».

Le module garde en mémoire l'état des composants — bot, Discord, base de données,
sources d'offres, tâches de fond — puis :

- construit un rapport lisible (`/sante`, endpoint `/api/health`) ;
- décide quand alerter, sans jamais spammer : une source est déclarée 🔴
  **indisponible** quand elle n'a plus réussi depuis `SOURCE_DOWN_AFTER_MINUTES`
  avec au moins un échec, une alerte identique n'est pas répétée avant
  `MONITOR_ALERT_COOLDOWN_MINUTES`, et le retour à la normale envoie un message
  de rétablissement ;
- compte les erreurs récentes pour repérer un pic (`MONITOR_ERROR_ALERT_THRESHOLD`
  sur `MONITOR_ERROR_WINDOW_MINUTES`).

Rien n'est inventé : chaque état provient d'un appel réellement observé (succès,
échec, délai d'attente, ping de la base), et le rapport indique toujours *quand*
la dernière mesure a eu lieu.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

import config
import database
from utils.logging_setup import log_event
from utils.metrics import format_last_check

log = logging.getLogger(__name__)

MAX_ERRORS_KEPT = 1000


class Status(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


STATUS_EMOJI = {
    Status.OK: "🟢",
    Status.DEGRADED: "🟠",
    Status.DOWN: "🔴",
    Status.UNKNOWN: "⚪",
}

STATUS_LABELS = {
    Status.OK: "OK",
    Status.DEGRADED: "dégradée",
    Status.DOWN: "indisponible",
    Status.UNKNOWN: "inconnu",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


@dataclass
class SourceHealth:
    """Ce qu'on sait d'une source d'offres, uniquement d'après des appels réels."""

    name: str
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    last_latency_ms: int | None = None
    last_offers: int | None = None
    consecutive_failures: int = 0
    total_success: int = 0
    total_failure: int = 0
    total_timeout: int = 0


@dataclass
class TaskHealth:
    """Une tâche de fond (veille des offres, surveillance) et sa dernière exécution."""

    name: str
    interval_seconds: float | None = None
    last_run_at: datetime | None = None
    last_error: str | None = None
    runs: int = 0
    failures: int = 0


@dataclass
class Alert:
    """Une alerte prête à être envoyée : clé stable, gravité, texte humain."""

    key: str
    level: str  # "critical", "warning" ou "recovery"
    text: str


@dataclass
class HealthRegistry:
    """État courant du bot, alimenté par les composants réellement exécutés."""

    started_at: datetime = field(default_factory=_now)
    _sources: dict[str, SourceHealth] = field(default_factory=dict)
    _tasks: dict[str, TaskHealth] = field(default_factory=dict)
    _errors: deque = field(default_factory=lambda: deque(maxlen=MAX_ERRORS_KEPT))
    _db_ok: bool | None = None
    _db_latency_ms: int | None = None
    _db_checked_at: datetime | None = None

    # ----- sources -----

    def source(self, name: str) -> SourceHealth:
        return self._sources.setdefault(name, SourceHealth(name=str(name)))

    def record_source_success(
        self,
        name: str,
        *,
        latency_ms: int | None = None,
        offers: int | None = None,
        now: datetime | None = None,
    ) -> SourceHealth:
        state = self.source(name)
        state.last_success_at = now or _now()
        state.last_latency_ms = latency_ms
        if offers is not None:
            state.last_offers = offers
        state.consecutive_failures = 0
        state.total_success += 1
        return state

    def record_source_failure(
        self,
        name: str,
        *,
        error: str | None = None,
        timeout: bool = False,
        now: datetime | None = None,
    ) -> SourceHealth:
        state = self.source(name)
        state.last_failure_at = now or _now()
        state.last_error = (error or "échec inconnu")[:200]
        state.consecutive_failures += 1
        state.total_failure += 1
        if timeout:
            state.total_timeout += 1
        return state

    def source_status(self, name: str, *, now: datetime | None = None) -> Status:
        state = self._sources.get(str(name))
        if state is None:
            return Status.UNKNOWN
        if state.last_success_at is None and state.last_failure_at is None:
            return Status.UNKNOWN
        if state.consecutive_failures == 0:
            return Status.OK
        moment = _as_utc(now or _now())
        if state.last_success_at is None:
            # Jamais de succès depuis le démarrage : la source est considérée
            # indisponible dès que le délai est écoulé.
            elapsed = (moment - _as_utc(self.started_at)).total_seconds()
        else:
            elapsed = (moment - _as_utc(state.last_success_at)).total_seconds()
        if elapsed >= config.SOURCE_DOWN_AFTER_MINUTES * 60:
            return Status.DOWN
        return Status.DEGRADED

    # ----- tâches -----

    def register_task(self, name: str, *, interval_seconds: float | None = None) -> TaskHealth:
        state = self._tasks.setdefault(str(name), TaskHealth(name=str(name)))
        if interval_seconds is not None:
            state.interval_seconds = float(interval_seconds)
        return state

    def record_task_run(
        self,
        name: str,
        *,
        interval_seconds: float | None = None,
        error: str | None = None,
        now: datetime | None = None,
    ) -> TaskHealth:
        state = self.register_task(name, interval_seconds=interval_seconds)
        state.last_run_at = now or _now()
        state.runs += 1
        if error:
            state.last_error = str(error)[:200]
            state.failures += 1
        else:
            state.last_error = None
        return state

    def task_lag_seconds(self, name: str, *, now: datetime | None = None) -> float | None:
        """Temps écoulé depuis la dernière exécution (ou depuis le démarrage)."""
        state = self._tasks.get(str(name))
        if state is None:
            return None
        moment = _as_utc(now or _now())
        reference = _as_utc(state.last_run_at) if state.last_run_at else _as_utc(self.started_at)
        return max(0.0, (moment - reference).total_seconds())

    def task_status(self, name: str, *, now: datetime | None = None) -> Status:
        state = self._tasks.get(str(name))
        if state is None or state.interval_seconds is None:
            return Status.UNKNOWN
        lag = self.task_lag_seconds(name, now=now) or 0.0
        allowed = state.interval_seconds + max(
            config.MONITOR_TASK_GRACE_MINUTES * 60, state.interval_seconds * 0.25
        )
        if lag > allowed:
            return Status.DOWN if lag > 2 * allowed else Status.DEGRADED
        return Status.OK

    # ----- erreurs -----

    def record_error(self, *, now: datetime | None = None) -> None:
        self._errors.append(now or _now())

    def error_count(self, window_minutes: float, *, now: datetime | None = None) -> int:
        moment = _as_utc(now or _now())
        threshold = moment - timedelta(minutes=window_minutes)
        while self._errors and _as_utc(self._errors[0]) <= threshold:
            self._errors.popleft()
        return len(self._errors)

    # ----- base de données -----

    def record_database(
        self, ok: bool, *, latency_ms: int | None = None, now: datetime | None = None
    ) -> None:
        self._db_ok = bool(ok)
        self._db_latency_ms = latency_ms
        self._db_checked_at = now or _now()

    def database_status(self) -> Status:
        if self._db_ok is None:
            return Status.UNKNOWN
        return Status.OK if self._db_ok else Status.DOWN

    def reset(self) -> None:
        self._sources.clear()
        self._tasks.clear()
        self._errors.clear()
        self._db_ok = None
        self._db_latency_ms = None
        self._db_checked_at = None
        self.started_at = _now()


HEALTH = HealthRegistry()


# ---------- Mesures ----------


async def probe_database(*, now: datetime | None = None) -> bool:
    """Ping réel de la base : cœur du contrôle « la base répond-elle ? »."""
    moment = now or _now()
    start = time.perf_counter()
    try:
        ok = await database.ping()
    except Exception as error:  # base verrouillée, fichier illisible, disque plein…
        ok = False
        log_event(
            "database.failure",
            level=logging.ERROR,
            error=f"{type(error).__name__}: {error}",
        )
    latency_ms = round((time.perf_counter() - start) * 1000)
    HEALTH.record_database(ok, latency_ms=latency_ms, now=moment)
    if not ok:
        HEALTH.record_error(now=moment)
    return ok


def discord_status(bot) -> tuple[Status, str]:
    """État de la connexion Discord, déduit de l'objet `bot` uniquement."""
    if bot is None:
        return Status.UNKNOWN, "inconnu"
    if callable(getattr(bot, "is_closed", None)) and bot.is_closed():
        return Status.DOWN, "déconnecté"
    if callable(getattr(bot, "is_ready", None)) and not bot.is_ready():
        return Status.DEGRADED, "connexion en cours"
    latency = getattr(bot, "latency", None)
    if latency is None:
        return Status.OK, "connecté"
    try:
        latency_ms = round(float(latency) * 1000)
    except (TypeError, ValueError):
        return Status.DEGRADED, "latence illisible"
    if not math.isfinite(latency_ms):
        return Status.DEGRADED, "latence inconnue"
    if latency_ms > config.MONITOR_LATENCY_WARN_MS:
        return Status.DEGRADED, f"latence élevée ({latency_ms} ms)"
    return Status.OK, f"connecté (latence {latency_ms} ms)"


# ---------- Anti-spam des alertes ----------


@dataclass
class AlertBook:
    """Mémorise les alertes envoyées pour ne pas répéter la même toutes les minutes.

    Le retour à la normale n'est signalé que si une alerte était active : une
    source qui oscille ne produit donc pas de bruit.
    """

    cooldown_minutes: float = field(
        default_factory=lambda: config.MONITOR_ALERT_COOLDOWN_MINUTES
    )
    _sent_at: dict[str, datetime] = field(default_factory=dict)
    _active: set[str] = field(default_factory=set)

    @property
    def cooldown_seconds(self) -> float:
        return max(0.0, float(self.cooldown_minutes) * 60)

    def due(self, key: str, *, now: datetime | None = None) -> bool:
        last = self._sent_at.get(key)
        if last is None:
            return True
        return (_as_utc(now or _now()) - _as_utc(last)).total_seconds() >= self.cooldown_seconds

    def mark_sent(self, key: str, *, now: datetime | None = None) -> None:
        self._sent_at[key] = now or _now()
        self._active.add(key)

    def recovered(self, key: str) -> bool:
        """True si cette clé avait une alerte active (donc un rétablissement à annoncer)."""
        if key in self._active:
            self._active.discard(key)
            return True
        return False

    def active_keys(self) -> set[str]:
        return set(self._active)

    def reset(self) -> None:
        self._sent_at.clear()
        self._active.clear()


# ---------- Décision d'alerte ----------


def evaluate(
    book: AlertBook,
    *,
    discord: tuple[Status, str] | None = None,
    sources=None,
    now: datetime | None = None,
) -> list[Alert]:
    """Compare les mesures aux seuils et retourne les alertes (et rétablissements) dus."""
    moment = _as_utc(now or _now())
    alerts: list[Alert] = []

    names = set(sources if sources is not None else config.OFFER_SOURCES)
    names.update(HEALTH._sources)

    for name in sorted(str(item) for item in names):
        key = f"source:{name}"
        status = HEALTH.source_status(name, now=moment)
        state = HEALTH._sources.get(name)
        if status is Status.DOWN:
            if book.due(key, now=moment):
                details = [
                    f"aucun succès depuis {config.SOURCE_DOWN_AFTER_MINUTES:.0f} min"
                    f" (dernier succès : {format_last_check(state.last_success_at, moment)})"
                    if state and state.last_success_at
                    else "aucun succès depuis le démarrage"
                ]
                if state and state.consecutive_failures:
                    details.append(f"{state.consecutive_failures} échec(s) consécutif(s)")
                if state and state.last_error:
                    details.append(f"dernière erreur : {state.last_error}")
                alerts.append(
                    Alert(
                        key,
                        "critical",
                        f"🚨 Source « {name} » indisponible — {' ; '.join(details)}. "
                        "Les autres sources continuent d'alimenter FreeGameDrop.",
                    )
                )
                book.mark_sent(key, now=moment)
        elif status is Status.OK and book.recovered(key):
            alerts.append(
                Alert(
                    key,
                    "recovery",
                    f"🟢 Source « {name} » rétablie"
                    + (f" ({state.last_latency_ms} ms)" if state and state.last_latency_ms else "")
                    + ".",
                )
            )

    database_status = HEALTH.database_status()
    if database_status is Status.DOWN:
        if book.due("database", now=moment):
            alerts.append(
                Alert(
                    "database",
                    "critical",
                    "🚨 La base de données ne répond plus : les annonces et les préférences "
                    "ne peuvent plus être lues. Vérifie le disque et `DB_PATH`.",
                )
            )
            book.mark_sent("database", now=moment)
    elif database_status is Status.OK and book.recovered("database"):
        alerts.append(Alert("database", "recovery", "🟢 Base de données rétablie."))

    if discord is not None:
        status, label = discord
        if status in (Status.DOWN, Status.DEGRADED):
            if book.due("discord", now=moment):
                alerts.append(
                    Alert(
                        "discord",
                        "critical" if status is Status.DOWN else "warning",
                        f"🚨 Connexion Discord {STATUS_LABELS[status]} ({label}). "
                        "Les vérifications continuent mais les annonces ne partiront pas.",
                    )
                )
                book.mark_sent("discord", now=moment)
        elif status is Status.OK and book.recovered("discord"):
            alerts.append(Alert("discord", "recovery", "🟢 Connexion Discord rétablie."))

    errors = HEALTH.error_count(config.MONITOR_ERROR_WINDOW_MINUTES, now=moment)
    if errors >= config.MONITOR_ERROR_ALERT_THRESHOLD:
        if book.due("errors", now=moment):
            alerts.append(
                Alert(
                    "errors",
                    "critical",
                    f"🚨 {errors} erreurs en {config.MONITOR_ERROR_WINDOW_MINUTES:.0f} min "
                    f"(seuil : {config.MONITOR_ERROR_ALERT_THRESHOLD}). Vérifie le journal "
                    "(`grep event=`).",
                )
            )
            book.mark_sent("errors", now=moment)
    elif book.recovered("errors"):
        alerts.append(Alert("errors", "recovery", "🟢 Le nombre d'erreurs est revenu à la normale."))

    for name in sorted(HEALTH._tasks):
        state = HEALTH._tasks[name]
        if state.interval_seconds is None:
            continue
        key = f"task:{name}"
        status = HEALTH.task_status(name, now=moment)
        if status in (Status.DOWN, Status.DEGRADED):
            if book.due(key, now=moment):
                alerts.append(
                    Alert(
                        key,
                        "critical" if status is Status.DOWN else "warning",
                        f"🚨 La tâche « {name} » ne s'exécute plus : dernier passage "
                        f"{format_last_check(state.last_run_at, moment)}, attendu toutes les "
                        f"{_format_seconds(state.interval_seconds)}.",
                    )
                )
                book.mark_sent(key, now=moment)
        elif status is Status.OK and book.recovered(key):
            alerts.append(Alert(key, "recovery", f"🟢 La tâche « {name} » est repartie."))

    return alerts


def _format_seconds(seconds: float) -> str:
    seconds = float(seconds or 0)
    if seconds >= 3600:
        hours = seconds / 3600
        return f"{hours:.0f} h"
    if seconds >= 60:
        return f"{seconds / 60:.0f} min"
    return f"{seconds:.0f} s"


async def run_check(bot=None, *, book: AlertBook | None = None, send=None, now=None) -> list[Alert]:
    """Un cycle de surveillance complet : mesure, journalise, alerte, bat le cœur.

    `send` est appelé pour chaque alerte due (fonction asynchrone) ; sans lui, le
    cycle se contente de journaliser — pratique en test et quand Discord est en panne.
    """
    moment = _as_utc(now or _now())
    ledger = book if book is not None else AlertBook()
    await probe_database(now=moment)
    alerts = evaluate(
        ledger,
        discord=discord_status(bot) if bot is not None else None,
        now=moment,
    )
    for alert in alerts:
        log_event(
            "monitor.alert",
            level=logging.INFO if alert.level == "recovery" else logging.WARNING,
            alert=alert.key,
            severity=alert.level,
            message=alert.text,
        )
        if send is None:
            continue
        try:
            await send(alert)
        except Exception:
            HEALTH.record_error(now=moment)
            log.exception("Alerte %s impossible à envoyer", alert.key)

    try:
        await database.set_bot_state("monitor_heartbeat_at", moment.isoformat())
    except Exception:
        log.warning("Impossible d'enregistrer le battement de cœur du monitoring")
    return alerts


# ---------- Rapport ----------


async def last_check_datetime() -> datetime | None:
    try:
        raw = await database.get_bot_state("last_check_at")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return _as_utc(datetime.fromisoformat(raw))
    except ValueError:
        return None


async def collect(bot=None, *, now: datetime | None = None) -> dict:
    """Instantané complet, sérialisable — utilisé par `/sante` et `/api/health`."""
    moment = _as_utc(now or _now())
    await probe_database(now=moment)
    discord_state = discord_status(bot)
    database_state = HEALTH.database_status()

    sources = [
        {
            "name": state.name,
            "status": HEALTH.source_status(state.name, now=moment).value,
            "last_success_at": state.last_success_at,
            "last_failure_at": state.last_failure_at,
            "last_latency_ms": state.last_latency_ms,
            "last_offers": state.last_offers,
            "consecutive_failures": state.consecutive_failures,
            "total_success": state.total_success,
            "total_failure": state.total_failure,
            "total_timeout": state.total_timeout,
            "last_error": state.last_error,
        }
        for state in sorted(HEALTH._sources.values(), key=lambda item: item.name)
    ]
    tasks = [
        {
            "name": state.name,
            "status": HEALTH.task_status(state.name, now=moment).value,
            "interval_seconds": state.interval_seconds,
            "last_run_at": state.last_run_at,
            "last_error": state.last_error,
            "runs": state.runs,
            "failures": state.failures,
        }
        for state in sorted(HEALTH._tasks.values(), key=lambda item: item.name)
    ]

    statuses = [discord_state[0], database_state]
    statuses += [HEALTH.source_status(item["name"], now=moment) for item in sources]
    statuses += [HEALTH.task_status(item["name"], now=moment) for item in tasks]
    if any(item is Status.DOWN for item in statuses):
        overall = Status.DOWN
    elif any(item in (Status.DEGRADED, Status.UNKNOWN) for item in statuses):
        overall = Status.DEGRADED
    else:
        overall = Status.OK

    return {
        "status": overall.value,
        "generated_at": moment,
        "components": {
            "bot": Status.OK.value if bot is not None else Status.UNKNOWN.value,
            "discord": discord_state[0].value,
            "database": database_state.value,
        },
        "labels": {
            "discord": discord_state[1],
            "database_latency_ms": HEALTH._db_latency_ms,
        },
        "sources": sources,
        "tasks": tasks,
        "errors_window_minutes": config.MONITOR_ERROR_WINDOW_MINUTES,
        "errors_recent": HEALTH.error_count(config.MONITOR_ERROR_WINDOW_MINUTES, now=moment),
        "uptime_seconds": int((moment - _as_utc(HEALTH.started_at)).total_seconds()),
        "last_check_at": await last_check_datetime(),
    }


def build_report(snapshot: dict, *, now: datetime | None = None) -> str:
    """Rend le rapport texte de `/sante` (et l'en-tête des alertes)."""
    moment = _as_utc(now or _now())
    components = snapshot.get("components") or {}
    labels = snapshot.get("labels") or {}

    lines = ["FreeGameDrop", "─" * 20]
    bot_status_value = Status.OK if components.get("bot") == "ok" else Status.UNKNOWN
    lines.append(
        f"{STATUS_EMOJI[bot_status_value]} Bot              "
        f"{'en ligne' if bot_status_value is Status.OK else 'inconnu (rapport hors du bot)'}"
    )
    discord_status_value = Status(components.get("discord", Status.UNKNOWN))
    lines.append(
        f"{STATUS_EMOJI[discord_status_value]} Discord          {labels.get('discord', 'inconnu')}"
    )
    database_status_value = Status(components.get("database", Status.UNKNOWN))
    latency = labels.get("database_latency_ms")
    database_text = "saine" if database_status_value is Status.OK else STATUS_LABELS[database_status_value]
    if database_status_value is Status.OK and latency is not None:
        database_text += f" ({latency} ms)"
    lines.append(f"{STATUS_EMOJI[database_status_value]} Base de données  {database_text}")

    sources = snapshot.get("sources") or []
    lines.append("")
    lines.append("Sources")
    if not sources:
        lines.append("⚪ aucune source interrogée depuis le démarrage")
    for source in sources:
        status = Status(source.get("status", Status.UNKNOWN))
        detail = [STATUS_LABELS[status]]
        detail.append(f"dernier succès : {format_last_check(source.get('last_success_at'), moment)}")
        if source.get("last_offers") is not None:
            detail.append(f"{source['last_offers']} offre(s)")
        if source.get("last_latency_ms"):
            detail.append(f"{source['last_latency_ms']} ms")
        if source.get("consecutive_failures"):
            detail.append(f"{source['consecutive_failures']} échec(s) d'affilée")
        lines.append(f"{STATUS_EMOJI[status]} {source.get('name')} — " + " · ".join(detail))

    tasks = snapshot.get("tasks") or []
    if tasks:
        lines.append("")
        lines.append("Tâches")
        for task in tasks:
            status = Status(task.get("status", Status.UNKNOWN))
            interval = task.get("interval_seconds")
            detail = f"dernier passage : {format_last_check(task.get('last_run_at'), moment)}"
            if interval:
                detail += f" (toutes les {_format_seconds(interval)})"
            if task.get("last_error"):
                detail += f" · dernière erreur : {task['last_error']}"
            lines.append(f"{STATUS_EMOJI[status]} {task.get('name')} — {detail}")

    lines.append("")
    lines.append(
        f"Dernière vérification : {format_last_check(snapshot.get('last_check_at'), moment)}"
    )
    errors = snapshot.get("errors_recent", 0)
    window = snapshot.get("errors_window_minutes", 0)
    lines.append(f"Erreurs ({window:.0f} dernières minutes) : {errors}")
    return "\n".join(lines)


def to_jsonable(value):
    """Rend un instantané sérialisable en JSON (dates ISO, énumérations en texte)."""
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


async def status_report(bot=None, *, now: datetime | None = None) -> str:
    """Rapport prêt à publier (utilisé par `/sante`)."""
    snapshot = await collect(bot, now=now)
    return build_report(snapshot, now=now)

"""Limites de débit : anti-spam raisonnable, et respect des limites Discord.

Trois niveaux, exactement comme prévu au cahier des charges :

- **par utilisateur** pour les commandes de lecture et la navigation
  (`/free`, `/recherche`, boutons…) : un membre normal ne les remarque jamais,
  un membre qui martèle est simplement ralenti ;
- **par serveur** pour les actions administratives (`/setup-auto`, `/reset-all`,
  `/test-jeux`…) : les admins d'un même serveur partagent le même quota ;
- **sortant** (envois Discord) : un espacement minimal entre deux messages d'un
  même salon ou à un même membre, et une seule reprise quand Discord répond
  `429 Too Many Requests` — pour ne jamais forcer les limites imposées par Discord.

Les valeurs par défaut sont volontairement généreuses : elles n'existent que pour
protéger les sources d'offres et l'API Discord, pas pour gêner les utilisateurs.
Elles se règlent dans `.env` (voir `config.py` et le README).
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass

import discord
from discord import app_commands

import config
from utils.logging_setup import log_event

log = logging.getLogger(__name__)

SCOPE_USER = "utilisateur"
SCOPE_GUILD = "serveur"

# Une limite par clé ne doit pas garder d'historique indéfiniment.
MAX_TRACKED_KEYS = 5000
SWEEP_SECONDS = 300.0

# Attente maximale après un « 429 » de Discord (au-delà, on laisse Discord
# re-tenter lui-même au prochain envoi : inutile de bloquer un cycle entier).
MAX_429_WAIT_SECONDS = 30.0


@dataclass(frozen=True)
class Limit:
    """Une limite : `max_hits` appels autorisés par `window_seconds`."""

    name: str
    max_hits: int
    window_seconds: float
    scope: str
    label: str

    def __post_init__(self):
        if self.max_hits < 1:
            raise ValueError("max_hits doit valoir au moins 1")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds doit être strictement positif")


@dataclass(frozen=True)
class Decision:
    """Résultat d'une vérification : autorisé, ou refusé avec un délai d'attente."""

    allowed: bool
    retry_after: float
    remaining: int


def default_limits() -> dict[str, Limit]:
    """Table des limites actives, construite depuis `config` (donc depuis `.env`)."""
    return {
        # Plafond global, par membre, toutes commandes de lecture confondues.
        "user_commands": Limit(
            "user_commands",
            max(1, config.RATE_LIMIT_USER_PER_MINUTE),
            60.0,
            SCOPE_USER,
            "tes commandes",
        ),
        # Commandes de lecture : chacune a sa propre limite, en plus du plafond global.
        "free": Limit(
            "free",
            max(1, config.RATE_LIMIT_FREE_PER_MINUTE),
            60.0,
            SCOPE_USER,
            "/free",
        ),
        "recherche": Limit("recherche", 8, 60.0, SCOPE_USER, "/recherche"),
        "historique": Limit("historique", 8, 60.0, SCOPE_USER, "/historique"),
        "favoris": Limit("favoris", 10, 60.0, SCOPE_USER, "/favoris"),
        "preferences": Limit("preferences", 6, 60.0, SCOPE_USER, "/preferences"),
        "alertes": Limit("alertes", 6, 60.0, SCOPE_USER, "/alertes"),
        "stats": Limit("stats", 8, 60.0, SCOPE_USER, "/stats"),
        "sante": Limit("sante", 6, 60.0, SCOPE_USER, "/sante"),
        "info": Limit("info", 10, 60.0, SCOPE_USER, "/info"),
        "ping": Limit("ping", 12, 60.0, SCOPE_USER, "/ping"),
        "mes_donnees": Limit("mes_donnees", 3, 600.0, SCOPE_USER, "/mes-donnees"),
        # Boutons : la navigation doit rester fluide, seul l'abus est freiné.
        "interactions": Limit("interactions", 60, 60.0, SCOPE_USER, "la navigation dans les offres"),
        # Ajouter/retirer un rôle touche l'API Discord : on espace davantage.
        "roles": Limit("roles", 6, 60.0, SCOPE_USER, "le choix des rôles"),
        # Actions administratives : quota partagé par serveur.
        "admin": Limit(
            "admin",
            max(1, config.RATE_LIMIT_ADMIN_PER_MINUTE),
            60.0,
            SCOPE_GUILD,
            "les actions de configuration",
        ),
        "admin_heavy": Limit(
            "admin_heavy",
            max(1, config.RATE_LIMIT_ADMIN_HEAVY_PER_10_MINUTES),
            600.0,
            SCOPE_GUILD,
            "les tests et réinitialisations",
        ),
    }


LIMITS: dict[str, Limit] = default_limits()


class SlidingWindowLimiter:
    """Fenêtre glissante en mémoire : chaque clé garde l'heure de ses derniers appels."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque] = {}
        self._expiry: dict[str, float] = {}
        self._last_sweep = 0.0

    def hit(self, key: str, limit: Limit, *, now: float | None = None) -> Decision:
        moment = self._clock() if now is None else float(now)
        history = self._hits.setdefault(key, deque())
        self._expiry[key] = moment + limit.window_seconds
        threshold = moment - limit.window_seconds
        while history and history[0] <= threshold:
            history.popleft()

        if len(history) >= limit.max_hits:
            retry_after = max(0.0, history[0] + limit.window_seconds - moment)
            return Decision(False, retry_after, 0)

        history.append(moment)
        self._sweep(moment)
        return Decision(True, 0.0, max(0, limit.max_hits - len(history)))

    def _sweep(self, moment: float) -> None:
        """Oublie les clés dont toutes les mesures sont expirées (pas de fuite mémoire)."""
        if moment - self._last_sweep < SWEEP_SECONDS and len(self._hits) <= MAX_TRACKED_KEYS:
            return
        self._last_sweep = moment
        for key in [
            key_item
            for key_item, expiry in self._expiry.items()
            if expiry <= moment or not self._hits.get(key_item)
        ]:
            self._hits.pop(key, None)
            self._expiry.pop(key, None)

    def reset(self) -> None:
        self._hits.clear()
        self._expiry.clear()


RATE_LIMITER = SlidingWindowLimiter()


class RateLimited(app_commands.CheckFailure):
    """Refus temporaire et lisible : la limite raisonnable vient d'être atteinte."""

    def __init__(self, limit: Limit, retry_after: float):
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(format_limit_message(limit, retry_after))


def format_delay(seconds: float) -> str:
    seconds = max(1, math.ceil(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes = (seconds + 59) // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = (minutes + 59) // 60
    return f"{hours} h"


def format_limit_message(limit: Limit, retry_after: float) -> str:
    """Message court, cordial, qui explique la limite au lieu de la subir."""
    return (
        f"⏳ Limite atteinte : {limit.label}, {limit.max_hits} fois par "
        f"{format_delay(limit.window_seconds)} maximum. Réessaie dans {format_delay(retry_after)}."
    )


def _identifier(limit: Limit, interaction) -> int:
    if limit.scope == SCOPE_GUILD:
        return getattr(interaction, "guild_id", None) or interaction.user.id
    return interaction.user.id


def consume(limit: Limit, identifier, *, now: float | None = None) -> Decision:
    """Consomme une unité du quota `limit` pour cet utilisateur ou ce serveur."""
    return RATE_LIMITER.hit(f"{limit.name}:{identifier}", limit, now=now)


def consume_command(name: str, interaction, *, now: float | None = None) -> Decision:
    """Vérifie la limite propre à la commande, puis le plafond global du membre.

    Les actions administratives sont limitées par serveur : le plafond par membre
    ne les concerne pas.
    """
    return consume_command_with_limit(name, interaction, now=now)[0]


def consume_command_with_limit(
    name: str, interaction, *, now: float | None = None
) -> tuple[Decision, Limit]:
    """Comme `consume_command`, en indiquant aussi *quelle* limite a refusé."""
    limit = LIMITS[name]
    decision = consume(limit, _identifier(limit, interaction), now=now)
    if not decision.allowed or limit.scope == SCOPE_GUILD:
        return decision, limit
    global_decision = consume(LIMITS["user_commands"], interaction.user.id, now=now)
    if global_decision.allowed:
        return decision, limit
    return global_decision, LIMITS["user_commands"]


def limited(name: str):
    """Décore une commande applicative : `@limited("recherche")`."""

    def decorator(func):
        async def predicate(interaction: discord.Interaction) -> bool:
            decision, limit = consume_command_with_limit(name, interaction)
            if decision.allowed:
                return True
            log_event(
                "command.rate_limited",
                level=logging.INFO,
                command=name,
                limit=limit.name,
                scope=limit.scope,
                user_id=getattr(interaction.user, "id", None),
                retry_after_s=round(decision.retry_after, 1),
            )
            raise RateLimited(limit, decision.retry_after)

        return app_commands.check(predicate)(func)

    return decorator


# ---------- Envois sortants (limites imposées par Discord) ----------


class OutboundThrottle:
    """Espace les envois vers Discord pour ne jamais partir en rafale.

    Discord limite la cadence par salon et par route : on réserve un créneau par
    clé (« channel:123 », « dm:456 »), ce qui suffit pour un bot qui publie
    plusieurs annonces à la suite.
    """

    def __init__(self, interval_seconds: float, clock=time.monotonic):
        self.interval_seconds = max(0.0, float(interval_seconds))
        self._clock = clock
        self._next_slot: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def retry_after(self, key: str, *, now: float | None = None) -> float:
        moment = self._clock() if now is None else float(now)
        return max(0.0, self._next_slot.get(key, 0.0) - moment)

    async def wait(self, key: str) -> None:
        if self.interval_seconds <= 0:
            return
        async with self._lock:
            moment = self._clock()
            ready_at = max(moment, self._next_slot.get(key, 0.0))
            self._next_slot[key] = ready_at + self.interval_seconds
            delay = ready_at - moment
        if delay > 0:
            await asyncio.sleep(delay)

    def reset(self) -> None:
        self._next_slot.clear()


DISCORD_THROTTLE = OutboundThrottle(config.DISCORD_SEND_INTERVAL_SECONDS)


def retry_after_of(error: discord.HTTPException) -> float | None:
    """Délai demandé par Discord dans un « 429 », ou None si ce n'est pas un 429."""
    if getattr(error, "status", None) != 429:
        return None
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None) or {}
    try:
        return max(0.0, float(headers.get("Retry-After", 1.0)))
    except (TypeError, ValueError):
        return 1.0


async def spaced_send(send, *, key: str, throttle: OutboundThrottle | None = None, **kwargs):
    """Envoie un message Discord en respectant la cadence.

    Une seule reprise est tentée, uniquement après un « 429 » : Discord indique
    alors lui-même combien de temps attendre. Les autres erreurs remontent à
    l'appelant, qui sait quoi en faire (salon supprimé, DM fermés…).
    """
    active = throttle if throttle is not None else DISCORD_THROTTLE
    await active.wait(key)
    try:
        return await send(**kwargs)
    except discord.HTTPException as error:
        delay = retry_after_of(error)
        if delay is None:
            raise
        log_event(
            "discord.rate_limited",
            level=logging.WARNING,
            key=key,
            retry_after_s=round(delay, 2),
        )
        if delay > MAX_429_WAIT_SECONDS:
            raise
        await asyncio.sleep(delay)
        await active.wait(key)
        return await send(**kwargs)

"""Agrège plusieurs sources d'offres (GamerPower, Epic Games Store, ...).

Chaque source renvoie son propre format brut ; ce module se contente d'étiqueter
chaque offre (source, type normalisé, genres), de vérifier qu'elle mérite d'être
annoncée, puis de fusionner le tout sans dupliquer une même offre.

Trois garanties :

1. **Indépendance des sources** — une source en panne, trop lente ou illisible est
   ignorée pour ce tour, les autres continuent (et son état est enregistré pour le
   monitoring) ;
2. **Pas de faux positif** — une offre n'est transmise que si sa source a été
   réellement interrogée et qu'elle semble encore active : jamais d'offre expirée,
   jamais d'offre que la source elle-même signale comme non active
   (`free_verified`), jamais d'entrée sans identifiant ni titre ;
3. **Respect des sources** — un cache court (`OFFER_CACHE_SECONDS`) et un appel
   unique partagé (single-flight) évitent qu'une rafale de `/free` martèle les API.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import config
from services import epic_games, gamerpower
from utils import monitoring
from utils.logging_setup import log_event
from utils.offers import classify_offer_type, normalize_genres, parse_end_datetime

log = logging.getLogger(__name__)


def _call_gamerpower():
    return gamerpower.fetch_giveaways()


def _call_epic():
    return epic_games.fetch_giveaways()


# Les valeurs sont de petites fonctions (plutôt que les méthodes directement) pour que
# monkeypatcher `gamerpower.fetch_giveaways` ou `epic_games.fetch_giveaways` dans les tests
# soit pris en compte, même après l'import de ce module.
SOURCES = {
    "gamerpower": _call_gamerpower,
    "epic": _call_epic,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(game: dict, source: str) -> dict:
    game = dict(game)
    game.setdefault("source", source)
    game["offer_type"] = classify_offer_type(game.get("type") or game.get("offer_type"))
    game["genres"] = normalize_genres(game.get("genres"))
    return game


def reject_reason(game: dict, *, now: datetime | None = None) -> str | None:
    """Pourquoi ne pas annoncer cette offre — ou None si elle est présentable.

    La règle est volontairement prudente : on ne refuse jamais une offre parce
    qu'une information manque (une source peut ne pas fournir de date de fin), mais
    on refuse toute offre que la source elle-même contredit (déjà terminée, statut
    non actif) ou qu'on ne saurait pas présenter (sans titre, lien invalide).
    """
    if not str(game.get("id") or "").strip():
        return "identifiant manquant"
    if not str(game.get("title") or "").strip():
        return "titre manquant"
    if game.get("free_verified") is False:
        return "la source indique que l'offre n'est plus active"
    end = parse_end_datetime(game.get("end_date"))
    if end is not None and end <= (now or _now()):
        return "offre déjà terminée"
    for field_name in ("open_giveaway_url", "gamerpower_url"):
        url = str(game.get(field_name) or "").strip()
        if url and not url.lower().startswith(("http://", "https://")):
            return "lien de récupération invalide"
    return None


async def _fetch_source(name: str, fetch, moment: datetime) -> tuple[list[dict], bool]:
    """Interroge une source ; retourne ses offres normalisées et si elle a répondu."""
    log_event("source.request", source=name)
    started = time.perf_counter()
    try:
        games = await asyncio.wait_for(fetch(), timeout=config.OFFER_SOURCE_TIMEOUT)
    except asyncio.TimeoutError:
        monitoring.HEALTH.record_source_failure(
            name, error="délai d'attente dépassé", timeout=True, now=moment
        )
        monitoring.HEALTH.record_error(now=moment)
        log_event(
            "source.timeout",
            level=logging.WARNING,
            source=name,
            timeout_s=config.OFFER_SOURCE_TIMEOUT,
        )
        return [], False
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        monitoring.HEALTH.record_source_failure(name, error=message, now=moment)
        monitoring.HEALTH.record_error(now=moment)
        log_event("source.failure", level=logging.WARNING, source=name, error=message)
        return [], False

    latency_ms = round((time.perf_counter() - started) * 1000)
    if not isinstance(games, list):
        monitoring.HEALTH.record_source_failure(name, error="format de réponse inattendu", now=moment)
        monitoring.HEALTH.record_error(now=moment)
        log_event(
            "source.failure",
            level=logging.WARNING,
            source=name,
            error="format de réponse inattendu (liste attendue)",
        )
        return [], False

    monitoring.HEALTH.record_source_success(name, latency_ms=latency_ms, offers=len(games), now=moment)
    log_event("source.success", source=name, latency_ms=latency_ms, offers=len(games))

    normalized = []
    for index, game in enumerate(games):
        if not isinstance(game, dict) or game.get("id") is None or not str(game.get("id")).strip():
            log_event(
                "offer.skipped",
                level=logging.DEBUG,
                source=name,
                index=index,
                reason="entrée invalide ou sans identifiant",
            )
            continue
        try:
            normalized.append(_normalize(game, name))
        except Exception:
            monitoring.HEALTH.record_error(now=moment)
            log.exception("Offre %s invalide dans la source « %s » ; elle est ignorée", index, name)
    return normalized, True


def _verify(offers: list[dict], moment: datetime) -> list[dict]:
    """Écarte les offres non annonçables et journalise ce qui a été écarté."""
    verified = []
    rejected = 0
    for game in offers:
        reason = reject_reason(game, now=moment)
        if reason is None:
            verified.append(game)
            continue
        rejected += 1
        log_event(
            "offer.rejected",
            level=logging.DEBUG,
            offer_id=game.get("id"),
            source=game.get("source"),
            reason=reason,
        )
    if rejected:
        log_event("offers.filtered", rejected=rejected, kept=len(verified))
    return verified


def _merge(results: list[list[dict]]) -> list[dict]:
    seen_ids = set()
    merged: list[dict] = []
    for games in results:
        for game in games:
            item_id = str(game.get("id") or "").strip()
            if not item_id or item_id in seen_ids:
                if item_id:
                    log_event("offer.duplicate", offer_id=item_id, source=game.get("source"))
                continue
            seen_ids.add(item_id)
            merged.append(game)
    return merged


async def _fetch_all(sources, moment: datetime) -> tuple[list[dict], bool]:
    configured = config.OFFER_SOURCES if sources is None else sources
    enabled = [name for name in configured if name in SOURCES]
    if not enabled:
        return [], False

    results = await asyncio.gather(
        *(_fetch_source(name, SOURCES[name], moment) for name in enabled)
    )
    merged = _verify(_merge([games for games, _ in results]), moment)
    for game in merged:
        log_event(
            "offer.detected",
            offer_id=game.get("id"),
            source=game.get("source"),
            offer_type=game.get("offer_type"),
            end_date=game.get("end_date") or None,
        )
    # Une source a réellement répondu si elle a renvoyé une liste, même vide.
    succeeded = any(answered for _, answered in results)
    return merged, succeeded


# ---------- Cache court (respect des sources) ----------

_cache: dict | None = None
_inflight: asyncio.Future | None = None


def clear_cache() -> None:
    """Oublie le cache des offres (utile en test et après une vérification forcée)."""
    global _cache
    _cache = None


def cached_offers(now: datetime | None = None) -> list[dict] | None:
    """Contenu du cache s'il est encore frais, sinon None (lecture seule)."""
    if not _cache:
        return None
    age = ((now or _now()) - _cache["fetched_at"]).total_seconds()
    if 0 <= age < config.OFFER_CACHE_SECONDS:
        return _cache["offers"]
    return None


async def _shared_fetch(moment: datetime) -> list[dict]:
    """Appel partagé entre plusieurs commandes simultanées (évite les rafales)."""
    global _cache
    offers, succeeded = await _fetch_all(None, moment)
    # Un échec total n'est pas mis en cache : dès qu'une source répond de nouveau,
    # les utilisateurs voient les offres sans attendre l'expiration du cache.
    if succeeded:
        _cache = {"fetched_at": moment, "offers": [dict(offer) for offer in offers]}
    return offers


async def _fetch_cached(moment: datetime) -> list[dict]:
    global _inflight
    cached = cached_offers(moment)
    if cached is not None:
        log_event(
            "offers.cache_hit",
            age_s=round((moment - _cache["fetched_at"]).total_seconds(), 1),
            offers=len(cached),
        )
        return [dict(offer) for offer in cached]

    if _inflight is not None and not _inflight.done():
        log_event("offers.cache_join")
        return await asyncio.shield(_inflight)

    task = asyncio.ensure_future(_shared_fetch(moment))
    _inflight = task
    try:
        return await asyncio.shield(task)
    finally:
        if _inflight is task:
            _inflight = None


async def fetch_offers(
    sources=None, *, use_cache: bool = False, now: datetime | None = None
) -> list[dict]:
    """Interroge les sources et fusionne les résultats.

    - `use_cache=True` : réutilise le dernier résultat récent et partage l'appel en
      cours entre plusieurs commandes (utilisé par `/free`) ;
    - une source en échec ou trop lente ne bloque pas les autres : elle est
      simplement ignorée pour ce tour-ci.
    """
    moment = now or _now()
    if use_cache and sources is None:
        return await _fetch_cached(moment)
    offers, _ = await _fetch_all(sources, moment)
    return offers

"""Agrège plusieurs sources d'offres (GamerPower, Epic Games Store, ...).

Chaque source renvoie son propre format brut ; ce module se contente
d'étiqueter chaque offre (source, type normalisé, genres) et de fusionner
le tout sans dupliquer une même offre.
"""

from __future__ import annotations

import asyncio
import logging

import config
from services import epic_games, gamerpower
from utils.offers import classify_offer_type, normalize_genres

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


def _normalize(game: dict, source: str) -> dict:
    game = dict(game)
    game.setdefault("source", source)
    game["offer_type"] = classify_offer_type(game.get("type") or game.get("offer_type"))
    game["genres"] = normalize_genres(game.get("genres"))
    return game


async def _fetch_source(name: str, fetch) -> list[dict]:
    try:
        games = await asyncio.wait_for(fetch(), timeout=config.OFFER_SOURCE_TIMEOUT)
    except asyncio.TimeoutError:
        log.warning("Source d'offres « %s » trop lente, ignorée pour ce tour", name)
        return []
    except Exception:
        log.exception("Source d'offres « %s » en erreur, ignorée pour ce tour", name)
        return []
    if not isinstance(games, list):
        log.warning("Format inattendu de la source « %s » : une liste était attendue", name)
        return []

    normalized = []
    for index, game in enumerate(games):
        if not isinstance(game, dict) or game.get("id") is None or not str(game.get("id")).strip():
            log.debug("Offre %s ignorée depuis « %s » : entrée invalide ou sans identifiant", index, name)
            continue
        try:
            normalized.append(_normalize(game, name))
        except Exception:
            log.exception("Offre %s invalide dans la source « %s » ; elle est ignorée", index, name)
    return normalized

async def fetch_offers(sources=None) -> list[dict]:
    """Interroge les sources activées en parallèle et fusionne les résultats.

    Une source en échec ou trop lente ne bloque pas les autres : elle est
    simplement ignorée pour ce tour-ci.
    """
    configured = config.OFFER_SOURCES if sources is None else sources
    enabled = [name for name in configured if name in SOURCES]
    if not enabled:
        return []

    results = await asyncio.gather(
        *(_fetch_source(name, SOURCES[name]) for name in enabled)
    )

    seen_ids = set()
    merged: list[dict] = []
    for games in results:
        for game in games:
            item_id = str(game.get("id") or "").strip()
            if not item_id or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            merged.append(game)
    return merged

"""Accès à l'API GamerPower (uniquement l'appel réseau, aucune logique Discord)."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import GAMERPOWER_API_URL, GAMERPOWER_TIMEOUT

log = logging.getLogger(__name__)

PARAMS = {"type": "game", "sort-by": "date"}

# Statuts renvoyés par GamerPower pour une offre réellement en cours. Le endpoint des
# giveaways peut aussi contenir d'anciennes offres : le statut sert de garde-fou
# contre les faux positifs (« ce jeu est gratuit » alors qu'il ne l'est plus).
ACTIVE_STATUSES = {"active", "free", "available"}


def mark_free_verified(games: list) -> list:
    """Annote chaque offre : `free_verified` = True / False / None (statut absent).

    None signifie « la source ne se prononce pas » : l'offre n'est pas rejetée pour
    autant, seule une contradiction explicite de la source bloque l'annonce.
    """
    for game in games:
        if not isinstance(game, dict):
            continue
        status = str(game.get("status") or "").strip().casefold()
        game["free_verified"] = status in ACTIVE_STATUSES if status else None
    return games


async def fetch_giveaways() -> list:
    """Retourne la liste des jeux gratuits, ou [] si l'API a un souci."""
    try:
        timeout = aiohttp.ClientTimeout(total=GAMERPOWER_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(GAMERPOWER_API_URL, params=PARAMS) as resp:
                if resp.status != 200:
                    log.warning("GamerPower a répondu avec le code %s", resp.status)
                    return []
                data = await resp.json()
                if not isinstance(data, list):
                    log.warning("Format de réponse inattendu de GamerPower : une liste était attendue")
                    return []
                return mark_free_verified(data)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Impossible de joindre GamerPower : %s", e)
        return []
    except ValueError as e:  # réponse qui n'est pas du JSON
        log.warning("Réponse illisible de GamerPower : %s", e)
        return []

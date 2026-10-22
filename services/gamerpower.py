"""Accès à l'API GamerPower (uniquement l'appel réseau, aucune logique Discord).

Deux catégories sont interrogées séparément :

- `type=game` — les jeux complets (source « gamerpower ») ;
- `type=loot` — les DLC, extensions et contenus en jeu (source « gamerpower_loot »).

La documentation officielle ne propose que `game`, `loot` et `beta` : il n'existe
pas de filtre « dlc » à part. C'est donc `loot` qui alimente le salon des DLC, et
le type réel de chaque entrée (`DLC`, `Loot`, …) est conservé pour la classification.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import GAMERPOWER_API_URL, GAMERPOWER_TIMEOUT

log = logging.getLogger(__name__)

# Jeux complets.
PARAMS = {"type": "game", "sort-by": "date"}
# DLC, extensions et contenus en jeu : même endpoint, autre catégorie.
DLC_PARAMS = {"type": "loot", "sort-by": "date"}

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


async def _fetch(params: dict, *, raise_on_error: bool = False) -> list:
    """Interroge l'API avec les paramètres donnés, ou [] si l'API a un souci.

    Quand `raise_on_error=True` (utilisé par `services.offer_engine`), les erreurs
    HTTP, réseau ou de format remontent à l'agrégateur pour que `/sante` et le
    monitoring reflètent fidèlement l'état réel de la source.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=GAMERPOWER_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(GAMERPOWER_API_URL, params=params) as resp:
                if resp.status != 200:
                    log.warning(
                        "GamerPower a répondu avec le code %s (type=%s)",
                        resp.status,
                        params.get("type"),
                    )
                    if raise_on_error:
                        raise RuntimeError(f"HTTP {resp.status}")
                    return []
                data = await resp.json()
                if not isinstance(data, list):
                    log.warning("Format de réponse inattendu de GamerPower : une liste était attendue")
                    if raise_on_error:
                        raise ValueError("format de réponse inattendu (liste attendue)")
                    return []
                return mark_free_verified(data)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Impossible de joindre GamerPower : %s", e)
        if raise_on_error:
            raise
        return []
    except ValueError as e:  # réponse qui n'est pas du JSON (ou format invalide ci-dessus)
        if not raise_on_error or "liste attendue" not in str(e):
            log.warning("Réponse illisible de GamerPower : %s", e)
        if raise_on_error:
            raise
        return []


async def fetch_giveaways(*, raise_on_error: bool = False) -> list:
    """Retourne la liste des jeux complets gratuits, ou [] si l'API a un souci."""
    return await _fetch(PARAMS, raise_on_error=raise_on_error)


async def fetch_dlc_giveaways(*, raise_on_error: bool = False) -> list:
    """Retourne les DLC, extensions et contenus en jeu gratuits, ou [] en cas de panne.

    Le type brut de chaque entrée est conservé : `services.offer_engine` le classe
    en « dlc » ou « contenu », et le salon des DLC reçoit les deux.
    """
    return await _fetch(DLC_PARAMS, raise_on_error=raise_on_error)

"""Accès à l'API GamerPower (uniquement l'appel réseau, aucune logique Discord)."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import GAMERPOWER_API_URL, GAMERPOWER_TIMEOUT

log = logging.getLogger(__name__)

PARAMS = {"type": "game", "sort-by": "date"}


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
                return data if isinstance(data, list) else []
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Impossible de joindre GamerPower : %s", e)
        return []
    except ValueError as e:  # réponse qui n'est pas du JSON
        log.warning("Réponse illisible de GamerPower : %s", e)
        return []

import asyncio
import logging

import aiohttp

log = logging.getLogger(__name__)

API_URL = "https://www.gamerpower.com/api/giveaways"


async def fetch_giveaways():
    """Retourne la liste des jeux gratuits, ou [] si l'API a un souci."""
    params = {"type": "game", "sort-by": "date"}
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(API_URL, params=params) as resp:
                if resp.status != 200:
                    log.warning("GamerPower a répondu avec le code %s", resp.status)
                    return []
                data = await resp.json()
                return data if isinstance(data, list) else []
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Impossible de joindre GamerPower : %s", e)
        return []
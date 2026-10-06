"""Accès à l'API publique du Epic Games Store (jeux gratuits de la semaine)."""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from config import EPIC_API_URL, EPIC_COUNTRY, EPIC_LOCALE, EPIC_STORE_URL, EPIC_TIMEOUT

log = logging.getLogger(__name__)

SOURCE_KEY = "epic"


def _active_promotion(element: dict) -> dict | None:
    """Retourne l'offre promotionnelle en cours (prix à 0€), sinon None."""
    promotions = element.get("promotions") or {}
    for offer_group in promotions.get("promotionalOffers") or []:
        for offer in offer_group.get("promotionalOffers") or []:
            discount = (offer.get("discountSetting") or {}).get("discountPercentage")
            if discount == 0:
                return offer
    return None


def _product_slug(element: dict) -> str | None:
    mappings = element.get("offerMappings") or []
    if mappings and mappings[0].get("pageSlug"):
        return mappings[0]["pageSlug"]
    if element.get("productSlug"):
        return str(element["productSlug"]).split("/")[0]
    catalog_ns = element.get("catalogNs") or {}
    for mapping in catalog_ns.get("mappings") or []:
        if mapping.get("pageSlug"):
            return mapping["pageSlug"]
    return None


def _thumbnail(element: dict) -> str:
    for image in element.get("keyImages") or []:
        if image.get("type") in {"OfferImageWide", "DieselStoreFrontWide", "Thumbnail"}:
            return image.get("url", "")
    images = element.get("keyImages") or []
    return images[0].get("url", "") if images else ""


def _original_price_text(element: dict) -> str:
    price = (element.get("price") or {}).get("totalPrice") or {}
    fmt = price.get("fmtPrice") or {}
    return fmt.get("originalPrice") or ""


def _parse_element(element: dict) -> dict | None:
    offer = _active_promotion(element)
    if offer is None:
        return None

    slug = _product_slug(element)
    claim_url = f"{EPIC_STORE_URL}/{EPIC_LOCALE.split('-')[0]}/p/{slug}" if slug else EPIC_STORE_URL

    item_id = element.get("id") or slug or element.get("title")
    if not item_id:
        return None

    return {
        "id": f"{SOURCE_KEY}:{item_id}",
        "title": element.get("title") or "Jeu gratuit",
        "description": element.get("description") or "",
        "platforms": "Epic Games Store",
        "worth": _original_price_text(element),
        "end_date": str(offer.get("endDate") or "").replace("T", " ").replace("Z", ""),
        "open_giveaway_url": claim_url,
        "gamerpower_url": claim_url,
        "thumbnail": _thumbnail(element),
        "published_date": str(offer.get("startDate") or "").replace("T", " ").replace("Z", ""),
        "type": "game",
        "genres": [],
        "source": SOURCE_KEY,
    }


async def fetch_giveaways() -> list:
    """Retourne les jeux actuellement offerts gratuitement sur l'Epic Games Store."""
    params = {
        "locale": EPIC_LOCALE,
        "country": EPIC_COUNTRY,
        "allowCountries": EPIC_COUNTRY,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=EPIC_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(EPIC_API_URL, params=params) as resp:
                if resp.status != 200:
                    log.warning("Epic Games Store a répondu avec le code %s", resp.status)
                    return []
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Impossible de joindre Epic Games Store : %s", e)
        return []
    except ValueError as e:  # réponse qui n'est pas du JSON
        log.warning("Réponse illisible d'Epic Games Store : %s", e)
        return []

    try:
        elements = data["data"]["Catalog"]["searchStore"]["elements"]
    except (KeyError, TypeError):
        log.warning("Format de réponse inattendu d'Epic Games Store")
        return []

    games = []
    for element in elements or []:
        if not isinstance(element, dict):
            continue
        parsed = _parse_element(element)
        if parsed is not None:
            games.append(parsed)
    return games

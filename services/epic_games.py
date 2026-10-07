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
    promotions = element.get("promotions")
    if not isinstance(promotions, dict):
        return None
    groups = promotions.get("promotionalOffers")
    if not isinstance(groups, list):
        return None
    for offer_group in groups:
        if not isinstance(offer_group, dict):
            continue
        offers = offer_group.get("promotionalOffers")
        if not isinstance(offers, list):
            continue
        for offer in offers:
            if not isinstance(offer, dict):
                continue
            setting = offer.get("discountSetting")
            discount = setting.get("discountPercentage") if isinstance(setting, dict) else None
            if discount == 0:
                return offer
    return None


def _product_slug(element: dict) -> str | None:
    mappings = element.get("offerMappings")
    if isinstance(mappings, list):
        for mapping in mappings:
            if isinstance(mapping, dict) and mapping.get("pageSlug"):
                return str(mapping["pageSlug"])
    if element.get("productSlug"):
        return str(element["productSlug"]).split("/")[0]
    catalog_ns = element.get("catalogNs")
    if isinstance(catalog_ns, dict):
        mappings = catalog_ns.get("mappings")
        if isinstance(mappings, list):
            for mapping in mappings:
                if isinstance(mapping, dict) and mapping.get("pageSlug"):
                    return str(mapping["pageSlug"])
    return None


def _thumbnail(element: dict) -> str:
    images = element.get("keyImages")
    if not isinstance(images, list):
        return ""
    for image in images:
        if (
            isinstance(image, dict)
            and image.get("type") in {"OfferImageWide", "DieselStoreFrontWide", "Thumbnail"}
        ):
            return str(image.get("url") or "")
    for image in images:
        if isinstance(image, dict) and image.get("url"):
            return str(image["url"])
    return ""


def _original_price_text(element: dict) -> str:
    price = element.get("price")
    total = price.get("totalPrice") if isinstance(price, dict) else None
    fmt = total.get("fmtPrice") if isinstance(total, dict) else None
    original = fmt.get("originalPrice") if isinstance(fmt, dict) else None
    return str(original or "")


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
    if not isinstance(elements, list):
        log.warning("Format de réponse inattendu d'Epic Games Store : la liste des jeux est absente")
        return []

    games = []
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            log.debug("Élément %s de la réponse Epic ignoré : objet attendu", index)
            continue
        try:
            parsed = _parse_element(element)
        except (AttributeError, TypeError, ValueError):
            log.warning("Élément %s de la réponse Epic illisible ; il est ignoré", index, exc_info=True)
            continue
        if parsed is not None:
            games.append(parsed)
    return games

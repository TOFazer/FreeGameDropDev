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


def _clean_slug(value: object) -> str | None:
    if not value:
        return None
    slug = str(value).split("/")[0].strip()
    if not slug or slug == "[]":
        return None
    return slug


def _product_slug(element: dict) -> str | None:
    mappings = element.get("offerMappings")
    if isinstance(mappings, list):
        for mapping in mappings:
            if isinstance(mapping, dict):
                slug = _clean_slug(mapping.get("pageSlug"))
                if slug:
                    return slug
    slug = _clean_slug(element.get("productSlug"))
    if slug:
        return slug
    catalog_ns = element.get("catalogNs")
    if isinstance(catalog_ns, dict):
        mappings = catalog_ns.get("mappings")
        if isinstance(mappings, list):
            for mapping in mappings:
                if isinstance(mapping, dict):
                    slug = _clean_slug(mapping.get("pageSlug"))
                    if slug:
                        return slug
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


# Types de produits Epic qui ne sont pas des jeux complets. Tout le reste est
# présenté comme un jeu : cette source ne sert qu'aux promotions gratuites, et
# mieux vaut ne pas envoyer un jeu complet dans le salon des DLC par erreur.
_DLC_OFFER_TYPES = {"dlc", "add_on", "addon", "expansion", "expansion_pack", "pack"}


def _offer_type(element: dict) -> str:
    """Type normalisé d'une offre Epic à partir de son `offerType` explicite."""
    raw = str(element.get("offerType") or "").strip().casefold().replace("-", "_")
    return "dlc" if raw in _DLC_OFFER_TYPES else "game"


def _discount_price_is_zero(element: dict) -> bool | None:
    """Le prix actuel est-il nul ? None quand l'information n'est pas fournie.

    Garde-fou contre les faux positifs : une remise à 0 % doit correspondre à un
    prix réellement nul. Quand le champ est absent, on ne conclut rien (la source
    ne se prononce pas) et l'offre reste éligible.
    """
    price = element.get("price")
    total = price.get("totalPrice") if isinstance(price, dict) else None
    if not isinstance(total, dict) or "discountPrice" not in total:
        return None
    try:
        return int(total["discountPrice"]) == 0
    except (TypeError, ValueError):
        return None


def _parse_element(element: dict) -> dict | None:
    offer = _active_promotion(element)
    if offer is None:
        return None
    if _discount_price_is_zero(element) is False:
        log.debug("Offre Epic ignorée : remise à 0 % mais prix actuel non nul")
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
        "type": _offer_type(element),
        "genres": [],
        "source": SOURCE_KEY,
        # Promo vérifiée ici même : remise à 0 % et prix actuel nul (ou inconnu).
        "free_verified": True,
    }


async def fetch_giveaways(*, raise_on_error: bool = False) -> list:
    """Retourne les jeux actuellement offerts gratuitement sur l'Epic Games Store.

    Quand `raise_on_error=True` (utilisé par `services.offer_engine`), les erreurs
    HTTP, réseau ou de structure remontent à l'agrégateur pour que `/sante` et le
    monitoring signalent fidèlement une source bloquée ou en panne.
    """
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
                    if raise_on_error:
                        raise RuntimeError(f"HTTP {resp.status}")
                    return []
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning("Impossible de joindre Epic Games Store : %s", e)
        if raise_on_error:
            raise
        return []
    except ValueError as e:  # réponse qui n'est pas du JSON
        log.warning("Réponse illisible d'Epic Games Store : %s", e)
        if raise_on_error:
            raise
        return []

    try:
        elements = data["data"]["Catalog"]["searchStore"]["elements"]
    except (KeyError, TypeError) as e:
        log.warning("Format de réponse inattendu d'Epic Games Store")
        if raise_on_error:
            raise ValueError("format de réponse inattendu d'Epic Games Store") from e
        return []
    if not isinstance(elements, list):
        log.warning("Format de réponse inattendu d'Epic Games Store : la liste des jeux est absente")
        if raise_on_error:
            raise ValueError("liste des jeux absente dans la réponse d'Epic Games Store")
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

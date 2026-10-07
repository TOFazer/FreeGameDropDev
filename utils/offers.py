"""Filtres communs du catalogue et classification prudente des offres."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config
from utils import platforms


def parse_end_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def classify_offer_type(value: object) -> str:
    """Mappe uniquement les types reconnus; contenu de loot et DLC restent distincts."""
    raw = str(value or "game").strip().casefold().replace("_", "-")
    if raw in {"game", "games", "base-game", "full-game", "jeu", "jeux"}:
        return "game"
    if raw in {"dlc", "add-on", "addon", "expansion", "extension"}:
        return "dlc"
    if raw in {
        "loot",
        "content",
        "in-game",
        "ingame",
        "in-game-loot",
        "beta",
        "beta-key",
        "beta-keys",
    }:
        return "content"
    return "content"


def offer_matches_type(game: dict, selected_types) -> bool:
    """Les catégories sont en OU; « temporaire » est un filtre supplémentaire en ET."""
    selected = set(selected_types or [])
    if not selected:
        return False
    category_types = selected.intersection({"game", "dlc", "content"})
    category = str(game.get("offer_type") or "game")
    if category_types and category not in category_types:
        return False
    if "temporary" in selected and parse_end_datetime(game.get("end_date")) is None:
        return False
    return bool(category_types or "temporary" in selected)


def parse_worth_eur(value: object) -> float | None:
    """Lit un prix explicitement libellé en euros; les autres devises restent inconnues."""
    text = str(value or "").strip()
    match = re.search(
        r"(?:€|\bEUR\b)\s*([0-9][0-9\s.,]*)|([0-9][0-9\s.,]*)\s*(?:€|\bEUR\b)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    number = re.sub(r"\s+", "", match.group(1) or match.group(2))
    if "," in number and "." in number:
        decimal_separator = "," if number.rfind(",") > number.rfind(".") else "."
        thousands_separator = "." if decimal_separator == "," else ","
        number = number.replace(thousands_separator, "").replace(decimal_separator, ".")
    elif "," in number:
        decimals = len(number.rsplit(",", 1)[1])
        number = number.replace(",", ".") if decimals in {1, 2} else number.replace(",", "")
    elif number.count(".") > 1:
        parts = number.split(".")
        number = "".join(parts[:-1]) + "." + parts[-1]
    try:
        amount = float(number)
    except ValueError:
        return None
    return amount if amount >= 0 else None


def normalize_genres(values) -> list[str]:
    """Normalise uniquement des étiquettes de genre explicites et connues."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    aliases = {label.casefold(): key for key, label in config.GENRE_LABELS.items()}
    genres = set()
    for genre in values:
        value = str(genre).strip().casefold()
        if value in config.GENRE_KEYS:
            genres.add(value)
        elif value in aliases:
            genres.add(aliases[value])
    return [key for key in config.GENRE_KEYS if key in genres]


def offer_matches_genres(game: dict, selected_genres) -> bool:
    """N'accepte que des genres structurés fournis explicitement par une source."""
    selected = set(selected_genres or [])
    if not selected:
        return True
    return bool(set(normalize_genres(game.get("genres"))).intersection(selected))


def normalize_platforms(values) -> list[str]:
    """Ne garde que les clés de plateformes suivies par le bot (steam, epic, gog, ubisoft)."""
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    return [key for key in platforms.PLATFORM_KEYS if key in {str(v).strip().casefold() for v in values}]


def offer_matches_preferences(game: dict, preferences: dict) -> bool:
    """Applique les préférences personnelles de type, plateforme, valeur et genres vérifiés."""
    if not offer_matches_type(game, preferences.get("offer_types", ["game"])):
        return False
    selected_platforms = normalize_platforms(preferences.get("platforms"))
    if selected_platforms:
        if platforms.detect_platform(game) not in selected_platforms:
            return False
    minimum = preferences.get("min_worth_eur")
    if minimum is not None:
        worth = parse_worth_eur(game.get("worth"))
        if worth is None or worth < float(minimum):
            return False
    return offer_matches_genres(game, preferences.get("genres", []))


def is_mega_deal(game: dict, now: datetime | None = None) -> bool:
    """Une offre « exceptionnelle » est un jeu complet, temporaire et de grande valeur.

    Seuls des champs réellement fournis par les sources décident : la valeur doit être
    explicitement libellée en euros (aucune conversion inventée), l'offre doit avoir une
    date de fin encore future, et il doit s'agir d'un jeu complet (pas un DLC ni un loot).
    """
    if config.MEGA_DEAL_MIN_WORTH_EUR <= 0:
        return False
    if str(game.get("offer_type") or "game") != "game":
        return False
    worth = parse_worth_eur(game.get("worth"))
    if worth is None or worth < config.MEGA_DEAL_MIN_WORTH_EUR:
        return False
    end = parse_end_datetime(game.get("end_date"))
    if end is None:
        return False
    now = now or datetime.now(timezone.utc)
    return end > now


def filter_offers(
    games: list[dict],
    *,
    platform: str | None = None,
    offer_type: str | None = None,
    period: str | None = None,
    now: datetime | None = None,
    timezone_name: str | None = None,
) -> list[dict]:
    """Filtre plateforme, type et échéance pour `/free`."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    try:
        zone = ZoneInfo(timezone_name or config.DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")

    filtered = []
    for game in games:
        if platform and not platforms.matches(game, [platform]):
            continue
        if offer_type and not offer_matches_type(game, [offer_type]):
            continue
        end = parse_end_datetime(game.get("end_date"))
        if period == "ends_today":
            if end is None or end <= now or end.astimezone(zone).date() != now.astimezone(zone).date():
                continue
        elif period == "ending_soon":
            if end is None or not now < end <= now + timedelta(hours=config.LAST_DAY_HOURS):
                continue
        filtered.append(game)
    return filtered

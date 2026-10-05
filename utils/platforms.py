"""Reconnaissance des plateformes et habillage de leurs rôles."""

from __future__ import annotations

from collections.abc import Iterable

import discord

from config import DEFAULT_COLOUR, DEFAULT_EMOJI, PLATFORM_KEYS, PLATFORMS, Platform


def get(key: str) -> Platform | None:
    return PLATFORMS.get(key)


def display_name(key: str) -> str:
    platform = get(key)
    return platform.name if platform else key


def emoji(key: str | None) -> str:
    platform = get(key) if key else None
    return platform.emoji if platform else DEFAULT_EMOJI


def colour(key: str | None) -> int:
    platform = get(key) if key else None
    return platform.colour if platform else DEFAULT_COLOUR


def role_name(key: str) -> str:
    platform = get(key)
    return platform.role_name if platform else key


def role_colour(key: str) -> discord.Colour:
    return discord.Colour(colour(key))


def channel_name(key: str) -> str:
    platform = get(key)
    return platform.channel_name if platform else key


def matches(game: dict, keys: Iterable[str]) -> bool:
    """Le jeu sort-il sur au moins une des plateformes demandées ?"""
    text = (game.get("platforms") or "").lower()
    for key in keys:
        platform = get(key)
        if platform and any(keyword in text for keyword in platform.keywords):
            return True
    return False


def detect_platform(game: dict) -> str | None:
    """Première plateforme connue correspondant au jeu, sinon None."""
    for key in PLATFORM_KEYS:
        if matches(game, [key]):
            return key
    return None

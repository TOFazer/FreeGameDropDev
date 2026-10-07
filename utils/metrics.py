"""Indicateurs d'usage exposés aux développeurs (commande /dev-stats, tableau de bord)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from discord.ext import commands

import config
import database
from utils.offers import parse_end_datetime, parse_worth_eur


def guild_count(bot: commands.Bot) -> int:
    return len(bot.guilds)


def member_count(bot: commands.Bot) -> int:
    """Nombre total de membres visibles par le bot, tous serveurs confondus."""
    return sum(getattr(guild, "member_count", 0) or 0 for guild in bot.guilds)


async def build_dev_stats(bot: commands.Bot) -> dict:
    """Rassemble les métriques utiles au suivi du bot (sans aucune donnée personnelle)."""
    catalogue = await database.get_giveaway_stats()
    return {
        "guilds": guild_count(bot),
        "members": member_count(bot),
        "latency_ms": round(bot.latency * 1000) if bot.latency == bot.latency else None,  # évite NaN
        **catalogue,
    }


def format_dev_stats_text(stats: dict) -> str:
    """Rendu texte simple, utilisé par la commande /dev-stats et les logs."""
    lines = [
        f"Serveurs : {stats.get('guilds', 0):,}",
        f"Membres couverts : {stats.get('members', 0):,}",
        f"Offres suivies : {stats.get('total_offers', 0):,}",
        f"Offres (30 derniers jours) : {stats.get('offers_last_30_days', 0):,}",
        f"Favoris enregistrés : {stats.get('total_favorites', 0):,} "
        f"({stats.get('members_with_favorites', 0):,} membres)",
        f"Serveurs configurés : {stats.get('configured_guilds', 0):,}/{stats.get('known_guilds', 0):,}",
    ]
    by_source = stats.get("offers_by_source") or {}
    if by_source:
        detail = ", ".join(f"{source}: {count}" for source, count in sorted(by_source.items()))
        lines.append(f"Par source : {detail}")
    return "\n".join(lines)


async def build_public_stats(bot: commands.Bot) -> dict:
    """Statistiques publiques affichées par /stats — uniquement des valeurs mesurées.

    - « offres actives » : offres du catalogue dont la date de fin est inconnue (toujours
      distribuées par la source) ou postérieure à maintenant ;
    - « valeur connue » : somme des valeurs explicitement libellées en euros par les
      sources. Les autres devises ne sont ni converties ni estimées.
    """
    catalogue = await database.get_giveaway_stats()
    rows = await database.get_offer_rows_for_stats()
    now = datetime.now(timezone.utc)
    active = 0
    known_value_eur = 0.0
    for end_date, worth in rows:
        end = parse_end_datetime(end_date)
        if end is None or end > now:
            active += 1
        value = parse_worth_eur(worth)
        if value is not None:
            known_value_eur += value

    last_check_raw = await database.get_bot_state("last_check_at")
    last_check = None
    if last_check_raw:
        try:
            last_check = datetime.fromisoformat(last_check_raw)
        except ValueError:
            last_check = None

    return {
        "guilds": guild_count(bot),
        "total_offers": catalogue.get("total_offers", 0),
        "active_offers": active,
        "offers_last_30_days": catalogue.get("offers_last_30_days", 0),
        "known_value_eur": round(known_value_eur, 2),
        "platforms_watched": len(config.PLATFORMS),
        "sources": sorted(config.OFFER_SOURCES),
        "last_check_at": last_check,
    }


def format_last_check(last_check: datetime | None, now: datetime | None = None) -> str:
    """Texte lisible pour la dernière vérification (« il y a 3 min », heure locale)."""
    if last_check is None:
        return "pas encore vérifié"
    now = now or datetime.now(timezone.utc)
    delta = now - last_check
    if delta.total_seconds() < 0:
        delta = timedelta(0)
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "à l'instant"
    if minutes < 60:
        return f"il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    return f"il y a {hours // 24} j"


def format_public_stats_text(stats: dict) -> str:
    """Rendu texte des statistiques publiques (logs, /stats en texte brut)."""
    return "\n".join(
        [
            f"Serveurs : {stats.get('guilds', 0):,}",
            f"Offres détectées : {stats.get('total_offers', 0):,}",
            f"Offres actives : {stats.get('active_offers', 0):,}",
            f"Valeur connue : {stats.get('known_value_eur', 0):,.2f} €",
            f"Plateformes suivies : {stats.get('platforms_watched', 0)}",
        ]
    )

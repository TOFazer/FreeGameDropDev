"""Indicateurs d'usage exposés aux développeurs (commande /dev-stats, tableau de bord)."""

from __future__ import annotations

from discord.ext import commands

import database


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

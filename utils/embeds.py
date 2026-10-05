"""Construction des messages Discord (annonces de jeux, panneau des rôles)."""

from __future__ import annotations

from datetime import datetime, timezone

import discord

from utils import platforms


def format_end_date(raw: str) -> str:
    """'2026-10-05 23:59:00' -> compte à rebours + date complète (heure locale de chacun)."""
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        ts = int(dt.timestamp())
        return f"<t:{ts}:R>\n<t:{ts}:f>"
    except (ValueError, TypeError):
        return "Pas de date limite connue"


def format_price(worth) -> str:
    if not worth or str(worth).strip().upper() == "N/A":
        return "**GRATUIT**"
    return f"~~{worth}~~ ➜ **GRATUIT**"


def clean_description(text: str, limit: int = 220) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def build_game_message(game: dict):
    """(embed, view) d'annonce d'un jeu gratuit."""
    key = platforms.detect_platform(game)
    title = game.get("title", "Jeu gratuit").replace(" Giveaway", "")
    url = game.get("open_giveaway_url") or game.get("gamerpower_url")

    embed = discord.Embed(
        title=f"{platforms.emoji(key)} {title}",
        url=url,
        description=clean_description(game.get("description")),
        color=platforms.colour(key),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name="🎁 NOUVEAU JEU GRATUIT")
    embed.add_field(name="💰 Prix", value=format_price(game.get("worth")), inline=True)
    embed.add_field(name="⏳ Fin de l'offre", value=format_end_date(game.get("end_date")), inline=True)
    embed.add_field(name="🖥️ Plateformes", value=game.get("platforms") or "N/A", inline=False)
    if game.get("thumbnail"):
        embed.set_image(url=game["thumbnail"])
    embed.set_footer(text="Source : GamerPower")

    view = discord.ui.View()
    if url:
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="Récupérer le jeu",
                emoji="🎁",
                url=url,
            )
        )
    return embed, view


def build_roles_embed() -> discord.Embed:
    """Panneau affiché dans le salon de choix des rôles."""
    embed = discord.Embed(
        title="🎮 Choisis tes alertes jeux gratuits",
        description=(
            "Clique sur un bouton pour **recevoir** le rôle d'une plateforme "
            "et débloquer son salon. Reclique pour le **retirer**.\n\n"
            "Tu seras mentionné quand un jeu gratuit sort sur cette plateforme."
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Salon en lecture seule : seuls les boutons fonctionnent ici.")
    return embed

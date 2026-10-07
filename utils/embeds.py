"""Construction des messages Discord (annonces de jeux, panneau des rôles).

L'embed n'est pas une notification technique : c'est une mini publicité pour
FreeGameDrop, construite selon l'identité visuelle de `utils/design.py`
(documentée dans `DESIGN.md`). Hiérarchie de lecture (2–3 secondes) :

1️⃣ Quoi    → badge d'auteur : 🎁 JEU GRATUIT / 🔥 SE TERMINE BIENTÔT / …
2️⃣ Quel jeu → titre : le nom du jeu, rien d'autre
3️⃣ Pourquoi → 💰 Prix : ~~59,99 €~~ ➜ **GRATUIT**
4️⃣ Où      → 🎮 Plateforme : petit badge (emoji + nom)
5️⃣ Quand   → ⏰ Fin de l'offre : emoji d'urgence + horodatage relatif
6️⃣ Action  → [🎁 Récupérer le jeu] (principal) + [➕ Ajouter FreeGameDrop] (secondaire)

La marque reste FreeGameDrop partout : le filet de l'embed est toujours la couleur
principale (gris neutre pour une offre terminée) — jamais la couleur d'une plateforme.
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord

import config
from utils import design, offers, platforms

SOURCE_LABELS = {
    "gamerpower": "GamerPower",
    "epic": "Epic Games Store",
}


def format_end_date(raw: str) -> str:
    """'2026-10-05 23:59:00' -> compte à rebours + date complète (heure locale de chacun)."""
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        ts = int(dt.timestamp())
        return f"<t:{ts}:R>\n<t:{ts}:f>"
    except (ValueError, TypeError):
        return "Pas de date limite connue"


def format_price(worth) -> str:
    """Le regard doit comprendre immédiatement : « je paierais ce prix, c'est gratuit »."""
    if not worth or str(worth).strip().upper() == "N/A":
        return "**GRATUIT**"
    return f"~~{worth}~~ ➜ **GRATUIT**"


def clean_description(text: str, limit: int = 220) -> str:
    """Description courte et secondaire — jamais une fiche Wikipédia."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def source_label(game: dict) -> str:
    return SOURCE_LABELS.get(game.get("source"), "GamerPower")


def urgency_for(end_date: str | None, now: datetime | None = None) -> str:
    """Niveau d'urgence (design.URGENCY_EMOJI) à partir de la date de fin brute."""
    return design.urgency_level(offers.parse_end_datetime(end_date), now=now)


def format_time_remaining(end_date: str | None, now: datetime | None = None) -> str:
    """⏰ emoji d'urgence + horodatage relatif Discord + date complète."""
    level = urgency_for(end_date, now=now)
    if level == "unknown":
        return f"{design.URGENCY_EMOJI['unknown']} Pas de date limite connue"
    return f"{design.URGENCY_EMOJI[level]} {format_end_date(end_date)}"


def offer_variant(game: dict, now: datetime | None = None) -> str:
    """Variante d'embed déduite de l'échéance : new / ending_soon / ended.

    « extended » (offre prolongée) se force explicitement : rien dans les sources
    ne permet aujourd'hui de détecter une prolongation.
    """
    level = urgency_for(game.get("end_date"), now=now)
    if level == "ended":
        return "ended"
    if level in {"urgent", "critical"}:
        return "ending_soon"
    return "new"


def platform_badge(game: dict) -> str:
    """Petit badge plateforme (emoji + nom) ; texte brut si la plateforme est inconnue."""
    key = platforms.detect_platform(game)
    if key is None:
        return str(game.get("platforms") or "N/A")
    return f"{platforms.emoji(key)} {platforms.display_name(key)}"


def build_game_message(game: dict, invite_url: str | None = None, *, variant: str | None = None):
    """(embed, view) d'annonce d'un jeu gratuit.

    `variant` force une variante d'embed (« new », « ending_soon », « extended",
    « ended ») ; par défaut elle est déduite de la date de fin.

    `invite_url` ajoute un petit bouton secondaire « Ajouter FreeGameDrop » sous
    l'annonce : le bouton principal reste « Récupérer le jeu » — l'objectif premier
    est de fournir le jeu, le second de convertir le lecteur en utilisateur.
    """
    if variant is None:
        variant = offer_variant(game)
    if variant not in design.EMBED_VARIANTS:
        raise ValueError(f"Variante inconnue : {variant!r}")

    key = platforms.detect_platform(game)
    title = game.get("title", "Jeu gratuit").replace(" Giveaway", "")
    url = game.get("open_giveaway_url") or game.get("gamerpower_url")
    mega = offers.is_mega_deal(game)

    if variant != "new":
        author = design.EMBED_VARIANTS[variant]["author"]
    elif mega:
        author = design.MEGA_DEAL_AUTHOR
    else:
        author = design.EMBED_VARIANTS["new"]["author"]

    embed = discord.Embed(
        title=f"{platforms.emoji(key)} {title}",
        url=url,
        description=clean_description(game.get("description")),
        color=design.embed_colour(variant),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=author)
    embed.add_field(name="💰 Prix", value=format_price(game.get("worth")), inline=True)
    embed.add_field(name="🎮 Plateforme", value=platform_badge(game), inline=True)
    embed.add_field(name="⏰ Fin de l'offre", value=format_time_remaining(game.get("end_date")), inline=True)

    offer_type = game.get("offer_type")
    if offer_type in {"dlc", "content"}:
        embed.add_field(
            name="🏷️ Type", value=config.OFFER_TYPE_LABELS.get(offer_type, offer_type), inline=True
        )
    if mega:
        worth = offers.parse_worth_eur(game.get("worth"))
        embed.add_field(
            name="🔥 Offre exceptionnelle",
            value=(
                f"Jeu complet d'une valeur de **{worth:.2f} €**, offert pour une durée limitée."
                if worth is not None
                else "Jeu complet offert pour une durée limitée."
            ),
            inline=False,
        )

    # L'image est la partie visuelle forte : même emplacement, même ratio ressenti
    # (image pleine largeur), jamais déformée — Discord ne recadre pas.
    if game.get("thumbnail"):
        embed.set_image(url=game["thumbnail"])
    # Branding discret : jamais plus important que le jeu.
    embed.set_footer(text=f"{design.FOOTER} · Source : {source_label(game)}")

    # Boutons-liens : Discord ne colore pas les boutons URL (discord.py force le
    # style « link »), la hiérarchie passe par l'ordre, le libellé et l'emoji :
    # « Récupérer le jeu » en premier et en 🎁, « Ajouter FreeGameDrop » en retrait.
    view = discord.ui.View()
    if url:
        ended = variant == "ended"
        view.add_item(
            discord.ui.Button(
                label="Voir l'offre" if ended else "Récupérer le jeu",
                emoji="🔗" if ended else "🎁",
                url=url,
            )
        )
    if invite_url:
        view.add_item(
            discord.ui.Button(
                label="Ajouter FreeGameDrop",
                emoji="➕",
                url=invite_url,
            )
        )
    return embed, view


def build_roles_embed() -> discord.Embed:
    """Panneau affiché dans le salon de choix des rôles."""
    embed = discord.Embed(
        title="🎮 FreeGameDrop — choisis tes alertes jeux gratuits",
        description=(
            "Clique sur un bouton pour **recevoir** le rôle d'une plateforme "
            "et débloquer son salon. Reclique pour le **retirer**.\n\n"
            "Tu seras mentionné quand un jeu gratuit sort sur cette plateforme."
        ),
        color=design.embed_colour("new"),
    )
    embed.set_footer(text=f"{design.FOOTER} — salon en lecture seule : seuls les boutons fonctionnent ici.")
    return embed

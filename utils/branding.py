"""Identité publique du bot : lien d'invitation partagé par /info, /stats et les annonces.

Le lien est construit à partir de l'identifiant de l'application du bot : il fonctionne
pour n'importe quelle instance auto-hébergée, sans configuration supplémentaire.
"""

from __future__ import annotations

from urllib.parse import urlencode

import discord

# Permissions indispensables : créer les salons/rôles et publier les annonces.
# La lecture de l'historique et la modération des messages admin sont facultatives.
INVITE_PERMISSIONS = discord.Permissions(
    manage_channels=True,
    manage_roles=True,
    view_channel=True,
    send_messages=True,
    embed_links=True,
).value


def build_invite_url(client_id: int | str, guild_id: int | str | None = None) -> str:
    """Lien « Ajouter FreeGameDrop à Discord », éventuellement pré-ciblé sur un serveur."""
    params = {
        "client_id": str(client_id),
        "permissions": INVITE_PERMISSIONS,
        "scope": "bot applications.commands",
    }
    if guild_id:
        params["guild_id"] = str(guild_id)
    return f"https://discord.com/oauth2/authorize?{urlencode(params)}"

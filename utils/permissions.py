"""Permissions des salons créés par le bot.

Règle du bot : ses salons se **lisent** mais ne s'écrivent pas.

Deux subtilités Discord sont gérées ici :

1. Discord refuse qu'un bot autorise ou interdise une permission qu'il ne
   possède pas lui-même : on filtre donc chaque réglage avec `bot_can()`.
2. Les administrateurs passent outre toutes les permissions de salon : ils
   pourront toujours écrire, c'est le bot qui efface leurs messages
   (voir `Jeux.on_message`). `admin_note()` le rappelle à l'admin.
"""

from __future__ import annotations

from collections.abc import Iterable

import discord

from config import MAX_ACCESS_ROLES

# Tout ce qu'on retire dans un salon en lecture seule : écrire, réagir, ouvrir
# un fil, lancer un sondage, envoyer un vocal, utiliser une commande...
# bref, regarder et c'est tout.
READONLY_DENY = (
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
    "manage_threads",
    "add_reactions",
    "send_tts_messages",
    "attach_files",
    "embed_links",
    "mention_everyone",
    "manage_messages",
    "use_application_commands",
    "send_voice_messages",
    "create_polls",
    "send_polls",
)

# Ce dont le bot a besoin dans ses propres salons.
BOT_ALLOW = (
    "view_channel",
    "read_message_history",
    "send_messages",
    "embed_links",
    "attach_files",
    "manage_messages",  # facultatif : modération des messages dans le salon des rôles
)

# Permissions réellement requises pour créer la configuration et envoyer les annonces.
# Lire l'historique et gérer les messages restent des options de modération, pas un prérequis.
SETUP_REQUIRED = (
    ("manage_channels", "Gérer les salons"),
    ("manage_roles", "Gérer les rôles"),
    ("view_channel", "Voir les salons"),
    ("send_messages", "Envoyer des messages"),
    ("embed_links", "Intégrer des liens"),
)


def overwrite(**flags) -> discord.PermissionOverwrite:
    """PermissionOverwrite en ignorant les permissions absentes de cette version de discord.py."""
    known = discord.Permissions.VALID_FLAGS
    return discord.PermissionOverwrite(**{k: v for k, v in flags.items() if k in known})


def bot_can(guild: discord.Guild, name: str) -> bool:
    """Le bot possède-t-il cette permission sur le serveur ?"""
    return bool(getattr(guild.me.guild_permissions, name, False))


def missing_setup_permissions(guild: discord.Guild) -> list[str]:
    """Permissions Discord indispensables à la configuration et aux annonces."""
    return [label for name, label in SETUP_REQUIRED if not bot_can(guild, name)]


def _denied(guild: discord.Guild) -> dict:
    return {name: False for name in READONLY_DENY if bot_can(guild, name)}


def bot_overwrite(guild: discord.Guild) -> discord.PermissionOverwrite:
    return overwrite(**{name: True for name in BOT_ALLOW if bot_can(guild, name)})


def readonly_overwrite(guild: discord.Guild) -> discord.PermissionOverwrite:
    """Voir le salon, le lire, cliquer sur les boutons. Rien d'autre."""
    flags = _denied(guild)
    flags["view_channel"] = True
    flags["read_message_history"] = True
    return overwrite(**flags)


def hidden_overwrite(guild: discord.Guild) -> discord.PermissionOverwrite:
    """Salon masqué, et verrouillé en écriture au cas où la vue serait rendue ailleurs."""
    flags = _denied(guild)
    flags["view_channel"] = False
    return overwrite(**flags)


def category_overwrites(guild: discord.Guild) -> dict:
    """Catégorie verrouillée en écriture (sans toucher à la visibilité)."""
    return {guild.default_role: overwrite(**_denied(guild)), guild.me: bot_overwrite(guild)}


def game_channel_overwrites(guild: discord.Guild, role: discord.Role) -> dict:
    """Salon d'une plateforme : invisible sans son rôle, lecture seule avec."""
    return {
        guild.default_role: hidden_overwrite(guild),
        role: readonly_overwrite(guild),
        guild.me: bot_overwrite(guild),
    }


def inactive_game_channel_overwrites(guild: discord.Guild) -> dict:
    """Cache un salon désactivé tout en laissant le bot le réparer plus tard."""
    return {
        guild.default_role: hidden_overwrite(guild),
        guild.me: bot_overwrite(guild),
    }


def clean_access_roles(guild: discord.Guild, roles: Iterable | None) -> list:
    """Garde les rôles réellement utilisables ; @everyone revient à « tout le monde »."""
    cleaned = []
    for role in roles or []:
        if role is None or role.is_default() or role in cleaned:
            continue
        cleaned.append(role)
    return cleaned[:MAX_ACCESS_ROLES]


def roles_channel_overwrites(guild: discord.Guild, access_roles: Iterable | None = None) -> dict:
    """Salon des rôles : personne ne peut écrire, jamais.

    - sans rôle précisé : visible par tout le monde, en lecture seule ;
    - avec des rôles : visible uniquement par ces rôles, toujours en lecture seule.
    """
    access_roles = clean_access_roles(guild, access_roles)
    overwrites = {guild.me: bot_overwrite(guild)}
    if access_roles:
        overwrites[guild.default_role] = hidden_overwrite(guild)
        for role in access_roles:
            overwrites[role] = readonly_overwrite(guild)
    else:
        overwrites[guild.default_role] = readonly_overwrite(guild)
    return overwrites


def describe_access(access_roles: Iterable | None) -> str:
    if access_roles:
        return ", ".join(role.mention for role in access_roles)
    return "tout le monde (`@everyone`)"


def admin_note(guild: discord.Guild) -> str:
    """Précise le comportement des administrateurs sans rendre la modération obligatoire."""
    if bot_can(guild, "manage_messages"):
        return (
            "\nℹ️ Discord autorise toujours les administrateurs à écrire dans les salons ; "
            "leurs messages y sont supprimés automatiquement grâce à **Gérer les messages**."
        )
    return (
        "\nℹ️ Les membres ne peuvent pas écrire dans ces salons. Discord autorise toujours les "
        "administrateurs ; **Gérer les messages** est facultatif si tu veux que je nettoie leurs messages."
    )

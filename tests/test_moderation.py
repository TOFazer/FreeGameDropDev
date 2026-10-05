"""Personne n'écrit dans le salon des rôles — pas même un administrateur."""

import discord
import pytest

from config import CATEGORY_NAME, ROLES_CHANNEL


@pytest.fixture
def salons(guild, fakes):
    """Un salon des rôles et un salon de jeux, dans la catégorie du bot."""
    category = fakes.Category(guild, CATEGORY_NAME)
    guild.categories.append(category)
    roles_channel = fakes.Channel(ROLES_CHANNEL, category, channel_id=111)
    autre = fakes.Channel("jeux-steam", category, channel_id=222)
    category.channels += [roles_channel, autre]
    return roles_channel, autre


async def test_message_dun_membre_supprime(cog, guild, salons, fakes):
    roles_channel, _ = salons
    cog.roles_channels = {guild.id: roles_channel.id}

    message = fakes.Message(roles_channel, author_id=5, guild=guild)
    await cog.on_message(message)

    assert message.deleted


async def test_message_dun_admin_aussi(cog, guild, salons, fakes):
    """Discord laisse toujours écrire les admins : c'est le bot qui nettoie."""
    roles_channel, _ = salons
    cog.roles_channels = {guild.id: roles_channel.id}

    message = fakes.Message(roles_channel, author_id=1, guild=guild)
    await cog.on_message(message)

    assert message.deleted


async def test_les_autres_salons_ne_sont_pas_touches(cog, guild, salons, fakes):
    roles_channel, autre = salons
    cog.roles_channels = {guild.id: roles_channel.id}

    message = fakes.Message(autre, author_id=5, guild=guild)
    await cog.on_message(message)

    assert not message.deleted


async def test_le_bot_ne_supprime_pas_son_propre_panneau(cog, guild, salons, fakes):
    roles_channel, _ = salons
    cog.roles_channels = {guild.id: roles_channel.id}

    message = fakes.Message(roles_channel, author_id=cog.bot.user.id, guild=guild)
    await cog.on_message(message)

    assert not message.deleted


async def test_messages_prives_ignores(cog, guild, salons, fakes):
    roles_channel, _ = salons

    message = fakes.Message(roles_channel, author_id=5, guild=None)
    await cog.on_message(message)

    assert not message.deleted


async def test_repli_sur_le_nom_du_salon_sans_entree_en_base(cog, guild, salons, fakes):
    roles_channel, _ = salons
    cog.roles_channels = {}

    message = fakes.Message(roles_channel, author_id=5, guild=guild)
    await cog.on_message(message)

    assert message.deleted


async def test_salon_homonyme_hors_categorie_ignore(cog, guild, fakes):
    cog.roles_channels = {}
    sosie = fakes.Channel(ROLES_CHANNEL, None, channel_id=333)

    message = fakes.Message(sosie, author_id=5, guild=guild)
    await cog.on_message(message)

    assert not message.deleted


async def test_salon_renomme_toujours_surveille(cog, guild, fakes):
    """Le salon est reconnu par son identifiant, pas par son nom."""
    cog.roles_channels = {guild.id: 444}
    renomme = fakes.Channel("salon-des-roles", None, channel_id=444)

    message = fakes.Message(renomme, author_id=5, guild=guild)
    await cog.on_message(message)

    assert message.deleted


async def test_suppression_impossible_sans_permission(cog, guild, salons, fakes, caplog):
    roles_channel, _ = salons
    cog.roles_channels = {guild.id: roles_channel.id}
    message = fakes.Message(roles_channel, author_id=5, guild=guild)

    async def refuse():
        raise discord.Forbidden(_Response(), "missing permissions")

    message.delete = refuse

    await cog.on_message(message)  # ne doit pas remonter d'erreur

    assert "Gérer les messages" in caplog.text


class _Response:
    status = 403
    reason = "Forbidden"

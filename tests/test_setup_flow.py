"""Parcours complet : /setup-auto, /acces-salon-roles, relance et /reset-all."""

import discord

from config import CATEGORY_NAME, ROLES_CHANNEL


async def test_setup_cree_categorie_salons_roles(cog, guild, db):
    rapport = await cog.apply_setup(guild, ["steam", "epic"], [])

    category = guild.categories[0]
    assert category.name == CATEGORY_NAME
    assert [c.name for c in category.channels] == ["jeux-steam", "jeux-epic", ROLES_CHANNEL]

    roles_channel = category.channels[-1]
    assert roles_channel.moved, "le salon des rôles est remonté en haut de la catégorie"
    assert "lecture seule" in roles_channel.topic
    assert roles_channel.overwrites[guild.default_role].view_channel is True
    assert roles_channel.overwrites[guild.default_role].send_messages is False

    panneau = roles_channel.sent[-1]
    assert panneau["embed"].title.startswith("🎮")
    assert [b.label for b in panneau["view"].children] == ["Steam", "Epic Games Store"]

    assert "lecture seule" in rapport
    assert await db.get_roles_channel(guild.id) == roles_channel.id
    assert cog.roles_channels == {guild.id: roles_channel.id}


async def test_roles_crees_avec_nom_et_couleur(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])

    role = guild.get_role(await db.get_platform_role(guild.id, "steam"))
    assert role.name == "🔵 Steam"
    assert role.colour == discord.Colour(0x66C0F4)
    assert role.mentionable is True


async def test_salon_de_jeu_reserve_a_son_role(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])

    salon = guild.categories[0].channels[0]
    role = guild.get_role(await db.get_platform_role(guild.id, "steam"))
    assert salon.overwrites[guild.default_role].view_channel is False
    assert salon.overwrites[role].view_channel is True
    assert salon.overwrites[role].send_messages is False


async def test_acces_restreint_puis_rouvert(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])
    salon = guild.categories[0].channels[-1]
    membre = guild.add_role("Membre")

    rapport = await cog.apply_access(guild, [membre])

    assert membre.mention in rapport
    assert salon.overwrites[guild.default_role].view_channel is False
    assert salon.overwrites[membre].view_channel is True
    assert salon.overwrites[membre].send_messages is False
    assert await db.get_roles_channel_access(guild.id) == [membre.id]

    await cog.apply_access(guild, [])

    assert salon.overwrites[guild.default_role].view_channel is True
    assert salon.overwrites[guild.default_role].send_messages is False
    assert membre not in salon.overwrites, "l'ancien rôle d'accès est retiré proprement"
    assert await db.get_roles_channel_access(guild.id) == []


async def test_acces_sans_setup_prealable(cog, guild, db):
    assert "setup-auto" in await cog.apply_access(guild, [])


async def test_relance_ne_duplique_rien_et_conserve_lacces(cog, guild, db):
    await cog.apply_setup(guild, ["steam", "epic"], [])
    membre = guild.add_role("Membre")
    await cog.apply_access(guild, [membre])

    await cog.apply_setup(guild, ["steam", "epic", "gog"], [membre])

    category = guild.categories[0]
    assert len(guild.categories) == 1
    assert [c.name for c in category.channels] == [
        "jeux-steam",
        "jeux-epic",
        ROLES_CHANNEL,
        "jeux-gog",
    ]
    assert len([r for r in guild.roles if r.name == "🔵 Steam"]) == 1
    salon = next(c for c in category.channels if c.name == ROLES_CHANNEL)
    assert salon.overwrites[membre].view_channel is True
    assert len(salon.sent[-1]["view"].children) == 3


async def test_salon_des_roles_retrouve_apres_renommage(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])
    salon = guild.categories[0].channels[-1]
    salon.name = "roles-renomme"

    await cog.apply_setup(guild, ["steam"], [])

    assert len([c for c in guild.categories[0].channels if "role" in c.name]) == 1


async def test_permission_manquante_explique_quoi_faire(cog, guild, db, fakes, monkeypatch):
    async def refuse(*args, **kwargs):
        raise discord.Forbidden(_FakeResponse(), "missing permissions")

    monkeypatch.setattr(fakes.Guild, "create_category", refuse)

    rapport = await cog.apply_setup(guild, ["steam"], [])

    assert "Gérer les salons" in rapport and "Gérer les rôles" in rapport


async def test_avertissement_si_le_bot_ne_peut_pas_moderer(db, fakes, cog_for):
    permissions = discord.Permissions.all()
    permissions.manage_messages = False
    guild = fakes.Guild(permissions)
    cog = cog_for(guild)

    rapport = await cog.apply_setup(guild, ["steam"], [])

    assert "Gérer les messages" in rapport


async def test_reset_all_supprime_tout(cog, guild, db):
    await cog.apply_setup(guild, ["steam", "epic"], [])

    rapport = await cog.wipe_guild(guild)

    assert guild.categories == []
    assert all(r.deleted for r in guild.roles if r.name.endswith(("Steam", "Epic Games Store")))
    assert "Nettoyage terminé" in rapport
    assert cog.roles_channels == {}
    assert await db.get_roles_channel(guild.id) is None
    assert await db.get_platform_channels(guild.id) == {}


class _FakeResponse:
    status = 403
    reason = "Forbidden"

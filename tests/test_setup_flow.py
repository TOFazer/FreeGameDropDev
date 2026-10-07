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


async def test_configurations_simultanees_sans_doublons(cog, guild, db):
    import asyncio

    reports = await asyncio.gather(
        cog.apply_setup(guild, ["steam", "epic"], []),
        cog.apply_setup(guild, ["steam", "epic"], []),
    )
    assert all(report.startswith("✅") for report in reports)
    assert len(guild.categories) == 1
    assert len(guild.text_channels) == 3
    channel = guild.get_channel(await db.get_roles_channel(guild.id))
    assert len(channel.sent) == 1


async def test_repare_role_et_salon_supprimes(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])
    channel_id = (await db.get_platform_channels(guild.id))["steam"]
    role_id = await db.get_platform_role(guild.id, "steam")
    await guild.get_channel(channel_id).delete()
    # Discord retire réellement le rôle du cache lors de sa suppression.
    guild.roles.remove(guild.get_role(role_id))
    assert (await cog.apply_setup(guild, ["steam"], [])).startswith("✅")
    assert (await db.get_platform_channels(guild.id))["steam"] != channel_id
    assert await db.get_platform_role(guild.id, "steam") != role_id
    assert len(guild.text_channels) == 2


async def test_plateforme_decochee_reactivable(cog, guild, db):
    await cog.apply_setup(guild, ["steam", "epic"], [])
    channels = await db.get_platform_channels(guild.id)
    await cog.apply_setup(guild, ["steam"], [])
    assert [route[1] for route in await db.get_routes()] == ["steam"]
    await cog.apply_setup(guild, ["steam", "epic"], [])
    assert await db.get_platform_channels(guild.id) == channels


async def test_permissions_minimales_suffisent(db, fakes, cog_for):
    from utils.branding import INVITE_PERMISSIONS

    guild = fakes.Guild(discord.Permissions(INVITE_PERMISSIONS))
    cog = cog_for(guild)
    assert (await cog.apply_setup(guild, ["steam"], [])).startswith("✅")
    assert (await cog.apply_setup(guild, ["steam"], [])).startswith("✅")
    channel = guild.get_channel(await db.get_roles_channel(guild.id))
    assert len(channel.sent) == 1


async def test_panneau_supprime_recree(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])
    channel = guild.get_channel(await db.get_roles_channel(guild.id))
    old_id = await db.get_roles_panel_message(guild.id)
    await channel.messages[0].delete()
    assert (await cog.apply_setup(guild, ["steam"], [])).startswith("✅")
    assert await db.get_roles_panel_message(guild.id) != old_id


async def test_redemarrage_reutilise_les_identifiants(cog, guild, db, cog_for):
    await cog.apply_setup(guild, ["steam"], [])
    channels = await db.get_platform_channels(guild.id)
    restarted = cog_for(guild)
    await db.init_db()
    assert (await restarted.apply_setup(guild, ["steam"], [])).startswith("✅")
    assert await db.get_platform_channels(guild.id) == channels


async def test_permission_manquante_avant_toute_creation(cog, guild, db):
    guild.me.guild_permissions.manage_roles = False
    report = await cog.apply_setup(guild, ["steam"], [])
    assert "Gérer les rôles" in report
    assert guild.categories == []


async def test_role_homonyme_privilegie_refuse(cog, guild, db):
    role = guild.add_role("🔵 Steam")
    role.permissions = discord.Permissions(administrator=True)
    report = await cog.apply_setup(guild, ["steam"], [])
    assert report.startswith("⚠️")
    assert await db.get_platform_role(guild.id, "steam") is None


async def test_salon_homonyme_non_modifie(cog, guild, db, fakes):
    category = fakes.Category(guild, "Communauté")
    guild.categories.append(category)
    channel = await category.create_text_channel("jeux-steam", topic="À conserver")
    report = await cog.apply_setup(guild, ["steam"], [])
    assert "Renomme" in report
    assert channel.topic == "À conserver"
    assert await db.get_platform_channels(guild.id) == {}


async def test_permission_retiree_pendant_le_menu():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from cogs.jeux import SetupView

    interaction = SimpleNamespace(
        guild=object(),
        user=SimpleNamespace(guild_permissions=discord.Permissions.none()),
        response=SimpleNamespace(send_message=AsyncMock()),
    )
    view = SetupView(None, ["steam"])
    assert not await view.interaction_check(interaction)
    interaction.response.send_message.assert_awaited_once()


async def test_confirmation_declenche_verification_ciblee():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from cogs.jeux import SetupView

    cog = SimpleNamespace(apply_setup=AsyncMock(return_value="✅ Prêt"), run_check=AsyncMock(return_value=1))
    interaction = SimpleNamespace(
        guild=SimpleNamespace(id=7),
        response=SimpleNamespace(edit_message=AsyncMock()),
        edit_original_response=AsyncMock(),
    )
    view = SetupView(cog, ["steam"])
    await view.confirm.callback(interaction)
    cog.run_check.assert_awaited_once_with(target_guild_id=7)
    assert view.is_finished()


async def test_menu_expire_explique_la_reprise():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from cogs.jeux import SetupView

    view = SetupView(None)
    view.message = SimpleNamespace(edit=AsyncMock())
    await view.on_timeout()
    assert "setup-auto" in view.message.edit.call_args.kwargs["content"]
    assert view.message.edit.call_args.kwargs["view"] is None

"""Chargement du bot et panneaux de configuration."""

import discord
import pytest
from discord.ext import commands

import config
from cogs.jeux import AccessView, ConfigView, Jeux, RolesView, SetupView


@pytest.fixture
async def bot_discord(db):
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    async with bot:
        await bot.load_extension("cogs.setup")
        await bot.load_extension("cogs.jeux")
        yield bot


async def test_les_commandes_sont_enregistrees(bot_discord):
    noms = sorted(c.name for c in bot_discord.tree.get_commands())

    assert noms == [
        "acces-salon-roles",
        "config",
        "favoris",
        "free",
        "info",
        "mes-donnees",
        "ping",
        "reset-all",
        "reset-jeux",
        "setup-auto",
        "test-jeux",
    ]


async def test_les_boutons_des_roles_survivent_au_redemarrage(bot_discord):
    vue = next(iter(bot_discord.persistent_views))

    assert [b.custom_id for b in vue.children] == [f"role:{k}" for k in config.PLATFORM_KEYS]
    assert vue.timeout is None


async def test_la_boucle_suit_lintervalle_configure(bot_discord):
    cog = bot_discord.get_cog("Jeux")

    assert cog.check_games.hours == config.CHECK_INTERVAL_HOURS
    assert cog.check_games.is_running()


def test_panneau_de_setup_preselectionne_lexistant():
    vue = SetupView(cog=None, platform_keys=["steam", "gog"], access_roles=[])

    selection = next(c for c in vue.children if hasattr(c, "options"))
    assert [o.value for o in selection.options if o.default] == ["steam", "gog"]
    assert "lecture seule" in vue.summary()
    assert "tout le monde" in vue.summary()
    assert [type(c).__name__ for c in vue.children].count("Button") == 2


def test_panneau_de_setup_sans_plateforme():
    assert "**—**" in SetupView(cog=None).summary()


def test_panneau_dacces():
    vue = AccessView(cog=None)

    assert "lecture seule" in vue.summary()
    assert isinstance(vue, ConfigView)
    assert vue.access_roles == []


def test_bouton_tout_le_monde_vide_la_selection(guild):
    membre = guild.add_role("Membre")
    vue = AccessView(cog=None, access_roles=[membre])
    assert membre.mention in vue.summary()

    vue.reset_access_select()

    assert vue.access_roles == []
    assert vue.access_select.default_values == []
    assert [type(c).__name__ for c in vue.children].count("AccessRoleSelect") == 1
    assert "tout le monde" in vue.summary()


def test_un_bouton_par_plateforme():
    vue = RolesView(config.PLATFORM_KEYS)

    assert [b.label for b in vue.children] == [
        config.PLATFORMS[k].name for k in config.PLATFORM_KEYS
    ]


def test_le_cog_expose_les_actions_utilisees_par_les_vues():
    for action in ("apply_setup", "apply_access", "wipe_guild", "run_check"):
        assert callable(getattr(Jeux, action))

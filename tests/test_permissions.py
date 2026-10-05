"""Le salon des rôles doit être illisible en écriture, et masqué si l'accès est restreint."""

import discord
import pytest

from utils import permissions as perms

ECRITURE = (
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
    "add_reactions",
    "send_tts_messages",
    "attach_files",
    "embed_links",
    "mention_everyone",
    "manage_messages",
    "use_application_commands",
    "send_voice_messages",
    "create_polls",
)


def test_salon_des_roles_visible_par_tous_mais_en_lecture_seule(guild):
    overwrites = perms.roles_channel_overwrites(guild, [])
    everyone = overwrites[guild.default_role]

    assert everyone.view_channel is True
    assert everyone.read_message_history is True
    for flag in ECRITURE:
        assert getattr(everyone, flag) is False, f"{flag} devrait être refusé à @everyone"


def test_salon_des_roles_reserve_a_des_roles(guild):
    membre = guild.add_role("Membre")
    vip = guild.add_role("VIP")

    overwrites = perms.roles_channel_overwrites(guild, [membre, vip])

    assert overwrites[guild.default_role].view_channel is False
    assert overwrites[guild.default_role].send_messages is False
    for role in (membre, vip):
        assert overwrites[role].view_channel is True
        assert overwrites[role].read_message_history is True
        assert overwrites[role].send_messages is False
        assert overwrites[role].add_reactions is False
    assert len(overwrites) == 4  # @everyone + 2 rôles + le bot


def test_le_bot_garde_de_quoi_poster_et_nettoyer(guild):
    overwrites = perms.roles_channel_overwrites(guild, [])
    bot = overwrites[guild.me]

    assert bot.view_channel and bot.send_messages and bot.embed_links
    assert bot.manage_messages is True


def test_everyone_et_doublons_ignores(guild):
    membre = guild.add_role("Membre")

    nettoyes = perms.clean_access_roles(guild, [membre, None, membre, guild.default_role])

    assert nettoyes == [membre]
    # @everyone seul revient à « tout le monde » : le salon reste visible
    assert perms.roles_channel_overwrites(guild, [guild.default_role])[guild.default_role].view_channel


def test_nombre_de_roles_plafonne(guild):
    roles = [guild.add_role(f"Role {i}") for i in range(15)]

    assert len(perms.clean_access_roles(guild, roles)) == 10


def test_permissions_que_le_bot_na_pas_ne_sont_pas_touchees(fakes):
    sans_gestion = discord.Permissions.all()
    sans_gestion.manage_messages = False
    guild = fakes.Guild(sans_gestion)
    membre = guild.add_role("Membre")

    overwrites = perms.roles_channel_overwrites(guild, [membre])

    # Discord refuserait la modification : on laisse le bit tranquille…
    assert overwrites[membre].manage_messages is None
    assert overwrites[guild.me].manage_messages is None
    # … sans rien perdre de l'essentiel
    assert overwrites[membre].send_messages is False
    assert overwrites[membre].view_channel is True


def test_salon_de_jeux_prive_et_en_lecture_seule(guild):
    role = guild.add_role("🔵 Steam")

    overwrites = perms.game_channel_overwrites(guild, role)

    assert overwrites[guild.default_role].view_channel is False
    assert overwrites[role].view_channel is True
    assert overwrites[role].send_messages is False


def test_categorie_verrouillee_sans_toucher_a_la_visibilite(guild):
    overwrites = perms.category_overwrites(guild)

    assert overwrites[guild.default_role].send_messages is False
    assert overwrites[guild.default_role].view_channel is None


def test_version_de_discord_sans_sondages(guild, monkeypatch):
    flags = {k: v for k, v in discord.Permissions.VALID_FLAGS.items() if "poll" not in k}
    monkeypatch.setattr(discord.Permissions, "VALID_FLAGS", flags)

    overwrites = perms.roles_channel_overwrites(guild, [])  # ne doit pas lever

    assert overwrites[guild.default_role].send_messages is False


@pytest.mark.parametrize(
    "roles, attendu",
    [([], "tout le monde (`@everyone`)"), (None, "tout le monde (`@everyone`)")],
)
def test_description_de_laccès_par_defaut(roles, attendu):
    assert perms.describe_access(roles) == attendu


def test_description_de_laccès_avec_roles(guild):
    membre = guild.add_role("Membre")

    assert perms.describe_access([membre]) == membre.mention


def test_note_sur_les_admins(guild, fakes):
    assert "supprimés automatiquement" in perms.admin_note(guild)

    sans_gestion = discord.Permissions.all()
    sans_gestion.manage_messages = False
    assert "Gérer les messages" in perms.admin_note(fakes.Guild(sans_gestion))

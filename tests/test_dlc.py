"""Salon des DLC : création, rôle, routage des annonces et commandes dédiées."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import config
import database
from cogs.jeux import Jeux, RoleButton, RolesView, SetupView
from services import gamerpower, offer_engine
from utils import embeds, offers

JEU_STEAM = {"id": 1, "title": "Jeu complet", "platforms": "PC (Steam)", "type": "Game"}
DLC_STEAM = {
    "id": 2,
    "title": "Extension gratuite",
    "platforms": "PC (Steam)",
    "type": "DLC",
    "end_date": (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
}
DLC_PERMANENT = {
    "id": 3,
    "title": "Pack cosmétique",
    "platforms": "PC (Steam)",
    "type": "Loot",
    "permanently_free": True,
}


def _patch_sources(monkeypatch, games=(), dlc=()):
    async def _games():
        return list(games)

    async def _dlc():
        return list(dlc)

    monkeypatch.setattr(gamerpower, "fetch_giveaways", _games)
    monkeypatch.setattr(gamerpower, "fetch_dlc_giveaways", _dlc)


# ---------- Création du salon et du rôle ----------


async def test_setup_cree_le_salon_et_le_role_dlc(cog, guild, db):
    report = await cog.apply_setup(guild, ["steam"], [])

    channel_id = await db.get_dlc_channel(guild.id)
    channel = guild.get_channel(channel_id)
    assert channel is not None
    assert channel.name == config.DLC_CHANNEL
    assert channel.topic == config.DLC_TOPIC
    assert report.count("dlc-gratuits") >= 1

    role = guild.get_role(await db.get_dlc_role(guild.id))
    assert role.name == config.DLC_ROLE_NAME
    assert role.mentionable is True

    # Même règle que les salons de plateforme : invisible sans le rôle, lecture seule.
    assert channel.overwrites[guild.default_role].view_channel is False
    assert channel.overwrites[role].view_channel is True
    assert channel.overwrites[role].send_messages is False


async def test_setup_signale_la_source_dlc_absente(cog, guild, db, monkeypatch):
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower", "epic"))

    report = await cog.apply_setup(guild, ["steam"], [])

    assert "gamerpower_loot" in report
    assert await db.get_dlc_channel(guild.id) is not None


async def test_panneau_des_roles_propose_le_bouton_dlc(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])

    roles_channel = guild.get_channel(await db.get_roles_channel(guild.id))
    view = roles_channel.sent[-1]["view"]
    assert [b.custom_id for b in view.children] == ["role:steam", f"role:{config.DLC_ROUTE}"]
    assert view.children[-1].label == config.DLC_ROLE_LABEL


async def test_bouton_dlc_attribue_le_role(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])
    button = next(
        b for b in RolesView([*config.PLATFORM_KEYS, config.DLC_ROUTE]).children
        if b.custom_id == f"role:{config.DLC_ROUTE}"
    )
    role = guild.get_role(await db.get_dlc_role(guild.id))
    user = SimpleNamespace(id=42, roles=[], add_roles=AsyncMock(), remove_roles=AsyncMock())
    interaction = SimpleNamespace(
        user=user,
        guild=guild,
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await button.callback(interaction)

    user.add_roles.assert_awaited_once_with(role)
    message = interaction.response.send_message.await_args.args[0]
    assert "DLC" in message


async def test_bouton_dlc_refuse_un_salon_masque(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])
    await database.set_dlc_active(guild.id, False)
    button = RoleButton(config.DLC_ROUTE)
    user = SimpleNamespace(id=42, roles=[], add_roles=AsyncMock(), remove_roles=AsyncMock())
    interaction = SimpleNamespace(
        user=user,
        guild=guild,
        response=SimpleNamespace(send_message=AsyncMock()),
    )

    await button.callback(interaction)

    user.add_roles.assert_not_awaited()
    assert "setup-auto" in interaction.response.send_message.await_args.args[0]


async def test_dlc_masque_puis_reactive_sans_doublon(cog, guild, db):
    await cog.apply_setup(guild, ["steam"], [])
    channel_id = await db.get_dlc_channel(guild.id)
    channel = guild.get_channel(channel_id)

    report = await cog.apply_setup(guild, ["steam"], [], include_dlc=False)

    assert await db.get_dlc_channel(guild.id) is None
    assert await db.get_dlc_channel(guild.id, include_inactive=True) == channel_id
    assert channel.overwrites[guild.default_role].view_channel is False
    assert "masqué" in report.lower()
    assert await db.get_all_dlc_routes() == {}

    await cog.apply_setup(guild, ["steam"], [])

    assert await db.get_dlc_channel(guild.id) == channel_id
    assert len([c for c in guild.categories[0].channels if c.name == config.DLC_CHANNEL]) == 1


async def test_panneau_de_setup_affiche_letat_dlc():
    vue = SetupView(None, ["steam"], [], include_dlc=False)

    assert "masqué" in vue.summary()
    assert any(getattr(b, "label", "") == "Salon DLC : masqué" for b in vue.children)

    vue.include_dlc = True
    vue._sync_dlc_button()
    assert "inclus" in vue.summary()
    assert vue.dlc_button.label == "Salon DLC : inclus"


# ---------- Routage des annonces ----------


async def test_les_dlc_ne_vont_que_dans_leur_salon(cog, guild, db, monkeypatch):
    await cog.apply_setup(guild, ["steam"], [])
    platform_channel = guild.get_channel((await db.get_platform_channels(guild.id))["steam"])
    dlc_channel = guild.get_channel(await db.get_dlc_channel(guild.id))
    dlc_role_id = await db.get_dlc_role(guild.id)
    _patch_sources(monkeypatch, games=[JEU_STEAM], dlc=[DLC_STEAM])

    envoyes = await cog.run_check()

    assert envoyes == 2
    assert [m["embed"].title for m in platform_channel.sent] == ["🔵 Jeu complet"]
    assert [m["embed"].title for m in dlc_channel.sent] == ["🔵 Extension gratuite"]
    assert dlc_channel.sent[0]["content"] == f"<@&{dlc_role_id}> nouveau DLC gratuit !"
    assert platform_channel.sent[0]["content"] == (
        f"<@&{await db.get_platform_role(guild.id, 'steam')}> nouveau jeu gratuit !"
    )


async def test_un_dlc_nest_pas_annonce_deux_fois(cog, guild, db, monkeypatch):
    await cog.apply_setup(guild, ["steam"], [])
    dlc_channel = guild.get_channel(await db.get_dlc_channel(guild.id))
    _patch_sources(monkeypatch, dlc=[DLC_STEAM])

    assert await cog.run_check() == 1
    assert await cog.run_check() == 0
    assert len(dlc_channel.sent) == 1


async def test_le_salon_dlc_respecte_les_plateformes_suivies(cog, guild, db, monkeypatch):
    await cog.apply_setup(guild, ["epic"], [])
    dlc_channel = guild.get_channel(await db.get_dlc_channel(guild.id))
    _patch_sources(monkeypatch, dlc=[DLC_STEAM])

    assert await cog.run_check() == 0
    assert dlc_channel.sent == []


async def test_le_salon_dlc_ne_recoit_rien_sil_est_masque(cog, guild, db, monkeypatch):
    await cog.apply_setup(guild, ["steam"], [], include_dlc=False)
    _patch_sources(monkeypatch, dlc=[DLC_STEAM])

    assert await cog.run_check() == 0


async def test_plafond_des_dlc(cog, guild, db, monkeypatch):
    await cog.apply_setup(guild, ["steam"], [])
    dlc_channel = guild.get_channel(await db.get_dlc_channel(guild.id))
    _patch_sources(monkeypatch, dlc=[dict(DLC_STEAM, id=i) for i in range(10)])

    assert await cog.run_check() == config.MAX_DLC_GAMES
    assert len(dlc_channel.sent) == config.MAX_DLC_GAMES


async def test_un_dlc_reste_un_dlc_dans_les_favoris(db):
    await db.save_giveaways([DLC_STEAM])
    await db.toggle_favorite(42, str(DLC_STEAM["id"]))

    (favori,) = await db.get_favorites(42)

    assert favori["offer_type"] == "dlc"
    assert favori["free_kind"] == "temporary"
    embed, _ = embeds.build_game_message(favori)
    assert "Type" in [f.name for f in embed.fields]


async def test_gratuite_permanente_et_temporaire_affichees(db):
    await db.save_giveaways([DLC_STEAM, DLC_PERMANENT])
    (temporaire,) = await db.get_recent_giveaways(offer_type="dlc")
    permanent = next(g for g in await db.get_recent_giveaways() if g["id"] == str(DLC_PERMANENT["id"]))

    embed_temporaire, _ = embeds.build_game_message(temporaire)
    embed_permanent, _ = embeds.build_game_message(permanent)

    assert dict((f.name, f.value) for f in embed_temporaire.fields)["Gratuité"].startswith("⏳")
    assert dict((f.name, f.value) for f in embed_permanent.fields)["Gratuité"].startswith("♾️")


# ---------- Commandes /dlc et /recap ----------


class _Response:
    def __init__(self):
        self.deferred = None
        self.sent = None

    async def defer(self, **kwargs):
        self.deferred = kwargs

    async def send_message(self, *args, **kwargs):
        self.sent = (args, kwargs)


class _Followup:
    def __init__(self):
        self.sent = None
        self.message = SimpleNamespace(edit=AsyncMock())

    async def send(self, *args, **kwargs):
        self.sent = (args, kwargs)
        return self.message


class _Interaction:
    def __init__(self, user_id=42):
        self.user = SimpleNamespace(id=user_id)
        self.response = _Response()
        self.followup = _Followup()
        self.message = SimpleNamespace()

    async def original_response(self):
        return self.message


async def test_commande_dlc_ne_montre_que_les_dlc(db, monkeypatch):
    _patch_sources(monkeypatch, games=[JEU_STEAM], dlc=[DLC_STEAM])
    interaction = _Interaction()

    await Jeux.dlc.callback(Jeux.__new__(Jeux), interaction)

    _, kwargs = interaction.followup.sent
    assert [g["id"] for g in kwargs["view"].games] == [DLC_STEAM["id"]]
    assert interaction.response.deferred == {"ephemeral": True, "thinking": True}


async def test_commande_dlc_sans_offre(db, monkeypatch):
    _patch_sources(monkeypatch, games=[JEU_STEAM])
    interaction = _Interaction()

    await Jeux.dlc.callback(Jeux.__new__(Jeux), interaction)

    args, _ = interaction.followup.sent
    assert "Aucun DLC" in args[0]


async def test_recap_resume_les_offres_recentes(db):
    await db.save_giveaways([JEU_STEAM, DLC_STEAM])
    interaction = _Interaction()

    await Jeux.recap.callback(Jeux.__new__(Jeux), interaction, heures=24)

    _, kwargs = interaction.response.sent
    assert "24" in kwargs["content"] and "DLC" in kwargs["content"]
    assert kwargs["view"].page_count == 2
    assert kwargs["ephemeral"] is True


async def test_recap_sans_nouveaute(db):
    interaction = _Interaction()

    await Jeux.recap.callback(Jeux.__new__(Jeux), interaction)

    args, _ = interaction.response.sent
    assert "Aucune nouvelle offre" in args[0]


# ---------- Classification ----------


def test_classification_gratuite_permanente():
    assert offers.classify_free_kind({"permanently_free": True}) == "permanent"
    assert offers.classify_free_kind({"free_kind": "permanent"}) == "permanent"
    assert offers.classify_free_kind({"end_date": "2030-01-01 00:00:00"}) == "temporary"
    assert offers.classify_free_kind({}) == "unknown"


def test_is_dlc_offer():
    assert offers.is_dlc_offer({"offer_type": "dlc"}) is True
    assert offers.is_dlc_offer({"offer_type": "content"}) is True
    assert offers.is_dlc_offer({"offer_type": "game"}) is False


async def test_le_moteur_note_la_nature_de_la_gratuite(monkeypatch):
    async def _dlc():
        return [dict(DLC_PERMANENT), dict(DLC_STEAM)]

    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower_loot", _dlc)

    games = await offer_engine.fetch_offers(sources=["gamerpower_loot"])

    kinds = {game["id"]: game["free_kind"] for game in games}
    assert kinds == {DLC_PERMANENT["id"]: "permanent", DLC_STEAM["id"]: "temporary"}

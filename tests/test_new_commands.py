"""Nouvelles commandes : historique, recherche, préférences, alertes, rappels, stats."""

from types import SimpleNamespace

from cogs.jeux import GameBrowserView, Jeux

GAME = {
    "id": 1,
    "title": "Jeu gratuit",
    "platforms": "PC (Steam)",
    "offer_type": "game",
}


class FakeResponse:
    def __init__(self):
        self.sent = None

    async def send_message(self, *args, **kwargs):
        self.sent = (args, kwargs)


class FakeInteraction:
    def __init__(self, user_id=42, guild_id=7, channel=None):
        self.user = SimpleNamespace(id=user_id)
        self.guild = SimpleNamespace(id=guild_id) if guild_id else None
        self.channel = channel or SimpleNamespace(id=999, mention="<#999>")
        self.response = FakeResponse()
        self.message = SimpleNamespace()

    async def original_response(self):
        return self.message


def _cog():
    return Jeux.__new__(Jeux)


async def test_historique_filtre_par_plateforme(db):
    await db.save_giveaways(
        [
            {"id": 1, "title": "Steam", "platforms": "PC (Steam)"},
            {"id": 2, "title": "Epic", "platforms": "Epic Games Store"},
        ]
    )
    interaction = FakeInteraction()

    await Jeux.historique.callback(_cog(), interaction, plateforme="steam", type=None)

    _, kwargs = interaction.response.sent
    assert isinstance(kwargs["view"], GameBrowserView)
    assert [g["id"] for g in kwargs["view"].games] == ["1"]


async def test_historique_vide(db):
    interaction = FakeInteraction()

    await Jeux.historique.callback(_cog(), interaction, plateforme=None, type=None)

    args, kwargs = interaction.response.sent
    assert "Aucune offre" in args[0]


async def test_recherche_trouve_une_offre(db):
    await db.save_giveaways([{"id": 1, "title": "Super RPG", "description": ""}])
    interaction = FakeInteraction()

    await Jeux.recherche.callback(_cog(), interaction, terme="rpg")

    _, kwargs = interaction.response.sent
    assert [g["id"] for g in kwargs["view"].games] == ["1"]


async def test_recherche_sans_resultat(db):
    interaction = FakeInteraction()

    await Jeux.recherche.callback(_cog(), interaction, terme="introuvable")

    args, _ = interaction.response.sent
    assert "Aucune offre trouvée" in args[0]


async def test_preferences_par_defaut_puis_mises_a_jour(db):
    interaction = FakeInteraction()

    await Jeux.preferences.callback(
        _cog(),
        interaction,
        types="game,dlc",
        prix_min=15.0,
        genres="rpg,action",
        plateformes="steam,epic",
        fuseau="Europe/Paris",
    )

    saved = await db.get_user_preferences(42)
    assert saved["offer_types"] == ["game", "dlc"]
    assert saved["min_worth_eur"] == 15.0
    assert sorted(saved["genres"]) == ["action", "rpg"]
    assert saved["platforms"] == ["steam", "epic"]
    assert saved["timezone"] == "Europe/Paris"
    args, kwargs = interaction.response.sent
    assert "Préférences enregistrées" in args[0]
    assert "Steam" in args[0] and "Epic Games Store" in args[0]
    assert kwargs["ephemeral"] is True


async def test_preferences_plateformes_vider_revient_a_toutes(db):
    interaction = FakeInteraction()
    await db.set_user_preferences(42, offer_types=["game"], platforms=["steam"])

    await Jeux.preferences.callback(
        _cog(), interaction, types=None, prix_min=None, genres=None, plateformes="", fuseau=None
    )

    saved = await db.get_user_preferences(42)
    assert saved["platforms"] == []
    args, _ = interaction.response.sent
    assert "toutes" in args[0]


async def test_preferences_partielles_conservent_le_reste(db):
    await db.set_user_preferences(
        42, offer_types=["game"], min_worth_eur=5.0, genres=["rpg"], platforms=["gog"]
    )
    interaction = FakeInteraction()

    await Jeux.preferences.callback(
        _cog(),
        interaction,
        types=None,
        prix_min=None,
        genres=None,
        plateformes=None,
        fuseau=None,
    )

    saved = await db.get_user_preferences(42)
    assert saved["offer_types"] == ["game"]
    assert saved["min_worth_eur"] == 5.0
    assert saved["genres"] == ["rpg"]
    assert saved["platforms"] == ["gog"]


async def test_alertes_active_puis_desactive(db):
    interaction = FakeInteraction()

    await Jeux.alertes.callback(_cog(), interaction, type="new_offer", active=True)
    assert await db.get_user_notifications(42) == {"new_offer": True}

    await Jeux.alertes.callback(_cog(), interaction, type="new_offer", active=False)
    assert await db.get_user_notifications(42) == {"new_offer": False}


async def test_rappel_salon_par_defaut_sur_le_salon_courant(db):
    interaction = FakeInteraction()

    await Jeux.rappel_salon.callback(_cog(), interaction, salon=None)

    assert await db.get_guild_reminder_channel(7) == 999


async def test_dev_stats_refuse_un_non_developpeur(db):
    cog = _cog()

    async def is_owner(user):
        return False

    cog.bot = SimpleNamespace(is_owner=is_owner)
    interaction = FakeInteraction()

    await Jeux.dev_stats.callback(cog, interaction)

    args, kwargs = interaction.response.sent
    assert "réservée au développeur" in args[0]
    assert kwargs["ephemeral"] is True


async def test_dev_stats_affiche_les_chiffres_au_developpeur(db):
    await db.save_giveaways([{"id": 1, "title": "Jeu"}])
    cog = _cog()

    async def is_owner(user):
        return True

    cog.bot = SimpleNamespace(is_owner=is_owner, guilds=[], latency=0.02)
    interaction = FakeInteraction()

    await Jeux.dev_stats.callback(cog, interaction)

    args, _ = interaction.response.sent
    assert "Offres suivies : 1" in args[0]

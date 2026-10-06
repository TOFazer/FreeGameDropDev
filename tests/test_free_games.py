"""Parcours privé des offres et gestion des favoris par membre."""

from types import SimpleNamespace

import pytest

from cogs.jeux import ConfirmDeleteDataView, GameBrowserView, Jeux
from services import gamerpower

GAME = {
    "id": 123,
    "title": "Jeu gratuit",
    "platforms": "PC (Steam)",
    "open_giveaway_url": "https://example.com/claim",
}


class FakeResponse:
    def __init__(self):
        self.deferred = None
        self.sent = None
        self.edited = None

    async def defer(self, **kwargs):
        self.deferred = kwargs

    async def send_message(self, *args, **kwargs):
        self.sent = (args, kwargs)

    async def edit_message(self, **kwargs):
        self.edited = kwargs


class FakeFollowup:
    def __init__(self):
        self.sent = None
        self.message = SimpleNamespace(edit=self.edit_message)

    async def send(self, *args, **kwargs):
        self.sent = (args, kwargs)
        return self.message

    async def edit_message(self, **kwargs):
        self.edited = kwargs


class FakeInteraction:
    def __init__(self, user_id=42):
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.message = SimpleNamespace(edit=self.edit_message)

    async def original_response(self):
        return self.message

    async def edit_message(self, **kwargs):
        self.edited = kwargs


async def test_free_affiche_les_offres_en_ephemere_et_les_met_en_cache(
    monkeypatch, db
):
    async def fake_fetch():
        return [GAME]

    monkeypatch.setattr(gamerpower, "fetch_giveaways", fake_fetch)
    interaction = FakeInteraction()

    await Jeux.free.callback(Jeux.__new__(Jeux), interaction)

    assert interaction.response.deferred == {"ephemeral": True, "thinking": True}
    _, kwargs = interaction.followup.sent
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title.endswith("Jeu gratuit")
    assert kwargs["view"].page_count == 1
    assert kwargs["view"].message is interaction.followup.message

    assert await db.get_favorites(42) == []
    await db.toggle_favorite(42, "123")
    assert (await db.get_favorites(42))[0]["title"] == "Jeu gratuit"


async def test_free_repond_quand_il_ny_a_pas_doffre(monkeypatch, db):
    async def fake_fetch():
        return []

    monkeypatch.setattr(gamerpower, "fetch_giveaways", fake_fetch)
    interaction = FakeInteraction()

    await Jeux.free.callback(Jeux.__new__(Jeux), interaction)

    args, kwargs = interaction.followup.sent
    assert "Aucun jeu gratuit" in args[0]
    assert kwargs["ephemeral"] is True


async def test_le_bouton_ajoute_puis_retire_un_favori(db):
    await db.save_giveaways([GAME])
    view = GameBrowserView([GAME], owner_id=42)
    interaction = SimpleNamespace(response=FakeResponse())

    await view.toggle_favorite(interaction)
    assert await db.is_favorite(42, "123") is True
    assert view.favorite_button.label == "Retirer des favoris"

    await view.toggle_favorite(interaction)
    assert await db.is_favorite(42, "123") is False
    assert view.favorite_button.label == "Ajouter aux favoris"


async def test_retirer_le_dernier_favori_ferme_le_navigateur(db):
    await db.save_giveaways([GAME])
    await db.toggle_favorite(42, "123")
    view = GameBrowserView([GAME], owner_id=42, favorite_ids={"123"}, showing_favorites=True)
    interaction = SimpleNamespace(response=FakeResponse())

    await view.toggle_favorite(interaction)

    assert await db.get_favorite_ids(42) == set()
    assert interaction.response.edited["content"] == "Tu n'as plus aucun favori enregistré."
    assert interaction.response.edited["view"] is None


async def test_favoris_est_ephemere_et_le_bouton_peut_supprimer(db):
    await db.save_giveaways([GAME])
    await db.toggle_favorite(42, "123")
    interaction = FakeInteraction()

    await Jeux.favoris.callback(Jeux.__new__(Jeux), interaction)

    _, kwargs = interaction.response.sent
    assert kwargs["ephemeral"] is True
    assert kwargs["view"].showing_favorites is True
    assert kwargs["view"].message is interaction.message
    assert kwargs["embed"].title.endswith("Jeu gratuit")


async def test_mes_donnees_demande_une_confirmation_privee():
    interaction = FakeInteraction()

    await Jeux.mes_donnees.callback(Jeux.__new__(Jeux), interaction)

    args, kwargs = interaction.response.sent
    assert "supprimera tes favoris" in args[0]
    assert kwargs["ephemeral"] is True
    assert isinstance(kwargs["view"], ConfirmDeleteDataView)
    assert kwargs["view"].owner_id == interaction.user.id


@pytest.mark.parametrize("interaction_user", [42, 99])
async def test_le_navigateur_est_reserve_a_la_personne_qui_l_a_lance(interaction_user):
    view = GameBrowserView([GAME], owner_id=42)
    interaction = FakeInteraction(interaction_user)

    allowed = await view.interaction_check(interaction)

    assert allowed is (interaction_user == 42)
    if interaction_user != 42:
        assert interaction.response.sent[1]["ephemeral"] is True

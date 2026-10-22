"""Fusion des sources d'offres : tolérance aux pannes et dédoublonnage."""

import asyncio

import pytest

import config
from services import offer_engine

GP_GAME = {"id": 1, "title": "Jeu GamerPower", "type": "game"}
EPIC_GAME = {"id": "epic:1", "title": "Jeu Epic", "type": "game", "source": "epic"}


async def _ok(games):
    return games


async def _boom():
    raise RuntimeError("panne réseau")


async def _slow():
    await asyncio.sleep(10)
    return [GP_GAME]


@pytest.fixture(autouse=True)
def sources(monkeypatch):
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower", "epic"))
    monkeypatch.setattr(config, "OFFER_SOURCE_TIMEOUT", 0.05)


async def test_fusionne_toutes_les_sources(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok([GP_GAME]))
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok([EPIC_GAME]))

    games = await offer_engine.fetch_offers()

    ids = {g["id"] for g in games}
    assert ids == {1, "epic:1"}
    assert all(g["offer_type"] == "game" for g in games)


async def test_une_source_en_panne_nempeche_pas_les_autres(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", _boom)
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok([EPIC_GAME]))

    games = await offer_engine.fetch_offers()

    assert [g["id"] for g in games] == ["epic:1"]


async def test_une_source_trop_lente_est_ignoree(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", _slow)
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok([EPIC_GAME]))

    games = await offer_engine.fetch_offers()

    assert [g["id"] for g in games] == ["epic:1"]


async def test_dedoublonnage_par_identifiant(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok([GP_GAME, GP_GAME]))
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok([]))

    games = await offer_engine.fetch_offers()

    assert len(games) == 1


async def test_sources_filtrables_explicitement(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok([GP_GAME]))
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok([EPIC_GAME]))

    games = await offer_engine.fetch_offers(sources=["epic"])

    assert [g["id"] for g in games] == ["epic:1"]


async def test_aucune_source_active():
    assert await offer_engine.fetch_offers(sources=[]) == []


async def test_identifiants_absents_ignores(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok([{}, None, GP_GAME]))
    assert [g["id"] for g in await offer_engine.fetch_offers(sources=["gamerpower"])] == [1]


async def test_liste_sources_vide_nappelle_rien(monkeypatch):
    from unittest.mock import AsyncMock

    fetch = AsyncMock(return_value=[GP_GAME])
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", fetch)
    assert await offer_engine.fetch_offers(sources=[]) == []
    fetch.assert_not_called()


async def test_fusion_en_alternance_entre_sources(monkeypatch):
    """Un gros catalogue GamerPower ne doit jamais reléguer Epic en queue de liste."""
    gp_offers = [{"id": f"gp:{i}", "title": f"GP {i}", "type": "game"} for i in range(1, 26)]
    epic_offers = [
        {"id": "epic:a", "title": "Epic A", "type": "game", "source": "epic"},
        {"id": "epic:b", "title": "Epic B", "type": "game", "source": "epic"},
    ]
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok(gp_offers))
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok(epic_offers))

    games = await offer_engine.fetch_offers()

    assert [g["id"] for g in games[:5]] == ["gp:1", "epic:a", "gp:2", "epic:b", "gp:3"]
    assert len(games) == 27


async def test_doublon_ou_entree_expiree_ne_bloque_pas_lautre_source(monkeypatch):
    """Une entrée rejetée dans la 1re source ne doit pas confisquer l'ID à la 2e."""
    gp_offers = [
        {"id": "partage", "title": "Expiré côté GP", "free_verified": False},
        {"id": "gp:1", "title": "GP 1", "type": "game"},
        {"id": "gp:1", "title": "GP 1 doublon", "type": "game"},
        {"id": "gp:2", "title": "GP 2", "type": "game"},
    ]
    epic_offers = [
        {"id": "partage", "title": "Actif côté Epic", "free_verified": True, "source": "epic"},
        {"id": "epic:2", "title": "Epic 2", "type": "game", "source": "epic"},
    ]
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok(gp_offers))
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok(epic_offers))

    games = await offer_engine.fetch_offers()

    assert [g["id"] for g in games] == ["gp:1", "partage", "gp:2", "epic:2"]
    assert next(g for g in games if g["id"] == "partage")["source"] == "epic"


async def test_identifiant_zero_accepte_mais_booleens_rejetes(monkeypatch):
    entrees = [
        {"id": 0, "title": "Jeu zéro", "type": "game"},
        {"id": False, "title": "Faux booléen", "type": "game"},
        {"id": True, "title": "Vrai booléen", "type": "game"},
        {"id": "   ", "title": "Vide", "type": "game"},
        {"id": None, "title": "Absent", "type": "game"},
    ]
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok(entrees))

    games = await offer_engine.fetch_offers(sources=["gamerpower"])

    assert [g["id"] for g in games] == [0]
    assert offer_engine.reject_reason({"id": 0, "title": "Jeu zéro"}) is None
    assert offer_engine.reject_reason({"id": False, "title": "Faux"}) == "identifiant manquant"

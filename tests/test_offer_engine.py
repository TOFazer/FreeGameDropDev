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

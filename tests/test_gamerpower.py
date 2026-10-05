"""Appel à l'API GamerPower : aucune panne ne doit faire tomber le bot."""

import asyncio

import aiohttp
import pytest

import config
from services import gamerpower

JEUX = [{"id": 1, "title": "Jeu"}]


class FakeResponse:
    def __init__(self, status=200, payload=None, error=None):
        self.status = status
        self._payload = payload
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        if self._error:
            raise self._error
        return self._payload


class FakeSession:
    appels = []

    def __init__(self, response):
        self.response = response

    def __call__(self, timeout=None):
        FakeSession.timeout = timeout
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, params=None):
        FakeSession.appels.append((url, params))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture
def api(monkeypatch):
    def _api(response):
        FakeSession.appels = []
        monkeypatch.setattr(gamerpower.aiohttp, "ClientSession", FakeSession(response))

    return _api


async def test_reponse_normale(api):
    api(FakeResponse(payload=JEUX))

    assert await gamerpower.fetch_giveaways() == JEUX
    assert FakeSession.appels == [(config.GAMERPOWER_API_URL, {"type": "game", "sort-by": "date"})]


async def test_code_derreur_http(api, caplog):
    api(FakeResponse(status=503))

    assert await gamerpower.fetch_giveaways() == []
    assert "503" in caplog.text


async def test_reponse_inattendue(api):
    api(FakeResponse(payload={"erreur": "nope"}))

    assert await gamerpower.fetch_giveaways() == []


async def test_json_illisible(api):
    api(FakeResponse(error=ValueError("pas du JSON")))

    assert await gamerpower.fetch_giveaways() == []


@pytest.mark.parametrize("panne", [aiohttp.ClientError("réseau coupé"), asyncio.TimeoutError()])
async def test_api_injoignable(api, panne, caplog):
    api(panne)

    assert await gamerpower.fetch_giveaways() == []

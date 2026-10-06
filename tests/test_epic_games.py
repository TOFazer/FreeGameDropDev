"""Appel à l'API de l'Epic Games Store : extraction des offres gratuites actives."""

import asyncio

import aiohttp
import pytest

from services import epic_games

PROMO_GRATUITE = {
    "id": "abc123",
    "title": "Super Jeu",
    "description": "Un jeu offert cette semaine",
    "keyImages": [{"type": "OfferImageWide", "url": "https://example.com/wide.jpg"}],
    "price": {"totalPrice": {"fmtPrice": {"originalPrice": "19,99 €"}}},
    "offerMappings": [{"pageSlug": "super-jeu"}],
    "promotions": {
        "promotionalOffers": [
            {
                "promotionalOffers": [
                    {
                        "startDate": "2026-10-01T15:00:00.000Z",
                        "endDate": "2026-10-08T15:00:00.000Z",
                        "discountSetting": {"discountPercentage": 0},
                    }
                ]
            }
        ]
    },
}

PROMO_A_VENIR = {
    "id": "def456",
    "title": "Jeu futur",
    "keyImages": [],
    "price": {"totalPrice": {"fmtPrice": {"originalPrice": "9,99 €"}}},
    "offerMappings": [{"pageSlug": "jeu-futur"}],
    "promotions": {
        "promotionalOffers": [],
        "upcomingPromotionalOffers": [
            {
                "promotionalOffers": [
                    {
                        "startDate": "2026-10-15T15:00:00.000Z",
                        "endDate": "2026-10-22T15:00:00.000Z",
                        "discountSetting": {"discountPercentage": 0},
                    }
                ]
            }
        ],
    },
}


def _payload(elements):
    return {"data": {"Catalog": {"searchStore": {"elements": elements}}}}


class FakeResponse:
    def __init__(self, status=200, payload=None, error=None):
        self.status = status
        self._payload = payload
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        if self._error:
            raise self._error
        return self._payload


class FakeSession:
    appels = []

    def __init__(self, response):
        self.response = response

    def __call__(self, timeout=None):
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
        monkeypatch.setattr(epic_games.aiohttp, "ClientSession", FakeSession(response))

    return _api


async def test_seules_les_offres_actives_sont_gratuites(api):
    api(FakeResponse(payload=_payload([PROMO_GRATUITE, PROMO_A_VENIR])))

    games = await epic_games.fetch_giveaways()

    assert len(games) == 1
    jeu = games[0]
    assert jeu["id"] == "epic:abc123"
    assert jeu["title"] == "Super Jeu"
    assert jeu["platforms"] == "Epic Games Store"
    assert jeu["worth"] == "19,99 €"
    assert jeu["open_giveaway_url"].endswith("/p/super-jeu")
    assert jeu["source"] == "epic"
    assert jeu["end_date"] == "2026-10-08 15:00:00.000"


async def test_aucune_offre_active(api):
    api(FakeResponse(payload=_payload([PROMO_A_VENIR])))

    assert await epic_games.fetch_giveaways() == []


async def test_code_derreur_http(api, caplog):
    api(FakeResponse(status=503))

    assert await epic_games.fetch_giveaways() == []
    assert "503" in caplog.text


async def test_format_inattendu(api):
    api(FakeResponse(payload={"oops": True}))

    assert await epic_games.fetch_giveaways() == []


@pytest.mark.parametrize("panne", [aiohttp.ClientError("réseau coupé"), asyncio.TimeoutError()])
async def test_api_injoignable(api, panne):
    api(panne)

    assert await epic_games.fetch_giveaways() == []

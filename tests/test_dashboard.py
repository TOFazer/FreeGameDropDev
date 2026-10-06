"""Tableau de bord web : pages publiques et connexion Discord (OAuth2)."""

from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

import config
from web import dashboard, dashboard_server


@pytest.fixture
async def client(db):
    bot = SimpleNamespace(guilds=[], latency=0.01)
    app = dashboard_server.create_app(bot)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


async def test_page_daccueil_publique(client, db):
    await db.save_giveaways([{"id": 1, "title": "Jeu"}])

    resp = await client.get("/")

    assert resp.status == 200
    text = await resp.text()
    assert "FreeGameDrop" in text
    assert "Se connecter avec Discord" in text


async def test_api_stats_json(client, db):
    await db.save_giveaways([{"id": 1, "title": "Jeu", "source": "epic"}])

    resp = await client.get("/api/stats")

    assert resp.status == 200
    data = await resp.json()
    assert data["total_offers"] == 1
    assert data["offers_by_source"] == {"epic": 1}


async def test_login_redirige_vers_discord_avec_un_cookie_detat(client, monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CLIENT_ID", "123")

    resp = await client.get("/login", allow_redirects=False)

    assert resp.status == 302
    assert "discord.com" in resp.headers["Location"]
    assert dashboard_server.STATE_COOKIE in resp.cookies


async def test_cookies_ne_sont_pas_secure_en_http_par_defaut(client, monkeypatch):
    monkeypatch.setattr(config, "DASHBOARD_COOKIE_SECURE", False)

    resp = await client.get("/login", allow_redirects=False)

    state_cookie = resp.cookies[dashboard_server.STATE_COOKIE]
    assert state_cookie["httponly"] is True
    assert state_cookie["samesite"] == "Lax"
    assert state_cookie["secure"] == ""


async def test_cookies_sont_secure_quand_configure(client, monkeypatch):
    monkeypatch.setattr(config, "DASHBOARD_COOKIE_SECURE", True)

    resp = await client.get("/login", allow_redirects=False)

    state_cookie = resp.cookies[dashboard_server.STATE_COOKIE]
    assert state_cookie["secure"] is True


def test_url_dautorisation_encode_les_parametres(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CLIENT_ID", "123")
    monkeypatch.setattr(
        config, "DISCORD_OAUTH_REDIRECT_URI", "https://freegamedrop.fr/auth/callback?x=1&y=2"
    )

    url = dashboard.build_authorize_url("un état avec espace & un symbole")

    assert "freegamedrop.fr%2Fauth%2Fcallback%3Fx%3D1%26y%3D2" in url
    assert "un+%C3%A9tat+avec+espace+%26+un+symbole" in url
    assert " " not in url
    assert url.count("&") == 4  # un seul « & » par séparateur entre les 5 paramètres


def test_cookie_secure_detecte_automatiquement_le_https(monkeypatch):
    import importlib

    monkeypatch.setenv("DASHBOARD_BASE_URL", "https://freegamedrop.fr")
    monkeypatch.delenv("DASHBOARD_COOKIE_SECURE", raising=False)
    reloaded = importlib.reload(config)
    try:
        assert reloaded.DASHBOARD_COOKIE_SECURE is True
    finally:
        monkeypatch.undo()
        importlib.reload(config)


async def test_callback_refuse_un_etat_invalide(client):
    resp = await client.get("/auth/callback", params={"code": "abc", "state": "mauvais"})

    assert resp.status == 400
    text = await resp.text()
    assert "refusée" in text


async def test_callback_cree_une_session_et_pose_un_cookie(client, monkeypatch, db):
    async def fake_complete_login(code):
        assert code == "abc"
        return {"session_id": "tok123", "user": {"id": "42", "username": "Alice"}}

    monkeypatch.setattr(dashboard, "complete_login", fake_complete_login)
    await db.create_dashboard_session("tok123", 42, "Alice", "", dashboard.session_expiry())

    login_resp = await client.get("/login", allow_redirects=False)
    state_cookie = login_resp.cookies[dashboard_server.STATE_COOKIE].value

    client.session.cookie_jar.update_cookies({dashboard_server.STATE_COOKIE: state_cookie})
    resp = await client.get(
        "/auth/callback", params={"code": "abc", "state": state_cookie}, allow_redirects=False
    )

    assert resp.status == 302
    assert dashboard.SESSION_COOKIE in resp.cookies


async def test_accueil_personnalise_quand_connecte(client, db):
    await db.create_dashboard_session("tok456", 42, "Bob", "", dashboard.session_expiry())
    client.session.cookie_jar.update_cookies({dashboard.SESSION_COOKIE: "tok456"})

    resp = await client.get("/")

    text = await resp.text()
    assert "Bob" in text
    assert "Se déconnecter" in text


async def test_logout_supprime_la_session(client, db):
    await db.create_dashboard_session("tok789", 42, "Carl", "", dashboard.session_expiry())
    client.session.cookie_jar.update_cookies({dashboard.SESSION_COOKIE: "tok789"})

    resp = await client.get("/logout", allow_redirects=False)

    assert resp.status == 302
    assert await db.get_dashboard_session("tok789") is None

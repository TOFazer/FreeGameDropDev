"""Tableau de bord web : pages publiques et connexion Discord (OAuth2)."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

import config
from utils import design
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


async def test_page_daccueil_porte_lidentite_freegamedrop(client, db):
    resp = await client.get("/")

    text = await resp.text()
    # thème sombre issu des tokens, police Inter, bouton principal de marque
    assert f"--fgd-primary: {design.PRIMARY};" in text
    assert f"--fgd-background: {design.BACKGROUND};" in text
    assert "Inter" in text
    assert "var(--fgd-primary)" in text
    # branding discret en pied de page
    assert design.FOOTER in text


async def test_page_offres_affiche_les_offres_avec_lidentite(client, db):
    fin = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    await db.save_giveaways(
        [
            {
                "id": 1,
                "title": "Super Jeu",
                "platforms": "PC (Steam)",
                "worth": "19.99€",
                "end_date": fin,
                "thumbnail": "https://example.com/jeu.jpg",
                "open_giveaway_url": "https://example.com/jeu",
                "source": "gamerpower",
            }
        ]
    )

    resp = await client.get("/offres")

    assert resp.status == 200
    text = await resp.text()
    assert 'class="offer-thumb"' in text  # vignette 16:9, présentation cohérente
    assert f"aspect-ratio: {design.IMAGE_RATIO}" in text
    assert '<span class="badge free">GRATUIT</span>' in text  # badge principal
    assert 'class="badge platform-steam"' in text  # badge plateforme, couleur Steam
    assert "<s" in text and "GRATUIT" in text  # prix barré → gratuit
    assert "🎁 Récupérer le jeu" in text  # CTA principal
    assert "jours restants" in text  # échéance avec niveau d'urgence


async def test_api_stats_json(client, db):
    await db.save_giveaways([{"id": 1, "title": "Jeu", "source": "epic"}])

    resp = await client.get("/api/stats")

    assert resp.status == 200
    data = await resp.json()
    assert data["total_offers"] == 1
    assert data["offers_by_source"] == {"epic": 1}


async def test_api_health_pour_la_supervision(client, db):
    resp = await client.get("/api/health")

    assert resp.status == 200
    data = await resp.json()
    assert data["status"] in {"ok", "degraded", "down"}
    assert data["components"]["database"] == "ok"
    assert data["components"]["bot"] == "ok"
    assert data["sources"] == []
    assert "generated_at" in data


async def test_health_repond_la_meme_chose_que_api_health(client, db):
    resp = await client.get("/health")

    assert resp.status == 200
    assert (await resp.json())["components"]["database"] == "ok"


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


# ---------- Nouveau tableau de bord : serveurs, offres, alertes, compte ----------


def _perms(**overrides):
    """Permissions du bot sur un faux serveur : tout accordé sauf mention contraire."""
    flags = {attr: True for attr, _label, _desc in dashboard.REQUIRED_BOT_PERMISSIONS}
    flags.update(overrides)
    return SimpleNamespace(**flags)


class _FakeRole:
    def __init__(self, role_id, name, default=False):
        self.id = role_id
        self.name = name
        self._default = default

    def is_default(self):
        return self._default


class _FakeChannel:
    def __init__(self, channel_id, name):
        self.id = channel_id
        self.name = name


class _FakeGuild:
    def __init__(self, guild_id, name="Mon serveur", permissions=None):
        self.id = guild_id
        self.name = name
        self.text_channels = [_FakeChannel(501, "général"), _FakeChannel(502, "jeux-steam")]
        self.roles = [_FakeRole(1, "@everyone", default=True), _FakeRole(601, "Steam")]
        self.me = SimpleNamespace(guild_permissions=permissions or _perms())


class _FakeBot:
    def __init__(self, *guilds):
        self.guilds = list(guilds)
        self.latency = 0.01

    def get_guild(self, guild_id):
        return next((g for g in self.guilds if g.id == guild_id), None)


@pytest.fixture
async def guild_client(db):
    """Client dont le bot est présent sur le serveur 123 (et seulement lui)."""
    bot = _FakeBot(_FakeGuild(123, "Serveur Gaming"))
    app = dashboard_server.create_app(bot)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


async def _login(db, client, guilds=None, user_id=42, csrf="csrf-test", session_id="tok-sess"):
    await db.create_dashboard_session(
        session_id,
        user_id,
        "Alice",
        "",
        dashboard.session_expiry(),
        csrf_token=csrf,
        guilds_json=json.dumps(guilds or []),
    )
    client.session.cookie_jar.update_cookies({dashboard.SESSION_COOKIE: session_id})


def test_url_dautorisation_demande_le_scope_guilds(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CLIENT_ID", "123")

    url = dashboard.build_authorize_url("etat")

    assert "scope=identify+guilds" in url


def test_lien_dinvitation_utilise_les_permissions_du_readme(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CLIENT_ID", "123")

    url = dashboard.build_invite_url(guild_id=987)

    assert "permissions=268454928" in url
    assert "guild_id=987" in url
    assert "scope=bot+applications.commands" in url


def test_filtre_des_serveurs_gerables_par_permissions():
    guilds = [
        {"id": "1", "name": "Proprio", "owner": True, "permissions": "0"},
        {"id": "2", "name": "Admin", "owner": False, "permissions": str(0x8)},
        {"id": "3", "name": "Manager", "owner": False, "permissions": str(0x20)},
        {"id": "4", "name": "Simple membre", "owner": False, "permissions": str(0x400)},
    ]

    manageable = dashboard.filter_manageable_guilds(guilds)

    assert [g["id"] for g in manageable] == ["1", "2", "3"]


async def test_serveurs_exige_une_connexion(guild_client):
    resp = await guild_client.get("/serveurs", allow_redirects=False)

    assert resp.status == 302
    assert resp.headers["Location"] == "/login"


async def test_serveurs_distingue_bot_present_ou_absent(guild_client, db, monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CLIENT_ID", "123")
    await _login(
        db,
        guild_client,
        guilds=[
            {"id": "123", "name": "Serveur Gaming", "icon": ""},
            {"id": "456", "name": "Serveur XYZ", "icon": ""},
        ],
    )

    resp = await guild_client.get("/serveurs")

    text = await resp.text()
    assert resp.status == 200
    assert "Serveur Gaming" in text and "Configurer" in text
    assert "Serveur XYZ" in text and "Ajouter FreeGameDrop" in text


async def test_config_refusee_pour_un_serveur_non_gerable(guild_client, db):
    await _login(db, guild_client, guilds=[{"id": "456", "name": "Autre", "icon": ""}])

    resp = await guild_client.get("/serveurs/123")

    assert resp.status == 404


async def test_config_refusee_si_le_bot_est_absent(guild_client, db):
    await _login(db, guild_client, guilds=[{"id": "456", "name": "Sans bot", "icon": ""}])

    resp = await guild_client.get("/serveurs/456")

    assert resp.status == 404
    assert "pas (ou plus) présent" in await resp.text()


async def test_config_affiche_salons_roles_et_permissions(guild_client, db):
    await _login(db, guild_client, guilds=[{"id": "123", "name": "Serveur Gaming", "icon": ""}])
    await db.set_platform_channel(123, "steam", 502)

    resp = await guild_client.get("/serveurs/123")

    text = await resp.text()
    assert resp.status == 200
    assert "jeux-steam" in text  # salon proposé dans les listes
    assert "Gérer les rôles" in text  # tableau des permissions
    assert "Permissions manquantes" not in text  # tout est accordé dans ce faux serveur


async def test_config_signale_une_permission_manquante(db):
    bot = _FakeBot(_FakeGuild(123, permissions=_perms(manage_roles=False)))
    app = dashboard_server.create_app(bot)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        await _login(db, client, guilds=[{"id": "123", "name": "Serveur", "icon": ""}])

        resp = await client.get("/serveurs/123")

        text = await resp.text()
        assert "⚠️" in text
        assert "Permissions manquantes : Gérer les rôles" in text
        assert "Corriger" in text
    finally:
        await client.close()


async def test_config_enregistre_salon_et_role(guild_client, db):
    await _login(db, guild_client, guilds=[{"id": "123", "name": "Serveur Gaming", "icon": ""}])

    resp = await guild_client.post(
        "/serveurs/123",
        data={"csrf": "csrf-test", "channel_steam": "502", "role_steam": "601",
              "reminder_channel": "501"},
        allow_redirects=False,
    )

    assert resp.status == 302
    assert (await db.get_platform_channels(123)) == {"steam": 502}
    assert await db.get_guild_platforms(123) == ["steam"]
    assert (await db.get_guild_platform_roles(123)) == {"steam": 601}
    assert (await db.get_guild_reminder_channel(123)) == 501


async def test_config_rejette_un_salon_etranger_au_serveur(guild_client, db):
    await _login(db, guild_client, guilds=[{"id": "123", "name": "Serveur Gaming", "icon": ""}])

    resp = await guild_client.post(
        "/serveurs/123",
        data={"csrf": "csrf-test", "channel_steam": "99999", "role_steam": "1"},
        allow_redirects=False,
    )

    assert resp.status == 302  # la page revient, mais rien n'est écrit
    assert (await db.get_platform_channels(123)) == {}
    assert (await db.get_guild_platform_roles(123)) == {}


async def test_post_sans_jeton_csrf_est_refuse(guild_client, db):
    await _login(db, guild_client, guilds=[{"id": "123", "name": "Serveur Gaming", "icon": ""}])

    resp = await guild_client.post(
        "/serveurs/123", data={"channel_steam": "502"}, allow_redirects=False
    )

    assert resp.status == 403
    assert (await db.get_platform_channels(123)) == {}


async def test_offres_est_publique_et_filtrable(client, db):
    await db.save_giveaways(
        [
            {"id": 1, "title": "Jeu Steam", "platforms": "Steam", "worth": "9.99€",
             "open_giveaway_url": "https://store.steampowered.com/jeu"},
            {"id": 2, "title": "Jeu Epic", "platforms": "Epic Games Store"},
        ]
    )

    resp = await client.get("/offres")
    text = await resp.text()
    assert resp.status == 200
    assert "Jeu Steam" in text and "Jeu Epic" in text
    assert "GRATUIT" in text
    assert "Récupérer" in text  # bouton construit depuis open_giveaway_url

    resp = await client.get("/offres", params={"plateforme": "steam"})
    text = await resp.text()
    assert "Jeu Steam" in text
    assert "Jeu Epic" not in text


async def test_alertes_exige_une_connexion(client):
    resp = await client.get("/alertes", allow_redirects=False)

    assert resp.status == 302
    assert resp.headers["Location"] == "/login"


async def test_alertes_enregistre_evenements_et_types(client, db):
    await _login(db, client)

    resp = await client.post(
        "/alertes",
        data={"csrf": "csrf-test", "event_new_offer": "on", "type_game": "on", "type_dlc": "on"},
        allow_redirects=False,
    )

    assert resp.status == 302
    notifications = await db.get_user_notifications(42)
    assert notifications.get("new_offer") is True
    assert notifications.get("ending_soon") is False
    preferences = await db.get_user_preferences(42)
    assert preferences["offer_types"] == ["game", "dlc"]


async def test_alertes_conserve_les_autres_preferences(client, db):
    await _login(db, client)
    await db.set_user_preferences(42, offer_types=["game"], min_worth_eur=5.0,
                                  genres=["rpg"], timezone="Europe/Paris")

    await client.post(
        "/alertes", data={"csrf": "csrf-test", "type_content": "on"}, allow_redirects=False
    )

    preferences = await db.get_user_preferences(42)
    assert preferences["offer_types"] == ["content"]
    assert preferences["min_worth_eur"] == 5.0
    assert preferences["genres"] == ["rpg"]
    assert preferences["timezone"] == "Europe/Paris"


async def test_compte_affiche_le_resume_sans_id_complet(client, db):
    await _login(db, client, user_id=123456789012345678)
    await db.save_giveaways([{"id": 1, "title": "Jeu"}])
    await db.toggle_favorite(123456789012345678, "1")

    resp = await client.get("/compte")

    text = await resp.text()
    assert resp.status == 200
    assert "Alice" in text
    assert "123456789012345678" not in text  # l'ID complet n'est jamais affiché
    assert "Favoris" in text


async def test_suppression_du_compte_efface_tout_et_deconnecte(client, db):
    await _login(db, client)
    await db.save_giveaways([{"id": 1, "title": "Jeu"}])
    await db.toggle_favorite(42, "1")
    await db.set_user_notification(42, "new_offer", True)

    resp = await client.post(
        "/compte/supprimer", data={"csrf": "csrf-test"}, allow_redirects=False
    )

    assert resp.status == 302
    assert await db.get_favorite_ids(42) == set()
    assert not (await db.get_user_notifications(42)).get("new_offer")
    assert await db.get_dashboard_session("tok-sess") is None


# ---------- Environnement affiché ----------


async def test_tableau_de_bord_dev_ne_ressemble_pas_a_la_production(client, monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "development")

    text = await (await client.get("/")).text()

    assert "FreeGameDrop DEV" in text
    assert "🧪 DEV" in text
    assert "environnement de développement" in text
    assert "<title>🧪 FreeGameDrop DEV" in text


async def test_tableau_de_bord_prod_garde_le_nom_public(client, monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")

    text = await (await client.get("/")).text()

    assert "<title>FreeGameDrop" in text
    assert "FreeGameDrop DEV" not in text
    assert "🧪 DEV" not in text


async def test_tableau_de_bord_signale_la_maintenance(client, monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "MAINTENANCE_MODE", True)

    text = await (await client.get("/")).text()

    assert "Maintenance : les annonces automatiques sont suspendues." in text


async def test_api_health_expose_lenvironnement(client, db, monkeypatch):
    """Un superviseur externe doit pouvoir distinguer DEV et PROD sur cette URL."""
    monkeypatch.setattr(config, "ENVIRONMENT", "development")

    payload = await (await client.get("/api/health")).json()

    assert payload["environment"] == "development"

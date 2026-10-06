"""Logique du tableau de bord web : pages HTML et échanges OAuth2 Discord.

Ce module ne connaît pas aiohttp.web : il construit des chaînes de caractères
et fait des appels réseau isolés dans de petites fonctions, pour rester
testable sans serveur HTTP réel. `web.dashboard_server` s'occupe du routage.
"""

from __future__ import annotations

import html
import secrets
from datetime import datetime, timedelta, timezone

import aiohttp

import config
import database

SESSION_COOKIE = "fgd_session"
SESSION_DURATION_HOURS = 24 * 7


def build_authorize_url(state: str) -> str:
    """URL vers laquelle rediriger un visiteur pour se connecter avec Discord."""
    params = {
        "client_id": config.DISCORD_CLIENT_ID,
        "redirect_uri": config.DISCORD_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": state,
    }
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{config.DISCORD_API_BASE_URL}/oauth2/authorize?{query}"


async def exchange_code_for_token(code: str) -> dict | None:
    """Échange le code OAuth2 contre un jeton d'accès Discord."""
    data = {
        "client_id": config.DISCORD_CLIENT_ID,
        "client_secret": config.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.DISCORD_OAUTH_REDIRECT_URI,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{config.DISCORD_API_BASE_URL}/oauth2/token", data=data) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


async def fetch_discord_user(access_token: str) -> dict | None:
    """Identité Discord minimale (id, pseudo, avatar) associée à un jeton d'accès."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{config.DISCORD_API_BASE_URL}/users/@me", headers=headers) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


def new_state_token() -> str:
    return secrets.token_urlsafe(24)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def session_expiry(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(hours=SESSION_DURATION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")


async def start_login(bot) -> tuple[str, str]:
    """Retourne (state, url_de_connexion) ; `state` doit être stocké dans un cookie court."""
    state = new_state_token()
    return state, build_authorize_url(state)


async def complete_login(code: str) -> dict | None:
    """Échange le code contre un jeton puis crée une session. Retourne la session créée."""
    token_payload = await exchange_code_for_token(code)
    if not token_payload or "access_token" not in token_payload:
        return None

    user = await fetch_discord_user(token_payload["access_token"])
    if not user or "id" not in user:
        return None

    session_id = new_session_id()
    await database.create_dashboard_session(
        session_id,
        int(user["id"]),
        user.get("username", ""),
        user.get("avatar") or "",
        session_expiry(),
    )
    return {"session_id": session_id, "user": user}


async def current_session(session_id: str | None) -> dict | None:
    if not session_id:
        return None
    return await database.get_dashboard_session(session_id)


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; background: #0f1117; color: #e6e6e6; }}
header {{ padding: 24px; background: #161925; }}
main {{ padding: 24px; max-width: 900px; margin: 0 auto; }}
.card {{ background: #1c2030; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }}
a.button {{ display: inline-block; background: #5865F2; color: white; padding: 10px 18px;
            border-radius: 8px; text-decoration: none; font-weight: 600; }}
table {{ width: 100%; border-collapse: collapse; }}
td, th {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #2a2f45; }}
</style>
</head>
<body>
<header><h1>🎮 FreeGameDrop</h1></header>
<main>
{body}
</main>
</body>
</html>"""


def render_home(stats: dict, user: dict | None) -> str:
    cards = "".join(
        f'<div class="card"><h3>{html.escape(str(value))}</h3><p>{html.escape(label)}</p></div>'
        for label, value in (
            ("Serveurs", stats.get("guilds", 0)),
            ("Offres suivies", stats.get("total_offers", 0)),
            ("Offres (30 jours)", stats.get("offers_last_30_days", 0)),
            ("Favoris enregistrés", stats.get("total_favorites", 0)),
        )
    )
    if user:
        account = f"<p>Connecté en tant que <strong>{html.escape(user.get('username', ''))}</strong> " \
                  f'· <a href="/logout">Se déconnecter</a></p>'
    else:
        account = '<p><a class="button" href="/login">Se connecter avec Discord</a></p>'

    sources = stats.get("offers_by_source") or {}
    sources_rows = "".join(
        f"<tr><td>{html.escape(source)}</td><td>{count}</td></tr>"
        for source, count in sorted(sources.items())
    )

    return _page(
        "FreeGameDrop — Tableau de bord",
        f"""
{account}
<div class="grid">{cards}</div>
<div class="card">
<h3>Offres par source</h3>
<table><tr><th>Source</th><th>Offres</th></tr>{sources_rows}</table>
</div>
""",
    )


def render_error(message: str) -> str:
    return _page("FreeGameDrop — Erreur", f'<div class="card"><p>{html.escape(message)}</p></div>')

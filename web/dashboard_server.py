"""Serveur HTTP du tableau de bord (aiohttp.web), lancé en option à côté du bot.

Règles d'accès :
- les pages « Serveurs », « Alertes » et « Compte » exigent une session Discord ;
- un serveur n'est configurable que si le membre peut le gérer (instantané OAuth
  pris à la connexion) ET que le bot y est réellement présent ;
- chaque POST est protégé par le jeton anti-CSRF de la session.
"""

from __future__ import annotations

import logging

from aiohttp import web

import config
import database
from utils import metrics
from web import dashboard

log = logging.getLogger(__name__)

STATE_COOKIE = "fgd_oauth_state"
BOT_KEY = web.AppKey("bot", object)


# ---------- Aides ----------


async def _session_of(request: web.Request) -> dict | None:
    return await dashboard.current_session(request.cookies.get(dashboard.SESSION_COOKIE))


def _require_login(session: dict | None) -> None:
    """Renvoie le visiteur vers la connexion s'il n'a pas de session valide."""
    if session is None:
        raise web.HTTPFound("/login")


async def _check_csrf(request: web.Request, session: dict) -> None:
    data = await request.post()
    expected = session.get("csrf_token") or ""
    provided = str(data.get("csrf") or "")
    if not expected or provided != expected:
        raise web.HTTPForbidden(text="Jeton de sécurité invalide — recharge la page.")


def _bot_guild(request: web.Request, guild_id: str):
    """L'objet Guild du bot pour ce serveur, ou None si le bot n'y est pas."""
    bot = request.app[BOT_KEY]
    if bot is None:
        return None
    try:
        return bot.get_guild(int(guild_id))
    except (TypeError, ValueError):
        return None


def _guild_permissions(guild) -> list[tuple[str, str, bool]]:
    """[(label, description, accordée)] pour chaque permission requise."""
    me = getattr(guild, "me", None)
    perms = getattr(me, "guild_permissions", None)
    return [
        (label, description, bool(getattr(perms, attr, False)))
        for attr, label, description in dashboard.REQUIRED_BOT_PERMISSIONS
    ]


def _guild_channels(guild) -> list[tuple[int, str]]:
    return [(channel.id, channel.name) for channel in getattr(guild, "text_channels", [])]


def _guild_roles(guild) -> list[tuple[int, str]]:
    return [
        (role.id, role.name)
        for role in getattr(guild, "roles", [])
        if not (hasattr(role, "is_default") and role.is_default())
    ]


# ---------- Pages publiques ----------


async def handle_home(request: web.Request) -> web.Response:
    bot = request.app[BOT_KEY]
    session = await _session_of(request)
    stats = await metrics.build_dev_stats(bot) if bot is not None else await database.get_giveaway_stats()
    return web.Response(text=dashboard.render_home(stats, session), content_type="text/html")


async def handle_api_stats(request: web.Request) -> web.Response:
    bot = request.app[BOT_KEY]
    stats = await metrics.build_dev_stats(bot) if bot is not None else await database.get_giveaway_stats()
    return web.json_response(stats)


async def handle_offers(request: web.Request) -> web.Response:
    session = await _session_of(request)
    platform = request.query.get("plateforme") or None
    if platform not in config.PLATFORM_KEYS:
        platform = None
    offers = await database.get_recent_giveaways(limit=30, platform=platform)
    return web.Response(
        text=dashboard.render_offers(offers, session, platform), content_type="text/html"
    )


# ---------- Mes serveurs ----------


async def handle_guilds(request: web.Request) -> web.Response:
    session = await _session_of(request)
    _require_login(session)

    guilds = []
    for guild in session.get("guilds") or []:
        guilds.append({**guild, "bot_present": _bot_guild(request, guild.get("id")) is not None})
    # Les serveurs où le bot est déjà installé d'abord, puis par nom.
    guilds.sort(key=lambda g: (not g["bot_present"], str(g.get("name", "")).casefold()))
    return web.Response(text=dashboard.render_guilds(session, guilds), content_type="text/html")


async def _load_guild_or_404(request: web.Request, session: dict):
    """Vérifie que le membre peut gérer ce serveur ET que le bot y est présent."""
    guild_id = request.match_info["guild_id"]
    entry = dashboard.session_guild(session, guild_id)
    if entry is None:
        raise web.HTTPNotFound(
            text=dashboard.render_error(
                "Ce serveur n'existe pas ou tu n'as pas la permission de le gérer.", session
            ),
            content_type="text/html",
        )
    guild = _bot_guild(request, guild_id)
    if guild is None:
        raise web.HTTPNotFound(
            text=dashboard.render_error(
                "FreeGameDrop n'est pas (ou plus) présent sur ce serveur.", session
            ),
            content_type="text/html",
        )
    return entry, guild


async def _render_guild_config(
    session: dict, entry: dict, guild, *, saved: bool = False
) -> web.Response:
    guild_id = int(entry["id"])
    return web.Response(
        text=dashboard.render_guild_config(
            session,
            entry,
            channels=_guild_channels(guild),
            roles=_guild_roles(guild),
            platform_channels=await database.get_platform_channels(guild_id),
            platform_roles=await database.get_guild_platform_roles(guild_id),
            reminder_channel_id=await database.get_guild_reminder_channel(guild_id),
            permissions=_guild_permissions(guild),
            csrf_token=session.get("csrf_token") or "",
            saved=saved,
        ),
        content_type="text/html",
    )


async def handle_guild_config(request: web.Request) -> web.Response:
    session = await _session_of(request)
    _require_login(session)
    entry, guild = await _load_guild_or_404(request, session)
    saved = request.query.get("ok") == "1"
    return await _render_guild_config(session, entry, guild, saved=saved)


async def handle_guild_config_save(request: web.Request) -> web.Response:
    session = await _session_of(request)
    _require_login(session)
    entry, guild = await _load_guild_or_404(request, session)
    await _check_csrf(request, session)

    data = await request.post()
    guild_id = int(entry["id"])
    valid_channels = {channel_id for channel_id, _name in _guild_channels(guild)}
    valid_roles = {role_id for role_id, _name in _guild_roles(guild)}

    def _clean_id(raw: object, allowed: set[int]) -> int | None:
        """Un identifiant n'est accepté que s'il appartient vraiment à CE serveur."""
        text = str(raw or "").strip()
        if not text.isdigit():
            return None
        value = int(text)
        return value if value in allowed else None

    for key in config.PLATFORM_KEYS:
        channel_id = _clean_id(data.get(f"channel_{key}"), valid_channels)
        if channel_id is not None:
            await database.set_platform_channel(guild_id, key, channel_id)
        role_id = _clean_id(data.get(f"role_{key}"), valid_roles)
        if role_id is not None:
            await database.set_platform_role(guild_id, key, role_id)

    reminder_id = _clean_id(data.get("reminder_channel"), valid_channels)
    if reminder_id is not None:
        await database.set_guild_reminder_channel(guild_id, reminder_id)

    raise web.HTTPFound(f"/serveurs/{guild_id}?ok=1")


# ---------- Alertes personnelles ----------


async def handle_alerts(request: web.Request) -> web.Response:
    session = await _session_of(request)
    _require_login(session)
    user_id = session["user_id"]
    return web.Response(
        text=dashboard.render_alerts(
            session,
            await database.get_user_notifications(user_id),
            await database.get_user_preferences(user_id),
            session.get("csrf_token") or "",
            saved=request.query.get("ok") == "1",
        ),
        content_type="text/html",
    )


async def handle_alerts_save(request: web.Request) -> web.Response:
    session = await _session_of(request)
    _require_login(session)
    await _check_csrf(request, session)

    data = await request.post()
    user_id = session["user_id"]

    for event in config.USER_NOTIFICATION_EVENT_LABELS:
        await database.set_user_notification(user_id, event, f"event_{event}" in data)

    # On ne touche qu'aux types d'offres : le reste des préférences (genres,
    # prix minimum, fuseau) continue d'être géré par /preferences sur Discord.
    current = await database.get_user_preferences(user_id)
    offer_types = [key for key in config.OFFER_TYPE_KEYS if f"type_{key}" in data]
    await database.set_user_preferences(
        user_id,
        offer_types=offer_types or ["game"],
        min_worth_eur=current.get("min_worth_eur"),
        genres=current.get("genres"),
        timezone=current.get("timezone"),
    )

    raise web.HTTPFound("/alertes?ok=1")


# ---------- Compte ----------


async def handle_account(request: web.Request) -> web.Response:
    session = await _session_of(request)
    _require_login(session)
    summary = await database.count_user_data(session["user_id"])
    return web.Response(
        text=dashboard.render_account(session, summary, session.get("csrf_token") or ""),
        content_type="text/html",
    )


async def handle_account_delete(request: web.Request) -> web.Response:
    session = await _session_of(request)
    _require_login(session)
    await _check_csrf(request, session)

    await database.delete_user_data(session["user_id"])
    response = web.HTTPFound("/")
    response.del_cookie(dashboard.SESSION_COOKIE)
    raise response


# ---------- Connexion Discord ----------


async def handle_login(request: web.Request) -> web.Response:
    state, url = await dashboard.start_login(request.app[BOT_KEY])
    response = web.HTTPFound(url)
    response.set_cookie(
        STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        samesite="Lax",
        secure=config.DASHBOARD_COOKIE_SECURE,
    )
    raise response


async def handle_callback(request: web.Request) -> web.Response:
    code = request.query.get("code")
    state = request.query.get("state")
    expected_state = request.cookies.get(STATE_COOKIE)

    if not code or not state or not expected_state or state != expected_state:
        return web.Response(
            text=dashboard.render_error("Connexion refusée : jeton de sécurité invalide ou expiré."),
            content_type="text/html",
            status=400,
        )

    result = await dashboard.complete_login(code)
    if result is None:
        return web.Response(
            text=dashboard.render_error("Impossible de terminer la connexion avec Discord."),
            content_type="text/html",
            status=502,
        )

    response = web.HTTPFound("/serveurs")
    response.del_cookie(STATE_COOKIE)
    response.set_cookie(
        dashboard.SESSION_COOKIE,
        result["session_id"],
        max_age=dashboard.SESSION_DURATION_HOURS * 3600,
        httponly=True,
        samesite="Lax",
        secure=config.DASHBOARD_COOKIE_SECURE,
    )
    raise response


async def handle_logout(request: web.Request) -> web.Response:
    session_id = request.cookies.get(dashboard.SESSION_COOKIE)
    if session_id:
        await database.delete_dashboard_session(session_id)
    response = web.HTTPFound("/")
    response.del_cookie(dashboard.SESSION_COOKIE)
    raise response


def create_app(bot) -> web.Application:
    app = web.Application()
    app[BOT_KEY] = bot
    app.router.add_get("/", handle_home)
    app.router.add_get("/api/stats", handle_api_stats)
    app.router.add_get("/offres", handle_offers)
    app.router.add_get("/serveurs", handle_guilds)
    app.router.add_get("/serveurs/{guild_id}", handle_guild_config)
    app.router.add_post("/serveurs/{guild_id}", handle_guild_config_save)
    app.router.add_get("/alertes", handle_alerts)
    app.router.add_post("/alertes", handle_alerts_save)
    app.router.add_get("/compte", handle_account)
    app.router.add_post("/compte/supprimer", handle_account_delete)
    app.router.add_get("/login", handle_login)
    app.router.add_get("/auth/callback", handle_callback)
    app.router.add_get("/logout", handle_logout)
    return app


async def start_dashboard(bot) -> web.AppRunner:
    """Démarre le serveur HTTP en tâche de fond ; retourne le runner pour pouvoir l'arrêter."""
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.DASHBOARD_HOST, config.DASHBOARD_PORT)
    await site.start()
    log.info("Tableau de bord web démarré sur %s:%s", config.DASHBOARD_HOST, config.DASHBOARD_PORT)
    return runner


async def stop_dashboard(runner: web.AppRunner) -> None:
    await runner.cleanup()

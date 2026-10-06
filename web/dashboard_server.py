"""Serveur HTTP du tableau de bord (aiohttp.web), lancé en option à côté du bot."""

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


async def handle_home(request: web.Request) -> web.Response:
    bot = request.app[BOT_KEY]
    session = await dashboard.current_session(request.cookies.get(dashboard.SESSION_COOKIE))
    stats = await metrics.build_dev_stats(bot) if bot is not None else await database.get_giveaway_stats()
    user = {"username": session["username"]} if session else None
    return web.Response(text=dashboard.render_home(stats, user), content_type="text/html")


async def handle_api_stats(request: web.Request) -> web.Response:
    bot = request.app[BOT_KEY]
    stats = await metrics.build_dev_stats(bot) if bot is not None else await database.get_giveaway_stats()
    return web.json_response(stats)


async def handle_login(request: web.Request) -> web.Response:
    state, url = await dashboard.start_login(request.app[BOT_KEY])
    response = web.HTTPFound(url)
    response.set_cookie(STATE_COOKIE, state, max_age=600, httponly=True, samesite="Lax")
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

    response = web.HTTPFound("/")
    response.del_cookie(STATE_COOKIE)
    response.set_cookie(
        dashboard.SESSION_COOKIE,
        result["session_id"],
        max_age=dashboard.SESSION_DURATION_HOURS * 3600,
        httponly=True,
        samesite="Lax",
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

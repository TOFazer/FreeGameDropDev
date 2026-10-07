"""Alertes DM personnelles et rappels serveur, indépendants des annonces publiques.

Ce module ne contient que la logique (qui doit recevoir quoi) : l'envoi
effectif passe par l'objet `bot` fourni par le cog pour rester testable
sans connexion Discord réelle.
"""

from __future__ import annotations

import logging

import config
import database
from utils import rate_limits
from utils.embeds import build_game_message
from utils.logging_setup import log_event
from utils.offers import offer_matches_preferences, parse_end_datetime

log = logging.getLogger(__name__)


async def notify_new_offers(bot, games: list[dict]) -> int:
    """Alerte en DM les membres abonnés à « new_offer » dont les préférences correspondent."""
    if not games:
        return 0

    user_ids = await database.get_users_subscribed("new_offer")
    if not user_ids:
        return 0

    sent = 0
    for user_id in user_ids:
        preferences = await database.get_user_preferences(user_id)
        for game in games:
            item_id = str(game.get("id"))
            if not offer_matches_preferences(game, preferences):
                continue
            if await database.was_alert_sent_recently(
                user_id, item_id, "new_offer", config.ALERT_CADENCE_HOURS
            ):
                continue
            if await _send_dm(bot, user_id, game):
                await database.record_alert_sent(user_id, item_id, "new_offer")
                sent += 1
                log_event("alert.sent", event="new_offer", user_id=user_id, offer_id=item_id)
    return sent


async def notify_ending_soon(bot, games: list[dict]) -> int:
    """Alerte en DM les membres abonnés à « ending_soon » pour leurs favoris qui expirent."""
    candidates = [g for g in games if parse_end_datetime(g.get("end_date")) is not None]
    if not candidates:
        return 0

    user_ids = await database.get_users_subscribed("ending_soon")
    if not user_ids:
        return 0

    sent = 0
    for user_id in user_ids:
        favorite_ids = await database.get_favorite_ids(user_id)
        if not favorite_ids:
            continue
        for game in candidates:
            item_id = str(game.get("id"))
            if item_id not in favorite_ids:
                continue
            if await database.was_alert_sent_recently(
                user_id, item_id, "ending_soon", config.ALERT_CADENCE_HOURS
            ):
                continue
            if await _send_dm(bot, user_id, game, reminder=True):
                await database.record_alert_sent(user_id, item_id, "ending_soon")
                sent += 1
                log_event("alert.sent", event="ending_soon", user_id=user_id, offer_id=item_id)
    return sent


async def _send_dm(bot, user_id: int, game: dict, *, reminder: bool = False) -> bool:
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
    except Exception:
        log.warning("Impossible de retrouver le membre %s pour une alerte", user_id)
        return False
    if user is None:
        return False

    embed, view = build_game_message(game)
    if reminder:
        content = "⏳ Un de tes favoris se termine bientôt !"
    else:
        content = "🆕 Une offre correspond à tes préférences !"
    try:
        await rate_limits.spaced_send(
            user.send, key=f"dm:{user_id}", content=content, embed=embed, view=view
        )
        return True
    except Exception:
        log.info("Impossible d'envoyer une alerte DM à %s (DMs fermés ?)", user_id)
        log_event("alert.failed", level=logging.INFO, user_id=user_id, offer_id=game.get("id"))
        return False


async def send_guild_reminders(bot, games: list[dict], *, now=None) -> int:
    """Poste un rappel « se termine aujourd'hui » dans le salon configuré par serveur."""
    from utils.offers import filter_offers

    channels = await database.get_all_guild_reminder_channels()
    if not channels:
        return 0

    ending_today = filter_offers(games, period="ends_today", now=now)
    if not ending_today:
        return 0

    sent = 0
    for guild_id, channel_id in channels.items():
        channel = bot.get_channel(channel_id)
        if channel is None:
            continue
        for game in ending_today:
            item_id = f"reminder:{game.get('id')}"
            if await database.is_sent(guild_id, item_id):
                continue
            embed, view = build_game_message(game)
            try:
                await rate_limits.spaced_send(
                    channel.send,
                    key=f"channel:{channel_id}",
                    content="📅 Dernier jour pour récupérer cette offre !",
                    embed=embed,
                    view=view,
                )
                await database.mark_sent(guild_id, item_id)
                sent += 1
                log_event("reminder.sent", guild_id=guild_id, offer_id=game.get("id"))
            except Exception:
                log.warning("Impossible d'envoyer le rappel sur le serveur %s", guild_id)
    return sent

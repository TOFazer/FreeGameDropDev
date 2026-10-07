"""Historique du catalogue, préférences, alertes et sessions du tableau de bord."""


async def test_historique_recent_filtre_par_plateforme_et_type(db):
    await db.save_giveaways(
        [
            {
                "id": 1,
                "title": "Jeu Steam",
                "platforms": "PC (Steam)",
                "type": "game",
                "source": "gamerpower",
            },
            {
                "id": "epic:2",
                "title": "Jeu Epic",
                "platforms": "Epic Games Store",
                "type": "game",
                "source": "epic",
            },
            {
                "id": 3,
                "title": "DLC Steam",
                "platforms": "PC (Steam)",
                "type": "dlc",
                "source": "gamerpower",
            },
        ]
    )

    recent = await db.get_recent_giveaways(limit=10)
    assert [g["id"] for g in recent] == ["3", "epic:2", "1"]

    steam_only = await db.get_recent_giveaways(platform="Steam")
    assert {g["id"] for g in steam_only} == {"1", "3"}

    dlc_only = await db.get_recent_giveaways(offer_type="dlc")
    assert [g["id"] for g in dlc_only] == ["3"]

    epic_only = await db.get_recent_giveaways(source="epic")
    assert [g["id"] for g in epic_only] == ["epic:2"]


async def test_recherche_plein_texte(db):
    await db.save_giveaways(
        [
            {"id": 1, "title": "Super Jeu de rôle", "description": "Une aventure épique"},
            {"id": 2, "title": "Autre titre", "description": "Rien à voir"},
        ]
    )

    resultats = await db.search_giveaways("épique")
    assert [g["id"] for g in resultats] == ["1"]

    resultats = await db.search_giveaways("super")
    assert [g["id"] for g in resultats] == ["1"]

    assert await db.search_giveaways("") == []
    assert await db.search_giveaways("introuvable") == []


async def test_genres_conserves_et_restitues(db):
    await db.save_giveaways([{"id": 1, "title": "Jeu", "genres": ["rpg", "action"]}])

    recent = await db.get_recent_giveaways()
    assert sorted(recent[0]["genres"]) == ["action", "rpg"]


async def test_statistiques_globales(db):
    await db.save_giveaways(
        [
            {"id": 1, "title": "Jeu A", "source": "gamerpower", "type": "game"},
            {"id": "epic:1", "title": "Jeu B", "source": "epic", "type": "game"},
        ]
    )
    await db.toggle_favorite(42, "1")
    await db.set_platform_channel(7, "steam", 10)

    stats = await db.get_giveaway_stats()

    assert stats["total_offers"] == 2
    assert stats["offers_by_source"] == {"gamerpower": 1, "epic": 1}
    assert stats["offers_by_type"] == {"game": 2}
    assert stats["offers_last_30_days"] == 2
    assert stats["total_favorites"] == 1
    assert stats["members_with_favorites"] == 1
    assert stats["configured_guilds"] == 1


async def test_preferences_par_defaut_puis_personnalisees(db):
    defaults = await db.get_user_preferences(42)
    assert defaults == {
        "offer_types": ["game"],
        "min_worth_eur": None,
        "genres": [],
        "timezone": "",
        "platforms": [],
    }

    await db.set_user_preferences(
        42,
        offer_types=["game", "dlc"],
        min_worth_eur=10.0,
        genres=["rpg"],
        timezone="Europe/Paris",
        platforms=["steam", "epic"],
    )

    preferences = await db.get_user_preferences(42)
    assert preferences == {
        "offer_types": ["game", "dlc"],
        "min_worth_eur": 10.0,
        "genres": ["rpg"],
        "timezone": "Europe/Paris",
        "platforms": ["steam", "epic"],
    }


async def test_preferences_plateformes_vides_retiennent_toutes_les_offres(db):
    """Une liste vide signifie « toutes les plateformes », comme pour les genres."""

    await db.set_user_preferences(42, offer_types=["game"], platforms=[])

    preferences = await db.get_user_preferences(42)
    assert preferences["platforms"] == []


async def test_notifications_personnelles(db):
    assert await db.get_user_notifications(42) == {}
    assert await db.get_users_subscribed("new_offer") == []

    await db.set_user_notification(42, "new_offer", True)
    await db.set_user_notification(42, "ending_soon", False)
    await db.set_user_notification(43, "new_offer", True)

    assert await db.get_user_notifications(42) == {"new_offer": True, "ending_soon": False}
    assert sorted(await db.get_users_subscribed("new_offer")) == [42, 43]

    await db.set_user_notification(42, "new_offer", False)
    assert await db.get_users_subscribed("new_offer") == [43]


async def test_cadence_des_alertes(db):
    assert await db.was_alert_sent_recently(42, "1", "new_offer", within_hours=1) is False

    await db.record_alert_sent(42, "1", "new_offer")

    assert await db.was_alert_sent_recently(42, "1", "new_offer", within_hours=1) is True
    assert await db.was_alert_sent_recently(42, "1", "ending_soon", within_hours=1) is False
    assert await db.was_alert_sent_recently(42, "2", "new_offer", within_hours=1) is False


async def test_salon_de_rappel_serveur(db):
    assert await db.get_guild_reminder_channel(7) is None

    await db.set_guild_reminder_channel(7, 100)
    await db.set_guild_reminder_channel(7, 200)

    assert await db.get_guild_reminder_channel(7) == 200
    assert await db.get_all_guild_reminder_channels() == {7: 200}


async def test_sessions_du_tableau_de_bord(db):
    from datetime import datetime, timedelta, timezone

    fmt = "%Y-%m-%d %H:%M:%S"
    futur = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(fmt)
    passe = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(fmt)

    await db.create_dashboard_session("tok1", 42, "Alice", "avatar.png", futur)
    await db.create_dashboard_session("tok2", 43, "Bob", "", passe)

    session = await db.get_dashboard_session("tok1")
    assert session["user_id"] == 42
    assert session["username"] == "Alice"

    assert await db.get_dashboard_session("tok2") is None  # expirée
    assert await db.get_dashboard_session("inconnue") is None

    await db.delete_dashboard_session("tok1")
    assert await db.get_dashboard_session("tok1") is None


async def test_purge_des_sessions_expirees(db):
    from datetime import datetime, timedelta, timezone

    fmt = "%Y-%m-%d %H:%M:%S"
    futur = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(fmt)
    passe = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(fmt)

    await db.create_dashboard_session("tok1", 42, "Alice", "", futur)
    await db.create_dashboard_session("tok2", 43, "Bob", "", passe)

    await db.purge_expired_sessions()

    assert await db.get_dashboard_session("tok1") is not None
    async with __import__("aiosqlite").connect(db.DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM dashboard_sessions") as cursor:
            (count,) = await cursor.fetchone()
    assert count == 1

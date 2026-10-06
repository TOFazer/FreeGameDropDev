"""Alertes DM personnelles et rappels serveur."""

from utils import notifications

GAME = {
    "id": 1,
    "title": "Jeu gratuit",
    "platforms": "PC (Steam)",
    "offer_type": "game",
    "genres": [],
    "end_date": "",
}


class FakeUser:
    def __init__(self, user_id, fails=False):
        self.id = user_id
        self.fails = fails
        self.sent = []

    async def send(self, **kwargs):
        if self.fails:
            raise RuntimeError("DMs fermés")
        self.sent.append(kwargs)


class FakeBot:
    def __init__(self, users=None, channels=None):
        self.users = users or {}
        self.channels = channels or {}

    def get_user(self, user_id):
        return self.users.get(user_id)

    async def fetch_user(self, user_id):
        return self.users.get(user_id)

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


async def test_alerte_nouvelle_offre_envoyee_aux_abonnes(db):
    alice = FakeUser(42)
    bot = FakeBot(users={42: alice})
    await db.set_user_notification(42, "new_offer", True)

    sent = await notifications.notify_new_offers(bot, [GAME])

    assert sent == 1
    assert len(alice.sent) == 1
    assert await db.was_alert_sent_recently(42, "1", "new_offer", within_hours=1) is True


async def test_alerte_nouvelle_offre_respecte_la_cadence(db):
    alice = FakeUser(42)
    bot = FakeBot(users={42: alice})
    await db.set_user_notification(42, "new_offer", True)

    await notifications.notify_new_offers(bot, [GAME])
    sent = await notifications.notify_new_offers(bot, [GAME])

    assert sent == 0
    assert len(alice.sent) == 1


async def test_alerte_nouvelle_offre_respecte_les_preferences(db):
    alice = FakeUser(42)
    bot = FakeBot(users={42: alice})
    await db.set_user_notification(42, "new_offer", True)
    await db.set_user_preferences(42, offer_types=["dlc"])

    sent = await notifications.notify_new_offers(bot, [GAME])

    assert sent == 0
    assert alice.sent == []


async def test_aucun_abonne_ne_fait_rien(db):
    bot = FakeBot()

    assert await notifications.notify_new_offers(bot, [GAME]) == 0


async def test_dm_impossible_nest_pas_compte_comme_envoye(db):
    alice = FakeUser(42, fails=True)
    bot = FakeBot(users={42: alice})
    await db.set_user_notification(42, "new_offer", True)

    sent = await notifications.notify_new_offers(bot, [GAME])

    assert sent == 0
    assert await db.was_alert_sent_recently(42, "1", "new_offer", within_hours=1) is False


async def test_alerte_fin_proche_uniquement_pour_les_favoris(db):
    alice = FakeUser(42)
    bot = FakeBot(users={42: alice})
    await db.set_user_notification(42, "ending_soon", True)
    jeu_expirant = {**GAME, "end_date": "2026-10-10 10:00:00"}

    sent = await notifications.notify_ending_soon(bot, [jeu_expirant])
    assert sent == 0  # pas encore en favori

    await db.toggle_favorite(42, "1")
    sent = await notifications.notify_ending_soon(bot, [jeu_expirant])

    assert sent == 1
    assert len(alice.sent) == 1


async def test_rappels_serveur_se_terminant_aujourdhui(db):
    import datetime as dt

    channel = FakeChannel()
    bot = FakeBot(channels={100: channel})
    await db.set_guild_reminder_channel(7, 100)

    now = dt.datetime(2026, 6, 15, 10, 0, tzinfo=dt.timezone.utc)
    jeu = {**GAME, "end_date": "2026-06-15 18:00:00"}

    sent = await notifications.send_guild_reminders(bot, [jeu], now=now)

    assert sent == 1
    assert len(channel.sent) == 1

    sent_again = await notifications.send_guild_reminders(bot, [jeu], now=now)
    assert sent_again == 0  # pas de doublon

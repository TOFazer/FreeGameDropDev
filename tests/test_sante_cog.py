"""Commande /sante et envoi des alertes de surveillance."""

from types import SimpleNamespace

import config
from cogs.sante import Sante
from utils import monitoring


def _jeton_factice():
    """Voir tests/test_logging_setup.py : forme de jeton, sans en écrire un en clair."""
    return "M" + "a" * 23 + "." + "b" * 6 + "." + "c" * 28


FAUX_TOKEN = _jeton_factice()


class FakeResponse:
    def __init__(self):
        self.sent = None

    def is_done(self):
        return False

    async def send_message(self, *args, **kwargs):
        self.sent = (args, kwargs)


class FakeInteraction:
    def __init__(self, user_id=42, guild_id=7):
        self.user = SimpleNamespace(id=user_id)
        self.guild_id = guild_id
        self.response = FakeResponse()


def _cog(bot=None):
    instance = Sante.__new__(Sante)
    instance.bot = bot
    instance.alert_book = monitoring.AlertBook(30.0)
    return instance


class FakeUser:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class FakeTextChannel:
    def __init__(self, channel_id=123):
        self.id = channel_id
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


async def test_sante_repond_en_prive_avec_un_rapport_mesure(db):
    monitoring.HEALTH.record_source_success("epic", latency_ms=50, offers=1)
    interaction = FakeInteraction()

    await Sante.sante.callback(_cog(), interaction)

    args, kwargs = interaction.response.sent
    assert kwargs["ephemeral"] is True
    assert args[0].startswith("```")
    assert "FreeGameDrop" in args[0]
    assert "epic" in args[0]
    assert "Base de données" in args[0]


async def test_sante_ne_divulgue_aucun_secret(db, monkeypatch):
    monkeypatch.setattr(config, "DISCORD_TOKEN", FAUX_TOKEN)
    interaction = FakeInteraction()

    await Sante.sante.callback(_cog(), interaction)

    texte = interaction.response.sent[0][0]
    assert config.DISCORD_TOKEN not in texte


async def test_une_alerte_part_dans_le_salon_configure(monkeypatch):
    channel = FakeTextChannel()
    monkeypatch.setattr(config, "MONITOR_ALERT_CHANNEL_ID", channel.id)
    bot = SimpleNamespace(get_channel=lambda channel_id: channel if channel_id == channel.id else None)
    alerte = monitoring.Alert("source:epic", "critical", "🚨 Source « epic » indisponible.")

    envoye = await _cog(bot).send_alert(alerte)

    assert envoye is True
    assert "surveillance" in channel.sent[0]["content"]
    assert "epic" in channel.sent[0]["content"]


async def test_sans_salon_lalerte_part_en_prive_au_proprietaire(monkeypatch):
    user = FakeUser()
    monkeypatch.setattr(config, "MONITOR_ALERT_CHANNEL_ID", None)
    monkeypatch.setattr(config, "MONITOR_OWNER_ID", 999)
    bot = SimpleNamespace(get_user=lambda user_id: user if user_id == 999 else None)
    alerte = monitoring.Alert("database", "critical", "🚨 La base de données ne répond plus.")

    assert await _cog(bot).send_alert(alerte) is True

    assert user.sent and "base de données" in user.sent[0]["content"]


async def test_sans_destinataire_lalerte_reste_dans_le_journal(monkeypatch, caplog):
    monkeypatch.setattr(config, "MONITOR_ALERT_CHANNEL_ID", None)
    monkeypatch.setattr(config, "MONITOR_OWNER_ID", None)

    async def refus():
        raise RuntimeError("API Discord injoignable")

    bot = SimpleNamespace(application_info=refus)
    alerte = monitoring.Alert("discord", "critical", "🚨 Connexion Discord perdue.")

    assert await _cog(bot).send_alert(alerte) is False


async def test_un_salon_introuvable_retombe_sur_le_proprietaire(monkeypatch):
    user = FakeUser()
    monkeypatch.setattr(config, "MONITOR_ALERT_CHANNEL_ID", 404)
    monkeypatch.setattr(config, "MONITOR_OWNER_ID", 1)
    bot = SimpleNamespace(get_channel=lambda channel_id: None, get_user=lambda user_id: user)
    alerte = monitoring.Alert("errors", "critical", "🚨 Pic d'erreurs.")

    assert await _cog(bot).send_alert(alerte) is True
    assert user.sent

"""Commande /info et lien d'invitation."""

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import discord

import config
from cogs.setup import build_info_embed


def test_info_affiche_latence_serveurs_et_liens(monkeypatch):
    monkeypatch.setattr(config, "PROJECT_URL", "https://example.com/project")
    monkeypatch.setattr(config, "SUPPORT_URL", "https://example.com/support")
    monkeypatch.setattr(config, "VOTE_URL", "https://example.com/vote")
    bot = SimpleNamespace(
        latency=0.012,
        guilds=[object(), object()],
        user=SimpleNamespace(id=123456),
    )

    embed = build_info_embed(bot)
    fields = {field.name: field.value for field in embed.fields}

    assert fields["Latence"] == "12 ms"
    assert fields["Serveurs"] == "2"
    assert "https://example.com/project" in fields["Liens utiles"]
    assert "https://example.com/support" in fields["Liens utiles"]
    assert "https://example.com/vote" in fields["Liens utiles"]


def test_info_naffiche_pas_un_lien_de_vote_vide(monkeypatch):
    monkeypatch.setattr(config, "PROJECT_URL", "")
    monkeypatch.setattr(config, "SUPPORT_URL", "")
    monkeypatch.setattr(config, "VOTE_URL", "")
    bot = SimpleNamespace(latency=float("inf"), guilds=[], user=None)

    embed = build_info_embed(bot)
    fields = {field.name: field.value for field in embed.fields}

    assert fields["Latence"] == "indisponible"
    assert fields["Liens utiles"] == "Aucun lien configuré."


def test_lien_dinvitation_ne_demande_pas_administrator():
    bot = SimpleNamespace(latency=0, guilds=[], user=SimpleNamespace(id=123))

    embed = build_info_embed(bot)
    invite = embed.fields[-1].value.split(")", 1)[0].split("(", 1)[1]
    params = parse_qs(urlparse(invite).query)
    permissions = discord.Permissions(int(params["permissions"][0]))

    assert not permissions.administrator
    assert permissions.manage_channels
    assert permissions.manage_roles
    assert permissions.send_messages


def test_info_affiche_lenvironnement_de_developpement(monkeypatch):
    """En DEV, `/info` doit dire clairement où l'on se trouve."""
    monkeypatch.setattr(config, "ENVIRONMENT", "development")
    monkeypatch.setattr(config, "DB_PATH", "data/freegamedrop-dev.db")
    bot = SimpleNamespace(latency=0.042, guilds=[object()], user=SimpleNamespace(id=123))

    embed = build_info_embed(bot)
    fields = {field.name: field.value for field in embed.fields}

    assert "🧪" in embed.title and "DEV" in embed.title
    assert fields["Environnement"] == "🧪 Development"
    assert fields["Latence"] == "42 ms"
    assert fields["Serveurs"] == "1"
    assert fields["Base de données"] == "SQLite · freegamedrop-dev.db"
    assert "🔧 Maintenance" not in fields
    assert "dev" in (embed.footer.text or "").lower()


def test_info_en_production_ne_parle_pas_de_developpement(monkeypatch):
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setattr(config, "DB_PATH", "bot.db")
    bot = SimpleNamespace(latency=0.05, guilds=[], user=SimpleNamespace(id=123))

    embed = build_info_embed(bot)
    fields = {field.name: field.value for field in embed.fields}

    assert embed.title == "🚀 FreeGameDrop"
    assert fields["Environnement"] == "🚀 Production"
    assert fields["Base de données"] == "SQLite"
    assert "dev" not in embed.title.lower()


def test_info_signale_le_mode_maintenance(monkeypatch):
    monkeypatch.setattr(config, "MAINTENANCE_MODE", True)
    bot = SimpleNamespace(latency=0.01, guilds=[], user=None)

    embed = build_info_embed(bot)
    fields = {field.name: field.value for field in embed.fields}

    assert "🔧 Maintenance" in fields
    assert "maintenance" in fields["🔧 Maintenance"].lower()

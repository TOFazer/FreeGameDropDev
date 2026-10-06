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

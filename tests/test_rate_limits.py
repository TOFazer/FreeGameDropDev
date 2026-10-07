"""Limites de débit : invisibles pour un usage normal, efficaces contre l'abus."""

import asyncio
import time
from types import SimpleNamespace

import discord
import pytest

import config
from cogs.jeux import Jeux
from utils import rate_limits

UTILISATEUR = SimpleNamespace(id=42)
AUTRE_UTILISATEUR = SimpleNamespace(id=99)
SERVEUR = SimpleNamespace(user=UTILISATEUR, guild_id=7)
AUTRE_SERVEUR = SimpleNamespace(user=UTILISATEUR, guild_id=8)


def _interaction(user_id=42, guild_id=7):
    return SimpleNamespace(user=SimpleNamespace(id=user_id), guild_id=guild_id)


# ---------- Fenêtre glissante ----------


def test_un_usage_normal_ne_rencontre_jamais_la_limite():
    limite = rate_limits.LIMITS["recherche"]

    decisions = [rate_limits.consume(limite, UTILISATEUR.id) for _ in range(limite.max_hits)]

    assert all(decision.allowed for decision in decisions)
    assert decisions[-1].remaining == 0


def test_labus_est_refuse_avec_un_delai_a_attendre():
    limite = rate_limits.LIMITS["recherche"]
    for _ in range(limite.max_hits):
        rate_limits.consume(limite, UTILISATEUR.id)

    decision = rate_limits.consume(limite, UTILISATEUR.id)

    assert decision.allowed is False
    assert 0 < decision.retry_after <= limite.window_seconds


def test_chaque_membre_a_son_propre_quota():
    limite = rate_limits.LIMITS["recherche"]
    for _ in range(limite.max_hits):
        rate_limits.consume(limite, UTILISATEUR.id)

    assert rate_limits.consume(limite, AUTRE_UTILISATEUR.id).allowed is True


def test_la_fenetre_se_vide_avec_le_temps():
    limite = rate_limits.Limit("test", 2, 60.0, rate_limits.SCOPE_USER, "/test")
    limiteur = rate_limits.SlidingWindowLimiter(clock=lambda: 0.0)
    limiteur.hit("test:1", limite, now=0.0)
    limiteur.hit("test:1", limite, now=1.0)
    assert limiteur.hit("test:1", limite, now=2.0).allowed is False

    decision = limiteur.hit("test:1", limite, now=61.0)

    assert decision.allowed is True


def test_les_cles_inactives_sont_oubliees():
    limite = rate_limits.Limit("test", 1, 1.0, rate_limits.SCOPE_USER, "/test")
    limiteur = rate_limits.SlidingWindowLimiter(clock=lambda: 0.0)
    limiteur.hit("test:1", limite, now=0.0)

    limiteur._sweep(0.0)
    limiteur.hit("test:2", limite, now=rate_limits.SWEEP_SECONDS + 1)
    limiteur._sweep(rate_limits.SWEEP_SECONDS + 1)

    assert "test:1" not in limiteur._hits


# ---------- Portées : membre et serveur ----------


def test_le_plafond_global_protege_contre_le_cumul_de_commandes():
    plafond = rate_limits.LIMITS["user_commands"]
    commandes = ["recherche", "historique", "favoris", "stats", "ping"]

    refus = None
    for index in range(plafond.max_hits * 2):
        nom = commandes[index % len(commandes)]
        decision = rate_limits.consume_command(nom, _interaction())
        if not decision.allowed:
            refus = decision
            break

    assert refus is not None
    assert refus.retry_after > 0


def test_les_actions_administratives_sont_limitees_par_serveur():
    limite = rate_limits.LIMITS["admin"]
    for _ in range(limite.max_hits):
        assert rate_limits.consume(limite, SERVEUR.guild_id).allowed is True

    assert rate_limits.consume(limite, SERVEUR.guild_id).allowed is False
    assert rate_limits.consume(limite, AUTRE_SERVEUR.guild_id).allowed is True


def test_le_message_explique_la_limite_sans_etre_desagreable():
    limite = rate_limits.LIMITS["free"]
    message = rate_limits.format_limit_message(limite, 20.0)

    assert "Réessaie dans" in message
    assert "/free" in message
    assert rate_limits.format_delay(0.2) == "1 s"
    assert rate_limits.format_delay(90) == "2 min"
    assert rate_limits.format_delay(7200) == "2 h"


# ---------- Intégration aux commandes ----------


async def test_la_commande_free_est_protegee_par_le_limiteur():
    check = Jeux.free.checks[0]
    limite = rate_limits.LIMITS["free"]
    interaction = _interaction()

    for _ in range(limite.max_hits):
        assert await check(interaction) is True

    with pytest.raises(rate_limits.RateLimited) as refus:
        await check(interaction)

    assert refus.value.limit.name == "free"
    assert "Réessaie dans" in str(refus.value)


async def test_les_commandes_administratives_sont_limitees_par_serveur():
    check = Jeux.setup_auto.checks[1]  # après le contrôle de permission
    limite = rate_limits.LIMITS["admin"]
    for _ in range(limite.max_hits):
        await check(_interaction(user_id=1))

    with pytest.raises(rate_limits.RateLimited):
        await check(_interaction(user_id=2))  # autre admin, même serveur

    assert await check(_interaction(user_id=1, guild_id=8)) is True


def test_la_commande_de_test_est_fortement_limitee():
    limite = rate_limits.LIMITS["admin_heavy"]

    assert limite.scope == rate_limits.SCOPE_GUILD
    assert limite.window_seconds >= 300
    assert limite.max_hits <= 3


def test_les_limites_par_defaut_sont_raisonnables():
    for limite in rate_limits.LIMITS.values():
        assert limite.max_hits >= 1
        assert limite.window_seconds > 0
        assert limite.scope in {rate_limits.SCOPE_USER, rate_limits.SCOPE_GUILD}


# ---------- Envois sortants (limites Discord) ----------


async def test_les_envois_dun_meme_salon_sont_espaces():
    throttle = rate_limits.OutboundThrottle(0.05)
    envois = []

    async def send(**kwargs):
        envois.append(time.monotonic())

    await rate_limits.spaced_send(send, key="channel:1", throttle=throttle, content="a")
    await rate_limits.spaced_send(send, key="channel:1", throttle=throttle, content="b")

    assert len(envois) == 2
    assert envois[1] - envois[0] >= 0.04


async def test_les_envois_de_salons_differents_ne_sattendent_pas():
    throttle = rate_limits.OutboundThrottle(0.2)
    envois = []

    async def send(**kwargs):
        envois.append(time.monotonic())

    await asyncio.gather(
        rate_limits.spaced_send(send, key="channel:1", throttle=throttle),
        rate_limits.spaced_send(send, key="channel:2", throttle=throttle),
    )

    assert abs(envois[1] - envois[0]) < 0.1


async def test_un_429_est_reessaye_une_seule_fois(caplog):
    appels = []

    async def send(**kwargs):
        appels.append(kwargs)
        if len(appels) == 1:
            raise discord.HTTPException(
                SimpleNamespace(status=429, reason="Too Many Requests", headers={"Retry-After": "0.01"}),
                "rate limited",
            )
        return "ok"

    resultat = await rate_limits.spaced_send(
        send, key="channel:1", throttle=rate_limits.OutboundThrottle(0.0)
    )

    assert resultat == "ok"
    assert len(appels) == 2
    assert "event=discord.rate_limited" in caplog.text


async def test_une_erreur_discord_normale_nest_pas_reessayee():
    async def send(**kwargs):
        raise discord.HTTPException(
            SimpleNamespace(status=500, reason="Server Error", headers={}), "boom"
        )

    with pytest.raises(discord.HTTPException):
        await rate_limits.spaced_send(send, key="channel:1", throttle=rate_limits.OutboundThrottle(0.0))


def test_un_429_tres_long_ne_bloque_pas_le_cycle():
    erreur = discord.HTTPException(
        SimpleNamespace(status=429, reason="Too Many Requests", headers={"Retry-After": "120"}),
        "rate limited",
    )

    assert rate_limits.retry_after_of(erreur) == 120
    assert rate_limits.retry_after_of(
        discord.HTTPException(SimpleNamespace(status=500, reason="Server Error", headers={}), "boom")
    ) is None


def test_les_valeurs_par_defaut_viennent_de_la_configuration():
    assert rate_limits.LIMITS["free"].max_hits == max(1, config.RATE_LIMIT_FREE_PER_MINUTE)
    assert rate_limits.LIMITS["admin"].max_hits == max(1, config.RATE_LIMIT_ADMIN_PER_MINUTE)

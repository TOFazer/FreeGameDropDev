"""Fiabilité des sources : panne isolée, cache partagé, et surtout zéro faux positif."""

import asyncio
import logging

import pytest

import config
from services import epic_games, gamerpower, offer_engine
from utils import monitoring

GAME = {"id": 1, "title": "Jeu GamerPower", "type": "game"}
EPIC_GAME = {"id": "epic:1", "title": "Jeu Epic", "type": "game", "source": "epic"}


async def _ok(games):
    return games


async def _boom():
    raise RuntimeError("panne réseau")


async def _slow():
    await asyncio.sleep(10)
    return [GAME]


@pytest.fixture(autouse=True)
def sources(monkeypatch):
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower", "epic"))
    monkeypatch.setattr(config, "OFFER_SOURCE_TIMEOUT", 0.05)
    monkeypatch.setattr(config, "OFFER_CACHE_SECONDS", 60.0)


# ---------- Pas de faux positifs ----------


def test_une_offre_sans_titre_ou_sans_identifiant_est_refusee():
    assert offer_engine.reject_reason({}) == "identifiant manquant"
    assert offer_engine.reject_reason({"id": 1}) == "titre manquant"
    assert offer_engine.reject_reason({"id": 1, "title": "Jeu"}) is None


def test_une_offre_signalee_non_active_par_la_source_est_refusee():
    motif = offer_engine.reject_reason(
        {"id": 1, "title": "Jeu", "free_verified": False}
    )

    assert motif is not None
    assert "plus active" in motif


def test_une_offre_terminee_nest_jamais_annoncee():
    motif = offer_engine.reject_reason(
        {"id": 1, "title": "Jeu", "end_date": "2020-01-01 12:00:00"}
    )
    assert motif == "offre déjà terminée"


def test_une_offre_sans_date_reste_eligible():
    assert offer_engine.reject_reason({"id": 1, "title": "Jeu", "end_date": "N/A"}) is None


def test_un_lien_de_recuperation_invalide_est_refuse():
    motif = offer_engine.reject_reason(
        {"id": 1, "title": "Jeu", "open_giveaway_url": "javascript:alert(1)"}
    )
    assert motif == "lien de récupération invalide"


async def test_une_offre_expiree_est_ecartee_du_flux(monkeypatch):
    monkeypatch.setitem(
        offer_engine.SOURCES,
        "gamerpower",
        lambda: _ok([{"id": 9, "title": "Vieux jeu", "end_date": "2020-01-01 00:00:00"}]),
    )

    assert await offer_engine.fetch_offers(sources=["gamerpower"]) == []


def test_gamerpower_marque_les_statuts():
    jeux = [{"status": "Active"}, {"status": "Expired"}, {"status": ""}]

    gamerpower.mark_free_verified(jeux)

    assert jeux[0]["free_verified"] is True
    assert jeux[1]["free_verified"] is False
    assert jeux[2]["free_verified"] is None  # la source ne se prononce pas


def _promo(discount_price=None, pourcentage=0):
    total = {"fmtPrice": {"originalPrice": "19,99 €"}}
    if discount_price is not None:
        total["discountPrice"] = discount_price
    return {
        "id": "abc123",
        "title": "Super Jeu",
        "keyImages": [],
        "price": {"totalPrice": total},
        "offerMappings": [{"pageSlug": "super-jeu"}],
        "promotions": {
            "promotionalOffers": [
                {
                    "promotionalOffers": [
                        {
                            "startDate": "2026-10-01T15:00:00.000Z",
                            "endDate": "2030-10-08T15:00:00.000Z",
                            "discountSetting": {"discountPercentage": pourcentage},
                        }
                    ]
                }
            ]
        },
    }


def test_epic_verifie_que_le_prix_actuel_est_bien_nul():
    assert epic_games._parse_element(_promo(discount_price=0))["free_verified"] is True
    assert epic_games._parse_element(_promo(discount_price=1999)) is None
    assert epic_games._parse_element(_promo()) is not None  # champ absent : rien n'est inventé


def test_epic_ignore_une_remise_non_nulle():
    assert epic_games._parse_element(_promo(discount_price=0, pourcentage=50)) is None


# ---------- Une source en panne n'empêche pas les autres ----------


async def test_une_source_en_panne_est_journalisee_et_nempeche_pas_le_reste(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", _boom)
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok([EPIC_GAME]))

    jeux = await offer_engine.fetch_offers()

    assert [jeu["id"] for jeu in jeux] == ["epic:1"]
    etat = monitoring.HEALTH.source("gamerpower")
    assert etat.consecutive_failures == 1
    assert "panne réseau" in etat.last_error
    assert monitoring.HEALTH.source_status("gamerpower") is monitoring.Status.DEGRADED
    assert "event=source.failure" in caplog.text
    assert "event=source.success" in caplog.text


async def test_une_source_muette_est_signalee(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setitem(offer_engine.SOURCES, "epic", _slow)

    assert await offer_engine.fetch_offers(sources=["epic"]) == []

    etat = monitoring.HEALTH.source("epic")
    assert etat.total_timeout == 1
    assert "délai d'attente dépassé" in etat.last_error
    assert "event=source.timeout" in caplog.text


async def test_un_format_inattendu_est_traite_comme_une_panne(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "epic", lambda: _ok({"pas": "une liste"}))

    assert await offer_engine.fetch_offers(sources=["epic"]) == []
    assert monitoring.HEALTH.source("epic").total_failure == 1


async def test_une_offre_malformee_nempeche_pas_les_autres(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lambda: _ok([{}, None, GAME]))

    jeux = await offer_engine.fetch_offers(sources=["gamerpower"])

    assert [jeu["id"] for jeu in jeux] == [1]


async def test_les_erreurs_alimentent_le_compteur_de_surveillance(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", _boom)

    await offer_engine.fetch_offers(sources=["gamerpower"])

    assert monitoring.HEALTH.error_count(config.MONITOR_ERROR_WINDOW_MINUTES) == 1


# ---------- Cache partagé (respect des sources) ----------


async def test_le_cache_evite_de_marteler_la_source(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    appels = []

    async def compteur():
        appels.append(1)
        return [GAME]

    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", compteur)
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower",))

    await offer_engine.fetch_offers(use_cache=True)
    await offer_engine.fetch_offers(use_cache=True)

    assert len(appels) == 1
    assert "event=offers.cache_hit" in caplog.text

    # Une vérification planifiée, elle, interroge toujours la source en direct.
    await offer_engine.fetch_offers()
    assert len(appels) == 2


async def test_le_cache_expire(monkeypatch):
    appels = []

    async def compteur():
        appels.append(1)
        return [GAME]

    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", compteur)
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower",))
    monkeypatch.setattr(config, "OFFER_CACHE_SECONDS", 0.0)

    await offer_engine.fetch_offers(use_cache=True)
    await offer_engine.fetch_offers(use_cache=True)

    assert len(appels) == 2


async def test_deux_commandes_simultanees_partagent_un_seul_appel(monkeypatch):
    appels = []

    async def lent():
        appels.append(1)
        await asyncio.sleep(0.02)  # plus court que OFFER_SOURCE_TIMEOUT (0,05 s)
        return [GAME]

    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", lent)
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower",))

    resultats = await asyncio.gather(
        offer_engine.fetch_offers(use_cache=True),
        offer_engine.fetch_offers(use_cache=True),
    )

    assert len(appels) == 1
    assert resultats[0] == resultats[1]


async def test_un_echec_total_nest_pas_mis_en_cache(monkeypatch):
    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", _boom)
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower",))

    assert await offer_engine.fetch_offers(use_cache=True) == []
    assert offer_engine.cached_offers() is None


async def test_un_flux_vide_est_mis_en_cache(monkeypatch):
    appels = []

    async def vide():
        appels.append(1)
        return []

    monkeypatch.setitem(offer_engine.SOURCES, "gamerpower", vide)
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower",))

    await offer_engine.fetch_offers(use_cache=True)
    await offer_engine.fetch_offers(use_cache=True)

    assert len(appels) == 1  # une source qui répond « rien » a bien répondu

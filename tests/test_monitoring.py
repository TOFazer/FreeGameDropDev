"""Surveillance : détecter « quelque chose va mal », alerter sans spammer, rétablir."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import config
import database
from utils import monitoring

MAINTENANT = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def _il_y_a(minutes: float) -> datetime:
    return MAINTENANT - timedelta(minutes=minutes)


@pytest.fixture(autouse=True)
def _seuils(monkeypatch):
    monkeypatch.setattr(config, "OFFER_SOURCES", ("gamerpower", "epic"))
    monkeypatch.setattr(config, "SOURCE_DOWN_AFTER_MINUTES", 10.0)
    monkeypatch.setattr(config, "MONITOR_ALERT_COOLDOWN_MINUTES", 30.0)
    monkeypatch.setattr(config, "MONITOR_ERROR_WINDOW_MINUTES", 15.0)
    monkeypatch.setattr(config, "MONITOR_ERROR_ALERT_THRESHOLD", 5)
    monkeypatch.setattr(config, "MONITOR_TASK_GRACE_MINUTES", 10.0)


# ---------- États ----------


def test_une_source_qui_repond_est_verte():
    monitoring.HEALTH.record_source_success("epic", latency_ms=120, offers=2, now=MAINTENANT)

    assert monitoring.HEALTH.source_status("epic", now=MAINTENANT) is monitoring.Status.OK
    assert monitoring.HEALTH.source("epic").last_offers == 2


def test_une_source_qui_vient_dechouer_est_degradee():
    monitoring.HEALTH.record_source_success("epic", now=_il_y_a(2))
    monitoring.HEALTH.record_source_failure("epic", error="timeout", now=MAINTENANT)

    assert monitoring.HEALTH.source_status("epic", now=MAINTENANT) is monitoring.Status.DEGRADED


def test_une_source_sans_succes_depuis_dix_minutes_est_indisponible():
    monitoring.HEALTH.record_source_success("epic", now=_il_y_a(40))
    for minutes in (12, 8, 4, 0):
        monitoring.HEALTH.record_source_failure("epic", error="HTTP 503", now=_il_y_a(minutes))

    assert monitoring.HEALTH.source_status("epic", now=MAINTENANT) is monitoring.Status.DOWN


def test_une_source_jamais_jointe_finit_indisponible():
    monitoring.HEALTH.record_source_failure("epic", error="réseau", now=_il_y_a(1))
    monitoring.HEALTH.started_at = _il_y_a(30)

    assert monitoring.HEALTH.source_status("epic", now=MAINTENANT) is monitoring.Status.DOWN


def test_une_source_jamais_interrogee_reste_inconnue():
    assert monitoring.HEALTH.source_status("epic", now=MAINTENANT) is monitoring.Status.UNKNOWN


def test_une_tache_en_retard_est_signalee():
    monitoring.HEALTH.record_task_run("check_games", interval_seconds=3600, now=_il_y_a(5))
    assert monitoring.HEALTH.task_status("check_games", now=MAINTENANT) is monitoring.Status.OK

    monitoring.HEALTH.record_task_run("check_games", interval_seconds=3600, now=_il_y_a(90))
    assert monitoring.HEALTH.task_status("check_games", now=MAINTENANT) is monitoring.Status.DEGRADED


def test_une_tache_qui_na_jamais_demarre_finit_par_alerter():
    monitoring.HEALTH.started_at = _il_y_a(70)
    monitoring.HEALTH.register_task("check_games", interval_seconds=3600)

    # 70 min après le démarrage, pour une tâche attendue toutes les heures + 10 min de marge :
    # rien d'anormal tant que la marge n'est pas dépassée… puis l'alerte tombe.
    assert monitoring.HEALTH.task_status("check_games", now=MAINTENANT) is monitoring.Status.OK
    monitoring.HEALTH.started_at = _il_y_a(120)
    assert monitoring.HEALTH.task_status("check_games", now=MAINTENANT) is not monitoring.Status.OK


# ---------- Alertes ----------


def test_une_source_indisponible_declenche_une_alerte_puis_un_retablissement():
    livre = monitoring.AlertBook(30.0)
    monitoring.HEALTH.started_at = _il_y_a(60)
    monitoring.HEALTH.record_source_failure("epic", error="HTTP 503", now=MAINTENANT)

    alertes = monitoring.evaluate(livre, now=MAINTENANT)
    cles = [alerte.key for alerte in alertes]
    assert "source:epic" in cles
    assert alertes[0].level == "critical"
    assert "indisponible" in alertes[0].text

    # Toujours en panne : pas de répétition avant la fin du délai anti-spam.
    monitoring.HEALTH.record_source_failure("epic", error="HTTP 503", now=MAINTENANT)
    assert monitoring.evaluate(livre, now=MAINTENANT) == []

    # La source revient : un seul message de rétablissement.
    monitoring.HEALTH.record_source_success("epic", now=MAINTENANT + timedelta(minutes=1))
    retablissements = monitoring.evaluate(livre, now=MAINTENANT + timedelta(minutes=1))
    assert [alerte.level for alerte in retablissements] == ["recovery"]
    assert monitoring.evaluate(livre, now=MAINTENANT + timedelta(minutes=2)) == []


def test_lalerte_est_repetee_apres_le_delai_anti_spam():
    livre = monitoring.AlertBook(30.0)
    monitoring.HEALTH.started_at = _il_y_a(60)
    monitoring.HEALTH.record_source_failure("epic", error="HTTP 503", now=MAINTENANT)
    assert monitoring.evaluate(livre, now=MAINTENANT)

    monitoring.HEALTH.record_source_failure("epic", error="HTTP 503", now=MAINTENANT)
    assert monitoring.evaluate(livre, now=MAINTENANT + timedelta(minutes=45))


def test_une_source_degradee_ne_declenche_pas_dalerte_bruyante():
    livre = monitoring.AlertBook(30.0)
    monitoring.HEALTH.record_source_success("epic", now=_il_y_a(1))
    monitoring.HEALTH.record_source_failure("epic", error="timeout", now=MAINTENANT)

    assert monitoring.evaluate(livre, now=MAINTENANT) == []
    assert monitoring.HEALTH.source_status("epic", now=MAINTENANT) is monitoring.Status.DEGRADED


async def test_la_base_de_donnees_injoignable_est_signalee(monkeypatch):
    async def ping_casse():
        raise OSError("disque plein")

    monkeypatch.setattr(database, "ping", ping_casse)
    livre = monitoring.AlertBook(30.0)

    assert await monitoring.probe_database(now=MAINTENANT) is False
    alertes = monitoring.evaluate(livre, now=MAINTENANT)

    assert [alerte.key for alerte in alertes] == ["database"]
    assert "base de données" in alertes[0].text


def test_un_pic_derreurs_declenche_une_alerte():
    livre = monitoring.AlertBook(30.0)
    for _ in range(5):
        monitoring.HEALTH.record_error(now=MAINTENANT)

    alertes = monitoring.evaluate(livre, now=MAINTENANT)

    assert [alerte.key for alerte in alertes] == ["errors"]
    monitoring.HEALTH.record_error(now=MAINTENANT)
    assert monitoring.evaluate(livre, now=MAINTENANT) == []  # anti-spam


def test_les_erreurs_anciennes_ne_comptent_plus():
    for _ in range(5):
        monitoring.HEALTH.record_error(now=_il_y_a(40))

    assert monitoring.HEALTH.error_count(15, now=MAINTENANT) == 0


def test_une_tache_arretee_declenche_une_alerte():
    livre = monitoring.AlertBook(30.0)
    monitoring.HEALTH.record_task_run("check_games", interval_seconds=3600, now=_il_y_a(180))

    alertes = monitoring.evaluate(livre, now=MAINTENANT)

    assert [alerte.key for alerte in alertes] == ["task:check_games"]
    assert "ne s'exécute plus" in alertes[0].text


def test_une_connexion_discord_perdue_declenche_une_alerte():
    livre = monitoring.AlertBook(30.0)

    alertes = monitoring.evaluate(livre, discord=(monitoring.Status.DOWN, "déconnecté"), now=MAINTENANT)

    assert [alerte.key for alerte in alertes] == ["discord"]
    assert "Discord" in alertes[0].text


def test_le_retablissement_du_serveur_est_annonce_une_fois():
    livre = monitoring.AlertBook(30.0)
    monitoring.evaluate(livre, discord=(monitoring.Status.DOWN, "déconnecté"), now=MAINTENANT)

    alertes = monitoring.evaluate(livre, discord=(monitoring.Status.OK, "connecté"), now=MAINTENANT)

    assert [alerte.level for alerte in alertes] == ["recovery"]


# ---------- État de Discord ----------


def test_un_bot_ferme_est_en_panne():
    bot = SimpleNamespace(is_closed=lambda: True, is_ready=lambda: False, latency=0.05)
    assert monitoring.discord_status(bot)[0] is monitoring.Status.DOWN


def test_un_bot_en_cours_de_connexion_est_degrade():
    bot = SimpleNamespace(is_closed=lambda: False, is_ready=lambda: False, latency=0.05)
    assert monitoring.discord_status(bot)[0] is monitoring.Status.DEGRADED


def test_une_latence_nan_est_signalee():
    bot = SimpleNamespace(latency=float("nan"))
    assert monitoring.discord_status(bot)[0] is monitoring.Status.DEGRADED


def test_un_bot_normal_est_vert():
    bot = SimpleNamespace(latency=0.042)
    statut, texte = monitoring.discord_status(bot)
    assert statut is monitoring.Status.OK
    assert "42 ms" in texte


# ---------- Cycle complet ----------


async def test_le_cycle_envoie_les_alertes_et_bat_le_coeur(db, monkeypatch):
    async def ping_casse():
        raise OSError("base inaccessible")

    monkeypatch.setattr(database, "ping", ping_casse)
    envoyees = []

    async def send(alerte):
        envoyees.append(alerte)

    alertes = await monitoring.run_check(None, book=monitoring.AlertBook(30.0), send=send, now=MAINTENANT)

    assert [alerte.key for alerte in alertes] == ["database"]
    assert envoyees == alertes
    assert await database.get_bot_state("monitor_heartbeat_at") is not None


async def test_une_alerte_impossible_a_envoyer_ne_bloque_pas_le_cycle(db, caplog):
    async def ping_casse():
        raise OSError("base inaccessible")

    async def send(alerte):
        raise RuntimeError("Discord injoignable")

    import database as database_module

    original = database_module.ping
    database_module.ping = ping_casse
    try:
        alertes = await monitoring.run_check(None, book=monitoring.AlertBook(30.0), send=send)
    finally:
        database_module.ping = original

    assert alertes  # l'alerte reste due et l'erreur est comptée
    assert monitoring.HEALTH.error_count(config.MONITOR_ERROR_WINDOW_MINUTES) >= 1


async def test_le_sans_destinataire_se_contente_de_journaliser(db, caplog):
    monitoring.HEALTH.record_source_failure("epic", error="HTTP 503", now=MAINTENANT)
    monitoring.HEALTH.started_at = _il_y_a(30)

    alertes = await monitoring.run_check(None, book=monitoring.AlertBook(30.0), now=MAINTENANT)

    assert alertes
    assert "event=monitor.alert" in caplog.text


# ---------- Rapport ----------


async def test_le_rapport_ressemble_au_tableau_de_bord_attendu(db):
    await db.set_bot_state("last_check_at", MAINTENANT.isoformat())
    monitoring.HEALTH.record_source_success("gamerpower", latency_ms=88, offers=4, now=MAINTENANT)
    monitoring.HEALTH.record_source_success("epic", latency_ms=140, offers=2, now=MAINTENANT)
    monitoring.HEALTH.record_task_run("check_games", interval_seconds=3600, now=MAINTENANT)

    rapport = await monitoring.status_report(SimpleNamespace(latency=0.05), now=MAINTENANT)

    assert "FreeGameDrop" in rapport
    assert "🟢 Bot" in rapport
    assert "🟢 Discord" in rapport
    assert "🟢 Base de données" in rapport
    assert "Sources" in rapport
    assert "gamerpower" in rapport and "epic" in rapport
    assert "Dernière vérification" in rapport
    assert "Erreurs" in rapport


async def test_un_instantane_json_serialisable(db):
    monitoring.HEALTH.record_source_success("epic", latency_ms=90, offers=1, now=MAINTENANT)

    instantane = await monitoring.collect(SimpleNamespace(latency=0.05), now=MAINTENANT)
    import json

    charge = json.dumps(monitoring.to_jsonable(instantane))

    assert '"status"' in charge
    assert instantane["components"]["database"] == "ok"
    assert instantane["sources"][0]["name"] == "epic"


async def test_une_base_injoignable_apparait_en_rouge(db, monkeypatch):
    async def ping_casse():
        raise OSError("fichier verrouillé")

    monkeypatch.setattr(database, "ping", ping_casse)

    instantane = await monitoring.collect(None, now=MAINTENANT)
    rapport = monitoring.build_report(instantane, now=MAINTENANT)

    assert instantane["components"]["database"] == "down"
    assert instantane["status"] == "down"
    assert "🔴 Base de données" in rapport


async def test_letat_de_sante_indique_lenvironnement(db, monkeypatch):
    """`/sante` et `/api/health` doivent dire quel environnement répond."""
    monkeypatch.setattr(config, "ENVIRONMENT", "development")

    instantane = await monitoring.collect(None, now=MAINTENANT)
    rapport = monitoring.build_report(instantane, now=MAINTENANT)

    assert instantane["environment"] == "development"
    assert "🧪 Development" in rapport
    assert "Environnement" in rapport

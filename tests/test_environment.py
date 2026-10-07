"""Garde-fou DEV / PROD : deux environnements, jamais les mêmes ressources.

Ces tests vérifient la règle la plus importante du lot : **le bot de développement
refuse de démarrer avec une configuration de production** (ou l'inverse), plutôt que
de se connecter au mauvais Discord avec la mauvaise base.
"""

import base64
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import config
from utils import environment as env

DEV_APP_ID = 1_234_567_890_123_456_789
PROD_APP_ID = 9_876_543_210_987_654_321


def fake_token(application_id: int) -> str:
    """Jeton Discord factice mais bien formé : l'identifiant d'application y est encodé."""
    first = base64.urlsafe_b64encode(str(application_id).encode()).decode().rstrip("=")
    return f"{first}.abcdefghijklmnopqrstuvwxyz012345.ABCDEFGHIJKLMNOPQRSTUVWXYZ01234567"


def dev_settings(**overrides) -> SimpleNamespace:
    """Configuration de développement cohérente, surchargeable champ par champ."""
    values = {
        "ENVIRONMENT": env.DEVELOPMENT,
        "EXPECTED_ENVIRONMENT": env.DEVELOPMENT,
        "DISCORD_TOKEN": fake_token(DEV_APP_ID),
        "DISCORD_APPLICATION_ID": DEV_APP_ID,
        "DISCORD_CLIENT_ID": str(DEV_APP_ID),
        "DB_PATH": env.DEVELOPMENT_DEFAULT_DB,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------- Environnement déclaré ----------


def test_development_environment():
    """La configuration de développement livrée est reconnue comme telle."""
    assert config.ENVIRONMENT in env.KNOWN_ENVIRONMENTS
    assert env.normalize("DEV") == env.DEVELOPMENT
    assert env.normalize(" Development ") == env.DEVELOPMENT
    assert env.normalize("PROD") == env.PRODUCTION


def test_dev_database_is_not_production():
    """La base par défaut du développement n'est jamais celle de la production."""
    assert "prod" not in env.DEVELOPMENT_DEFAULT_DB.lower()
    assert env.DEVELOPMENT_DEFAULT_DB != env.PRODUCTION_DEFAULT_DB
    assert "dev" in env.DEVELOPMENT_DEFAULT_DB.lower()


def test_configuration_de_developpement_acceptee():
    result = env.check(
        environment="development",
        expected="development",
        token=fake_token(DEV_APP_ID),
        application_id=DEV_APP_ID,
        client_id=str(DEV_APP_ID),
        db_path="data/freegamedrop-dev.db",
    )

    assert result.ok, result.errors
    assert result.environment == env.DEVELOPMENT
    assert not result.warnings


def test_configuration_de_production_nominale_acceptee():
    result = env.check(
        environment="production",
        expected="production",
        token=fake_token(PROD_APP_ID),
        application_id=PROD_APP_ID,
        client_id=str(PROD_APP_ID),
        db_path="bot.db",
    )

    assert result.ok, result.errors


def test_environnement_inconnu_refuse():
    result = env.check(environment="staging", expected="staging")

    assert not result.ok
    assert any("inconnu" in message for message in result.errors)


# ---------- Le scénario catastrophe ----------


def test_le_bot_de_dev_refuse_un_jeton_de_production():
    """Le cas visé : un `.env` de production lancé depuis le dossier de développement."""
    result = env.check(
        environment="development",
        expected="development",
        token=fake_token(PROD_APP_ID),  # jeton de l'application PROD
        application_id=DEV_APP_ID,  # identifiant de l'application DEV
        client_id=str(DEV_APP_ID),
        db_path="data/freegamedrop-dev.db",
    )

    assert not result.ok
    assert any("Discord application mismatch" in message for message in result.errors)
    assert "refused to start" in result.refusal_message()


def test_le_bot_de_dev_refuse_une_base_de_production():
    result = env.check(
        environment="development",
        expected="development",
        token=fake_token(DEV_APP_ID),
        application_id=DEV_APP_ID,
        db_path="data/freegamedrop-prod.db",
    )

    assert not result.ok
    assert any("base de production" in message for message in result.errors)


def test_la_production_refuse_une_base_de_developpement():
    result = env.check(
        environment="production",
        expected="production",
        token=fake_token(PROD_APP_ID),
        application_id=PROD_APP_ID,
        db_path="data/freegamedrop-dev.db",
    )

    assert not result.ok
    assert any("base de développement" in message for message in result.errors)


def test_ecart_entre_environnement_et_environnement_attendu():
    result = env.check(environment="production", expected="development", db_path="bot.db")

    assert not result.ok
    assert any("Environment mismatch" in message for message in result.errors)


def test_le_client_oauth_doit_etre_la_meme_application_que_le_jeton():
    """Un jeton DEV et un `DISCORD_CLIENT_ID` PROD ne doivent pas cohabiter."""
    result = env.check(
        environment="development",
        expected="development",
        token=fake_token(DEV_APP_ID),
        application_id=DEV_APP_ID,
        client_id=str(PROD_APP_ID),
        db_path="data/freegamedrop-dev.db",
    )

    assert not result.ok
    assert any("DISCORD_CLIENT_ID" in message for message in result.errors)


def test_avertissement_quand_lapplication_nest_pas_declaree():
    """Sans DISCORD_APPLICATION_ID, le jeton ne peut pas être rattaché : avertissement."""
    result = env.check(
        environment="development",
        expected="development",
        token=fake_token(DEV_APP_ID),
        application_id=None,
        db_path="data/freegamedrop-dev.db",
    )

    assert result.ok, "un garde-fou incomplet avertit, il ne bloque pas"
    assert any("DISCORD_APPLICATION_ID" in message for message in result.warnings)


def test_avertissement_si_environnement_attendu_absent():
    result = env.check(environment="development", db_path="data/freegamedrop-dev.db")

    assert result.ok
    assert any("EXPECTED_ENVIRONMENT" in message for message in result.warnings)


def test_avertissement_si_le_dev_utilise_le_fichier_par_defaut_de_la_production():
    result = env.check(environment="development", db_path="bot.db")

    assert result.ok
    assert any(env.DEVELOPMENT_DEFAULT_DB in message for message in result.warnings)


# ---------- Lecture du jeton ----------


def test_application_id_lu_dans_le_jeton():
    assert env.application_id_from_token(fake_token(PROD_APP_ID)) == PROD_APP_ID
    assert env.application_id_from_token("") is None
    assert env.application_id_from_token("pas-un-jeton") is None
    assert env.application_id_from_token("...") is None


# ---------- Identité affichée ----------


def test_prefixe_et_nom_public():
    assert env.log_prefix("development") == "[DEVELOPMENT]"
    assert env.log_prefix("production") == "[PRODUCTION]"
    assert env.product_name("development") == "FreeGameDrop DEV"
    assert env.product_name("production") == "FreeGameDrop"
    assert env.describe("development") == "🧪 Development"
    assert env.page_title("FreeGameDrop — Tableau de bord", "development").startswith("🧪 FreeGameDrop DEV")


def test_bandeau_de_demarrage_porte_lenvironnement(caplog):
    with caplog.at_level(logging.INFO):
        env.log_start(
            logging.getLogger("test"),
            db_path=env.DEVELOPMENT_DEFAULT_DB,
            application_id=DEV_APP_ID,
            maintenance=False,
            environment="development",
        )

    text = caplog.text
    assert "[DEVELOPMENT] FreeGameDrop starting..." in text
    assert f"[DEVELOPMENT] Database: {env.DEVELOPMENT_DEFAULT_DB}" in text
    assert f"[DEVELOPMENT] Discord application: {DEV_APP_ID}" in text


def test_bandeau_de_connexion_porte_lenvironnement(caplog):
    with caplog.at_level(logging.INFO):
        env.log_connected(
            logging.getLogger("test"), user="Bot#1234", guilds=1, environment="development"
        )

    assert "[DEVELOPMENT] Discord bot connected as Bot#1234" in caplog.text


# ---------- Refus effectif du démarrage ----------


def test_verify_startup_refuse_une_configuration_de_production_en_dev(caplog):
    settings = dev_settings(
        DISCORD_TOKEN=fake_token(PROD_APP_ID),
        DISCORD_CLIENT_ID=str(PROD_APP_ID),
    )

    with caplog.at_level(logging.INFO), pytest.raises(env.EnvironmentRefused) as refused:
        env.verify_startup(settings)

    assert "refused to start" in str(refused.value)
    assert "Discord application mismatch" in caplog.text
    assert "event=environment.refused" in caplog.text


def test_verify_startup_accepte_la_configuration_de_dev(caplog):
    with caplog.at_level(logging.INFO):
        result = env.verify_startup(dev_settings())

    assert result.ok
    assert "event=environment.checked" in caplog.text


# ---------- Démarrage réel (processus séparé, sans réseau) ----------


def _run_main(**overrides) -> subprocess.CompletedProcess:
    """Lance `main.py` avec un environnement explicite et récupère sa sortie."""
    variables = {
        "ENVIRONMENT": "development",
        "EXPECTED_ENVIRONMENT": "development",
        "DISCORD_TOKEN": fake_token(DEV_APP_ID),
        "DISCORD_APPLICATION_ID": str(DEV_APP_ID),
        "DISCORD_CLIENT_ID": str(DEV_APP_ID),
        "DB_PATH": "data/freegamedrop-dev.db",
        "LOG_LEVEL": "INFO",
    }
    variables.update({key: str(value) for key, value in overrides.items()})
    return subprocess.run(
        [sys.executable, "main.py"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ, **variables},
    )


def test_le_processus_refuse_de_demarrer_avec_un_jeton_de_production():
    """Test de bout en bout : rien n'est tenté côté Discord, le processus s'arrête."""
    done = _run_main(DISCORD_APPLICATION_ID=PROD_APP_ID + 1, DISCORD_TOKEN=fake_token(PROD_APP_ID))

    assert done.returncode != 0
    assert "Discord application mismatch" in done.stdout + done.stderr
    assert "refused to start" in done.stdout + done.stderr


def test_le_processus_refuse_une_base_de_production_en_dev():
    done = _run_main(DB_PATH="data/freegamedrop-prod.db")

    assert done.returncode != 0
    assert "base de production" in done.stdout + done.stderr


def test_le_processus_sarrete_si_le_jeton_manque():
    done = _run_main(DISCORD_TOKEN="")

    assert done.returncode != 0
    assert "DISCORD_TOKEN manquant" in done.stdout + done.stderr


def test_un_dossier_parent_dev_ne_bloque_pas_la_production():
    """Un chemin d'installation nommé « dev » ou « test » ne doit pas bloquer la prod."""
    result = env.check(
        environment="production",
        expected="production",
        token=fake_token(PROD_APP_ID),
        application_id=PROD_APP_ID,
        db_path="/srv/dev/freegamedrop.db",
    )

    assert result.ok, result.errors


def test_la_production_refuse_un_fichier_de_developpement():
    result = env.check(
        environment="production",
        expected="production",
        token=fake_token(PROD_APP_ID),
        application_id=PROD_APP_ID,
        db_path="/srv/data/bot-dev.db",
    )

    assert not result.ok
    assert any("base de développement" in message for message in result.errors)

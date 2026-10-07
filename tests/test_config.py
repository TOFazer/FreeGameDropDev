"""Lecture de la configuration (.env) et valeurs par défaut."""

import config
from utils import environment


def test_valeurs_par_defaut():
    assert config.CATEGORY_NAME and config.ROLES_CHANNEL
    assert config.CHECK_INTERVAL_HOURS > 0
    assert config.MAX_GAMES > 0
    assert config.MAX_ACCESS_ROLES <= 25  # limite d'un menu Discord
    assert config.GAMERPOWER_API_URL.startswith("https://")


def test_variable_absente_ou_vide(monkeypatch):
    monkeypatch.delenv("UNE_VARIABLE", raising=False)
    assert config._env_str("UNE_VARIABLE", "défaut") == "défaut"

    monkeypatch.setenv("UNE_VARIABLE", "   ")
    assert config._env_str("UNE_VARIABLE", "défaut") == "défaut"


def test_valeurs_numeriques(monkeypatch):
    monkeypatch.setenv("UN_NOMBRE", "3")
    assert config._env_int("UN_NOMBRE", 1) == 3
    assert config._env_float("UN_NOMBRE", 1.0) == 3.0

    monkeypatch.setenv("UN_NOMBRE", "pas un nombre")
    assert config._env_int("UN_NOMBRE", 7) == 7, "une valeur illisible ne doit pas tout casser"
    assert config._env_float("UN_NOMBRE", 0.5) == 0.5


def test_espaces_autour_des_valeurs(monkeypatch):
    monkeypatch.setenv("UN_TEXTE", "  salon-des-roles  ")
    assert config._env_str("UN_TEXTE", "") == "salon-des-roles"


def test_le_token_nest_jamais_dans_le_depot():
    """Le token vient de .env (ignoré par git), jamais du code."""
    with open("config.py", encoding="utf-8") as f:
        source = f.read()

    assert 'DISCORD_TOKEN: str = _env_str("DISCORD_TOKEN")' in source


def test_variables_denvironnement_exposees():
    """Les quatre réglages du garde-fou DEV / PROD sont bien lus depuis `.env`."""
    assert config.ENVIRONMENT in environment.KNOWN_ENVIRONMENTS
    assert isinstance(config.EXPECTED_ENVIRONMENT, str)
    assert config.DISCORD_APPLICATION_ID is None or isinstance(config.DISCORD_APPLICATION_ID, int)
    assert isinstance(config.MAINTENANCE_MODE, bool)


def test_lenvironnement_ne_choisit_pas_le_jeton():
    """Le jeton vient toujours de `.env` : l'environnement ne fait que le contrôler.

    Si quelqu'un ajoutait un jour un jeton de production dans le code au motif
    « c'est la prod, c'est plus simple », ce test tomberait.
    """
    with open("config.py", encoding="utf-8") as f:
        source = f.read()

    assert 'DISCORD_TOKEN: str = _env_str("DISCORD_TOKEN")' in source
    assert source.count('_env_str("DISCORD_TOKEN"') == 1, "un seul jeton : celui de `.env`"
    assert 'ENVIRONMENT).DISCORD_TOKEN' not in source


def test_la_base_par_defaut_suit_lenvironnement():
    """Un fichier SQLite différent par environnement, sans configuration explicite."""
    assert "dev" in environment.DEVELOPMENT_DEFAULT_DB.lower()
    assert "dev" not in environment.PRODUCTION_DEFAULT_DB.lower()
    assert config.DB_PATH  # dépend de l'environnement de la machine de test

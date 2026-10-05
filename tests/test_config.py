"""Lecture de la configuration (.env) et valeurs par défaut."""

import config


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

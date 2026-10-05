"""Configuration centralisée du bot.

Tout ce qui peut changer (token, base de données, rythme de vérification,
plateformes suivies, noms des salons) est défini ici et surchargeable
via le fichier `.env` — voir `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None or not value.strip() else value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env_str(name, str(default)))
    except ValueError:
        return default


# ---------- Discord ----------

DISCORD_TOKEN: str = _env_str("DISCORD_TOKEN")

# Ancien serveur de test : ses copies de commandes sont nettoyées au démarrage
# pour éviter les doublons. Mettre TEST_GUILD_ID=0 dans .env pour désactiver.
TEST_GUILD_ID: int | None = _env_int("TEST_GUILD_ID", 1391429196105912452) or None

LOG_LEVEL: str = _env_str("LOG_LEVEL", "INFO").upper()


# ---------- Base de données ----------

DB_PATH: str = _env_str("DB_PATH", "bot.db")


# ---------- Vérification des jeux ----------

CHECK_INTERVAL_HOURS: float = _env_float("CHECK_INTERVAL_HOURS", 1.0)
MAX_GAMES: int = _env_int("MAX_GAMES", 10)  # jeux récents examinés à chaque tour


# ---------- API GamerPower ----------

GAMERPOWER_API_URL: str = _env_str("GAMERPOWER_API_URL", "https://www.gamerpower.com/api/giveaways")
GAMERPOWER_TIMEOUT: float = _env_float("GAMERPOWER_TIMEOUT", 15.0)


# ---------- Salons créés par /setup-auto ----------

CATEGORY_NAME: str = _env_str("CATEGORY_NAME", "🎮 Jeux gratuits")
ROLES_CHANNEL: str = _env_str("ROLES_CHANNEL", "choisir-ses-roles")
ROLES_TOPIC: str = "Clique sur un bouton pour recevoir les alertes • salon en lecture seule"
GAME_CHANNEL_PREFIX: str = "jeux-"
MAX_ACCESS_ROLES: int = 10  # rôles maximum autorisés à voir le salon des rôles


# ---------- Plateformes suivies ----------


@dataclass(frozen=True)
class Platform:
    """Une plateforme suivie : son rôle, son salon, sa couleur et ses mots-clés API."""

    key: str
    name: str
    keywords: tuple  # cherchés dans le champ "platforms" de l'API GamerPower
    emoji: str
    colour: int

    @property
    def role_name(self) -> str:
        return f"{self.emoji} {self.name}"

    @property
    def channel_name(self) -> str:
        return f"{GAME_CHANNEL_PREFIX}{self.key}"


PLATFORMS = {
    platform.key: platform
    for platform in (
        Platform("steam", "Steam", ("steam",), "🔵", 0x66C0F4),
        Platform("epic", "Epic Games Store", ("epic games",), "⚪", 0xD9D9D9),
        Platform("gog", "GOG", ("gog",), "🟣", 0xA855F7),
        Platform("ubisoft", "Ubisoft", ("ubisoft",), "🔷", 0x0070FF),
    )
}
PLATFORM_KEYS = list(PLATFORMS)

# Utilisés quand la plateforme d'un jeu n'est pas reconnue.
DEFAULT_EMOJI = "🎁"
DEFAULT_COLOUR = 0xF1C40F

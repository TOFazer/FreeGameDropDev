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

# Liens affichés dans la commande /info.
PROJECT_URL: str = _env_str(
    "PROJECT_URL", "https://github.com/TOFazer/release-bot-FreeGameDrop"
)
SUPPORT_URL: str = _env_str("SUPPORT_URL", f"{PROJECT_URL}/issues")
VOTE_URL: str = _env_str("VOTE_URL")


# ---------- Base de données ----------

DB_PATH: str = _env_str("DB_PATH", "bot.db")


# ---------- Vérification des jeux ----------

CHECK_INTERVAL_HOURS: float = _env_float("CHECK_INTERVAL_HOURS", 1.0)
MAX_GAMES: int = _env_int("MAX_GAMES", 10)  # jeux récents examinés à chaque tour


# ---------- API GamerPower ----------

GAMERPOWER_API_URL: str = _env_str("GAMERPOWER_API_URL", "https://www.gamerpower.com/api/giveaways")
GAMERPOWER_TIMEOUT: float = _env_float("GAMERPOWER_TIMEOUT", 15.0)


# ---------- Source Epic Games Store ----------

EPIC_API_URL: str = _env_str(
    "EPIC_API_URL",
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions",
)
EPIC_TIMEOUT: float = _env_float("EPIC_TIMEOUT", 15.0)
EPIC_STORE_URL: str = _env_str("EPIC_STORE_URL", "https://store.epicgames.com")
EPIC_LOCALE: str = _env_str("EPIC_LOCALE", "fr-FR")
EPIC_COUNTRY: str = _env_str("EPIC_COUNTRY", "FR")


# ---------- Moteur d'agrégation multi-sources ----------

# Sources activées pour /free, les alertes et la veille automatique.
OFFER_SOURCES: tuple = tuple(
    source.strip()
    for source in _env_str("OFFER_SOURCES", "gamerpower,epic").split(",")
    if source.strip()
)
OFFER_SOURCE_TIMEOUT: float = _env_float("OFFER_SOURCE_TIMEOUT", 20.0)


# ---------- Fuseau horaire par défaut ----------

DEFAULT_TIMEZONE: str = _env_str("DEFAULT_TIMEZONE", "Europe/Paris")


# ---------- Catégorisation des offres ----------

OFFER_TYPE_LABELS: dict = {
    "game": "🎮 Jeu complet",
    "dlc": "➕ DLC / extension",
    "content": "🎁 Contenu / bêta",
}
OFFER_TYPE_KEYS = list(OFFER_TYPE_LABELS)

GENRE_LABELS: dict = {
    "action": "Action",
    "adventure": "Aventure",
    "rpg": "RPG",
    "strategy": "Stratégie",
    "simulation": "Simulation",
    "sport": "Sport",
    "racing": "Course",
    "puzzle": "Puzzle",
    "horror": "Horreur",
    "indie": "Indépendant",
    "multiplayer": "Multijoueur",
    "shooter": "Tir",
}
GENRE_KEYS = list(GENRE_LABELS)


# ---------- Alertes et notifications ----------

USER_NOTIFICATION_EVENT_LABELS: dict = {
    "new_offer": "🆕 Nouvelle offre",
    "ending_soon": "⏳ Se termine bientôt",
}
REMINDER_EVENT_LABELS: dict = {
    "ends_today": "📅 Se termine aujourd'hui",
}

# Délai minimal entre deux alertes identiques envoyées à un même membre, en heures.
ALERT_CADENCE_HOURS: float = _env_float("ALERT_CADENCE_HOURS", 1.0)

# Fenêtre considérée comme « se termine bientôt » pour les alertes et /free.
LAST_DAY_HOURS: float = _env_float("LAST_DAY_HOURS", 24.0)
LAST_HOURS_THRESHOLD: float = _env_float("LAST_HOURS_THRESHOLD", 6.0)


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


# ---------- Tableau de bord web ----------

DASHBOARD_ENABLED: bool = _env_str("DASHBOARD_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
DASHBOARD_HOST: str = _env_str("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT: int = _env_int("DASHBOARD_PORT", 8080)
DASHBOARD_SECRET_KEY: str = _env_str("DASHBOARD_SECRET_KEY", "change-me-in-prod")
DASHBOARD_BASE_URL: str = _env_str("DASHBOARD_BASE_URL", f"http://localhost:{DASHBOARD_PORT}")

DISCORD_CLIENT_ID: str = _env_str("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET: str = _env_str("DISCORD_CLIENT_SECRET")
DISCORD_OAUTH_REDIRECT_URI: str = _env_str(
    "DISCORD_OAUTH_REDIRECT_URI", f"{DASHBOARD_BASE_URL}/auth/callback"
)
DISCORD_API_BASE_URL: str = _env_str("DISCORD_API_BASE_URL", "https://discord.com/api")

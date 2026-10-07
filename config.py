"""Configuration centralisée du bot.

Tout ce qui peut changer (token, base de données, rythme de vérification,
plateformes suivies, noms des salons) est défini ici et surchargeable
via le fichier `.env` — voir `.env.example`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from utils import design

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


def _env_bool(name: str, default: bool) -> bool:
    value = _env_str(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


# ---------- Discord ----------

DISCORD_TOKEN: str = _env_str("DISCORD_TOKEN")

# Ancien serveur de test : ses copies de commandes sont nettoyées au démarrage
# pour éviter les doublons. Mettre TEST_GUILD_ID=0 dans .env pour désactiver.
TEST_GUILD_ID: int | None = _env_int("TEST_GUILD_ID", 1391429196105912452) or None

LOG_LEVEL: str = _env_str("LOG_LEVEL", "INFO").upper()

# Fichier de journal supplémentaire (rotation automatique, 5 Mo × 3). Vide = sortie
# standard uniquement. Les secrets y sont masqués de la même façon que sur la sortie.
LOG_FILE: str = _env_str("LOG_FILE")

# Remplace les identifiants Discord (membres, serveurs) par une empreinte stable dans
# les logs. À activer si un journal doit sortir de l'infrastructure du bot.
LOG_PSEUDONYMIZE_IDS: bool = _env_bool("LOG_PSEUDONYMIZE_IDS", False)

# Longueur maximale d'un champ dans les lignes `event=…` (au-delà : tronqué).
LOG_MAX_FIELD_CHARS: int = _env_int("LOG_MAX_FIELD_CHARS", 160)

# Liens affichés dans la commande /info.
PROJECT_URL: str = _env_str("PROJECT_URL", "https://github.com/TOFazer/freegamedrop")
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

# Durée pendant laquelle les offres déjà récupérées sont réutilisées pour /free :
# plusieurs membres peuvent consulter le catalogue sans marteler les sources.
OFFER_CACHE_SECONDS: float = _env_float("OFFER_CACHE_SECONDS", 60.0)


# ---------- Limites de débit ----------

# Ces limites n'existent que pour protéger les sources et l'API Discord : elles sont
# volontairement larges. Le détail par commande est dans `utils/rate_limits.py`.
RATE_LIMIT_USER_PER_MINUTE: int = _env_int("RATE_LIMIT_USER_PER_MINUTE", 20)
RATE_LIMIT_FREE_PER_MINUTE: int = _env_int("RATE_LIMIT_FREE_PER_MINUTE", 4)
RATE_LIMIT_ADMIN_PER_MINUTE: int = _env_int("RATE_LIMIT_ADMIN_PER_MINUTE", 6)
RATE_LIMIT_ADMIN_HEAVY_PER_10_MINUTES: int = _env_int("RATE_LIMIT_ADMIN_HEAVY_PER_10_MINUTES", 3)

# Espacement minimal entre deux messages envoyés dans un même salon ou à un même membre.
# Respecte les limites de cadence de Discord sans jamais retarder une annonce isolée.
DISCORD_SEND_INTERVAL_SECONDS: float = _env_float("DISCORD_SEND_INTERVAL_SECONDS", 0.4)


# ---------- Monitoring ----------

# Surveillance interne : état des composants, alerte si une source tombe, si une
# tâche s'arrête, si la base ne répond plus ou si les erreurs s'accumulent.
MONITOR_ENABLED: bool = _env_bool("MONITOR_ENABLED", True)
MONITOR_INTERVAL_MINUTES: float = _env_float("MONITOR_INTERVAL_MINUTES", 5.0)

# Salon qui reçoit les alertes de surveillance. Vide = message privé au propriétaire.
MONITOR_ALERT_CHANNEL_ID: int | None = _env_int("MONITOR_ALERT_CHANNEL_ID", 0) or None
# Destinataire des alertes si aucun salon n'est configuré (0 = propriétaire du bot).
MONITOR_OWNER_ID: int | None = _env_int("MONITOR_OWNER_ID", 0) or None

# Une source qui n'a plus réussi depuis ce délai est considérée comme indisponible.
SOURCE_DOWN_AFTER_MINUTES: float = _env_float("SOURCE_DOWN_AFTER_MINUTES", 10.0)
# Deux alertes identiques ne sont pas répétées avant ce délai.
MONITOR_ALERT_COOLDOWN_MINUTES: float = _env_float("MONITOR_ALERT_COOLDOWN_MINUTES", 30.0)
# Pic d'erreurs : seuil atteint sur la fenêtre glissante.
MONITOR_ERROR_WINDOW_MINUTES: float = _env_float("MONITOR_ERROR_WINDOW_MINUTES", 15.0)
MONITOR_ERROR_ALERT_THRESHOLD: int = _env_int("MONITOR_ERROR_ALERT_THRESHOLD", 10)
# Marge accordée à une tâche avant de la considérer comme arrêtée.
MONITOR_TASK_GRACE_MINUTES: float = _env_float("MONITOR_TASK_GRACE_MINUTES", 10.0)
# Latence Discord (ms) au-delà de laquelle la connexion est signalée comme dégradée.
MONITOR_LATENCY_WARN_MS: int = _env_int("MONITOR_LATENCY_WARN_MS", 1000)


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
# Les seuils par défaut sont les niveaux d'urgence de l'identité visuelle.
LAST_DAY_HOURS: float = _env_float("LAST_DAY_HOURS", design.WARNING_HOURS)
LAST_HOURS_THRESHOLD: float = _env_float("LAST_HOURS_THRESHOLD", design.URGENT_HOURS)


# ---------- Offres exceptionnelles ----------

# Une offre est mise en avant « 🔥 Offre exceptionnelle » quand c'est un jeu complet,
# temporaire, et dont la valeur explicitement libellée en euros atteint ce seuil.
# Les valeurs non libellées en euros ne comptent jamais : rien n'est inventé.
# Mettre 0 pour désactiver la mise en avant.
MEGA_DEAL_MIN_WORTH_EUR: float = _env_float("MEGA_DEAL_MIN_WORTH_EUR", 19.99)


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
        Platform("steam", "Steam", ("steam",), "🔵", design.rgb(design.PLATFORM_COLOURS["steam"])),
        Platform(
            "epic", "Epic Games Store", ("epic games",), "⚪", design.rgb(design.PLATFORM_COLOURS["epic"])
        ),
        Platform("gog", "GOG", ("gog",), "🟣", design.rgb(design.PLATFORM_COLOURS["gog"])),
        Platform(
            "ubisoft", "Ubisoft", ("ubisoft",), "🔷", design.rgb(design.PLATFORM_COLOURS["ubisoft"])
        ),
    )
}
PLATFORM_KEYS = list(PLATFORMS)

# Utilisés quand la plateforme d'un jeu n'est pas reconnue : la couleur par défaut
# est la couleur principale de la marque (voir utils/design.py), jamais une couleur
# de plateforme.
DEFAULT_EMOJI = "🎁"
DEFAULT_COLOUR = design.rgb(design.PRIMARY)


# ---------- Tableau de bord web ----------

DASHBOARD_ENABLED: bool = _env_bool("DASHBOARD_ENABLED", False)
DASHBOARD_HOST: str = _env_str("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT: int = _env_int("DASHBOARD_PORT", 8080)
DASHBOARD_SECRET_KEY: str = _env_str("DASHBOARD_SECRET_KEY", "change-me-in-prod")
DASHBOARD_BASE_URL: str = _env_str("DASHBOARD_BASE_URL", f"http://localhost:{DASHBOARD_PORT}")

# Cookies « Secure » par défaut dès que l'URL publique est en HTTPS (donc automatiquement en
# production normale) ; surchargeable explicitement si un proxy termine le TLS en amont.
DASHBOARD_COOKIE_SECURE: bool = _env_bool(
    "DASHBOARD_COOKIE_SECURE", DASHBOARD_BASE_URL.strip().lower().startswith("https://")
)

DISCORD_CLIENT_ID: str = _env_str("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET: str = _env_str("DISCORD_CLIENT_SECRET")
DISCORD_OAUTH_REDIRECT_URI: str = _env_str(
    "DISCORD_OAUTH_REDIRECT_URI", f"{DASHBOARD_BASE_URL}/auth/callback"
)
DISCORD_API_BASE_URL: str = _env_str("DISCORD_API_BASE_URL", "https://discord.com/api")

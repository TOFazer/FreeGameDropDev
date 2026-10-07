"""Séparation DEV / PROD : un environnement identifié, un démarrage vérifié.

Le développement et la production utilisent le même code, mais jamais les mêmes
ressources : un jeton de production ne doit pas partir depuis l'instance de
développement, et une base de développement ne doit pas recevoir les annonces de la
production. Ce module fournit les briques du garde-fou, et **rien d'autre** :

1. `ENVIRONMENT` déclare l'environnement de l'instance ; `EXPECTED_ENVIRONMENT`
   déclare celui qui était attendu. Les deux doivent concorder, sinon le bot refuse
   de démarrer (c'est le cas d'un `.env` de production posé dans le dossier de dev).
2. `DISCORD_APPLICATION_ID` et `DISCORD_CLIENT_ID` sont comparés à l'identifiant
   d'application encodé dans le jeton Discord : le jeton doit appartenir à la même
   application Discord que le reste de la configuration (`application_id_from_token`).
   Le contrôle est local, sans le moindre appel réseau.
3. `DB_PATH` ne doit pas désigner la base de l'autre environnement (« prod » en
   développement, « dev » en production).

Aucune de ces vérifications ne choisit le jeton à la place de l'opérateur : le jeton
vient toujours de `DISCORD_TOKEN` dans `.env`. Elles vérifient seulement que ce jeton
et le reste de la configuration parlent bien du même environnement.

Le module n'importe pas `config` au chargement (seulement dans `current()`, à
l'appel) : les fonctions reçoivent des valeurs et rendent un verdict, ce qui les rend
testables sans variable d'environnement.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass

DEVELOPMENT = "development"
PRODUCTION = "production"
KNOWN_ENVIRONMENTS = (DEVELOPMENT, PRODUCTION)

#: « DEV », « dev », « develop » désignent tous l'environnement de développement.
_ALIASES = {
    "dev": DEVELOPMENT,
    "develop": DEVELOPMENT,
    "development": DEVELOPMENT,
    "prod": PRODUCTION,
    "production": PRODUCTION,
}

EMOJI = {DEVELOPMENT: "🧪", PRODUCTION: "🚀"}
LABEL = {DEVELOPMENT: "Development", PRODUCTION: "Production"}
TAG = {DEVELOPMENT: "DEV", PRODUCTION: "PROD"}

#: Morceaux de nom de fichier qui trahissent la base de l'autre environnement.
_PROD_DB_HINTS = ("prod",)
_DEV_DB_HINTS = ("dev", "test")

#: Nom du fichier SQLite livré par défaut en production (voir `.env.example`).
PRODUCTION_DEFAULT_DB = "bot.db"
#: Nom du fichier SQLite livré par défaut en développement.
DEVELOPMENT_DEFAULT_DB = "data/freegamedrop-dev.db"


def normalize(value: str | None) -> str:
    """« DEV », « dev » et « development » désignent le même environnement.

    Une valeur inconnue est renvoyée telle quelle (en minuscules) : le garde-fou
    pourra ainsi dire précisément ce qui ne va pas au lieu de l'ignorer.
    """
    text = (value or "").strip().lower()
    return _ALIASES.get(text, text)


def is_development(environment: str | None) -> bool:
    return normalize(environment) == DEVELOPMENT


def current() -> str:
    """Environnement déclaré par la configuration chargée (`.env`)."""
    import config  # import tardif : évite un cycle config -> utils.environment

    return normalize(getattr(config, "ENVIRONMENT", PRODUCTION))


# ---------- Identité affichée ----------


def log_prefix(environment: str | None = None) -> str:
    """Préfixe des journaux : `[DEVELOPMENT]` / `[PRODUCTION]`."""
    return f"[{normalize(environment or current()).upper()}]"


def describe(environment: str | None = None) -> str:
    """Libellé lisible : « 🧪 Development », « 🚀 Production »."""
    key = normalize(environment or current())
    if key in KNOWN_ENVIRONMENTS:
        return f"{EMOJI[key]} {LABEL[key]}"
    return f"⚠️ {key or 'inconnu'}"


def emoji_of(environment: str | None = None) -> str:
    """Emoji de l'environnement : 🧪 en développement, 🚀 en production."""
    return EMOJI.get(normalize(environment or current()), "⚠️")


def label_of(environment: str | None = None) -> str:
    """Nom de l'environnement, tel qu'affiché dans `/info` et le tableau de bord."""
    return LABEL.get(normalize(environment or current()), "Inconnu")


def product_name(environment: str | None = None) -> str:
    """Nom public : « FreeGameDrop » en production, « FreeGameDrop DEV » en développement."""
    return "FreeGameDrop DEV" if is_development(environment or current()) else "FreeGameDrop"


def page_title(title: str, environment: str | None = None) -> str:
    """Titre du tableau de bord, impossible à confondre entre DEV et PROD."""
    key = normalize(environment or current())
    if key not in KNOWN_ENVIRONMENTS:
        return title
    if is_development(key):
        return f"{EMOJI[key]} {title.replace('FreeGameDrop', 'FreeGameDrop DEV')}"
    return title


# ---------- Contrôles ----------


def _as_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def application_id_from_token(token: str | None) -> int | None:
    """Identifiant d'application encodé dans la première partie d'un jeton Discord.

    Un jeton de bot s'écrit `base64(application_id).secret.checksum` : on peut donc
    savoir à quelle application Discord il appartient **sans aucun appel réseau**.
    Retourne `None` si le jeton n'a pas cette forme (jeton tronqué ou factice).
    """
    first = (token or "").split(".", 1)[0].strip()
    if not first:
        return None
    padded = first + "=" * (-len(first) % 4)
    try:
        text = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return int(text) if text.isdigit() else None


@dataclass(frozen=True)
class EnvironmentCheck:
    """Verdict du garde-fou : `errors` bloque le démarrage, `warnings` avertit."""

    environment: str
    expected: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def refusal_message(self) -> str:
        """Message unique lisible, à écrire avant de couper le processus."""
        return (
            f"{EMOJI.get(self.environment, '⚠️')} "
            f"{LABEL.get(self.environment, self.environment or 'inconnu')} bot refused to start "
            f"({len(self.errors)} erreur(s) de configuration)."
        )


def check(
    *,
    environment: str,
    expected: str = "",
    token: str = "",
    application_id: int | str | None = None,
    client_id: int | str | None = None,
    db_path: str = "",
) -> EnvironmentCheck:
    """Compare la configuration à l'environnement déclaré et rend un verdict.

    Les paramètres sont explicites (aucune lecture de `config`) : le même appel sert
    au démarrage réel et aux tests, sans variable d'environnement à manipuler.
    """
    key = normalize(environment)
    expected_key = normalize(expected)
    errors: list[str] = []
    warnings: list[str] = []

    if key not in KNOWN_ENVIRONMENTS:
        errors.append(
            f"❌ ENVIRONMENT={environment or '(vide)'} inconnu : écris development ou production."
        )

    if expected_key and expected_key != key:
        errors.append(
            f"❌ Environment mismatch : ENVIRONMENT={key or '(vide)'} mais "
            f"EXPECTED_ENVIRONMENT={expected or '(vide)'}."
        )
    elif not expected_key and key in KNOWN_ENVIRONMENTS:
        warnings.append(
            "⚠️ EXPECTED_ENVIRONMENT n'est pas défini : le contrôle de cohérence d'environnement "
            "est incomplet (ajoute EXPECTED_ENVIRONMENT=" + key + ")."
        )

    token_application = application_id_from_token(token)
    declared_application = _as_int(application_id)
    oauth_application = _as_int(client_id)

    if token and token_application is None:
        warnings.append(
            "⚠️ Jeton Discord illisible : impossible de vérifier l'application dont il dépend."
        )
    elif token_application is not None:
        if declared_application is None:
            warnings.append(
                "⚠️ DISCORD_APPLICATION_ID absent : le jeton n'est pas rattaché à une application "
                "déclarée (ajoute l'identifiant de l'application Discord de cet environnement)."
            )
        elif declared_application != token_application:
            errors.append(
                f"❌ Discord application mismatch : le jeton appartient à l'application "
                f"{token_application} alors que DISCORD_APPLICATION_ID={declared_application} "
                f"est attendu pour l'environnement {key or '(inconnu)'}."
            )
        if oauth_application is not None and oauth_application != token_application:
            errors.append(
                f"❌ Discord application mismatch : DISCORD_CLIENT_ID={oauth_application} ne "
                f"correspond pas au jeton (application {token_application}) ; le tableau de bord "
                "et le bot doivent utiliser la même application Discord."
            )

    # En développement, tout le chemin est examiné : « data/freegamedrop-prod.db » ou
    # « /srv/freegamedrop-prod/… » désignent sans ambiguïté la base de production.
    # En production, seul le nom du fichier compte : un dossier parent nommé « dev » ou
    # « test » (utilisateur, machine de staging promue…) ne doit pas bloquer un
    # déploiement légitime.
    low_path = (db_path or "").replace("\\", "/").lower()
    file_name = low_path.rstrip("/").rsplit("/", 1)[-1]
    if key == DEVELOPMENT:
        if any(hint in low_path for hint in _PROD_DB_HINTS):
            errors.append(
                f"❌ Refus de démarrer en développement sur une base de production : "
                f"DB_PATH={db_path}."
            )
        elif db_path.strip() == PRODUCTION_DEFAULT_DB:
            warnings.append(
                f"⚠️ DB_PATH={db_path} est le fichier SQLite livré par défaut en production ; "
                f"en développement, préfère {DEVELOPMENT_DEFAULT_DB}."
            )
    elif key == PRODUCTION and any(hint in file_name for hint in _DEV_DB_HINTS):
        errors.append(
            f"❌ Refus de démarrer en production sur une base de développement : "
            f"DB_PATH={db_path} (nom de fichier « {file_name} »)."
        )

    return EnvironmentCheck(
        environment=key, expected=expected_key, errors=tuple(errors), warnings=tuple(warnings)
    )


def verify_startup(settings) -> EnvironmentCheck:
    """Applique `check` à la configuration chargée, journalise et refuse si besoin.

    `settings` est le module `config` (ou tout objet exposant les mêmes attributs),
    ce qui permet de tester le garde-fou avec une configuration bidon.
    """
    from utils.logging_setup import log_event

    result = check(
        environment=getattr(settings, "ENVIRONMENT", ""),
        expected=getattr(settings, "EXPECTED_ENVIRONMENT", ""),
        token=getattr(settings, "DISCORD_TOKEN", ""),
        application_id=getattr(settings, "DISCORD_APPLICATION_ID", None),
        client_id=getattr(settings, "DISCORD_CLIENT_ID", ""),
        db_path=getattr(settings, "DB_PATH", ""),
    )

    log = logging.getLogger("utils.environment")
    for warning in result.warnings:
        log.warning("%s %s", log_prefix(result.environment), warning)

    if result.ok:
        log_event(
            "environment.checked",
            environment=result.environment,
            expected=result.expected or result.environment,
            warnings=len(result.warnings),
        )
        return result

    for error in result.errors:
        log.critical("%s %s", log_prefix(result.environment), error)
    log_event(
        "environment.refused",
        level=logging.CRITICAL,
        environment=result.environment,
        expected=result.expected or "(non défini)",
        errors=len(result.errors),
    )
    log.critical("%s %s", log_prefix(result.environment), result.refusal_message())
    raise EnvironmentRefused(result)


class EnvironmentRefused(RuntimeError):
    """Configuration incohérente avec l'environnement déclaré : démarrage interdit."""

    def __init__(self, result: EnvironmentCheck):
        super().__init__(result.refusal_message())
        self.result = result


# ---------- Journaux de démarrage ----------


def log_start(
    logger: logging.Logger,
    *,
    db_path: str = "",
    application_id: int | str | None = None,
    maintenance: bool = False,
    environment: str | None = None,
) -> None:
    """Bandeau de démarrage : on doit voir l'environnement dans les toutes premières lignes."""
    key = environment or current()
    prefix = log_prefix(key)
    logger.info("%s FreeGameDrop starting...", prefix)
    logger.info("%s Environment: %s", prefix, describe(key))
    if db_path:
        log_database(logger, db_path=db_path, environment=key)
    if application_id:
        logger.info("%s Discord application: %s", prefix, application_id)
    logger.info("%s Maintenance mode: %s", prefix, "ON" if maintenance else "off")


def log_database(logger: logging.Logger, *, db_path: str, environment: str | None = None) -> None:
    """Rappelle le fichier SQLite réellement utilisé (DEV et PROD n'y touchent pas ensemble)."""
    logger.info("%s Database: %s", log_prefix(environment), db_path)


def log_connected(
    logger: logging.Logger,
    *,
    user=None,
    guilds: int | None = None,
    environment: str | None = None,
) -> None:
    """Confirme l'environnement au moment où la connexion Discord est établie."""
    prefix = log_prefix(environment)
    logger.info("%s Discord bot connected as %s", prefix, user)
    if guilds is not None:
        logger.info("%s Servers: %s", prefix, guilds)


def log_maintenance(logger: logging.Logger, environment: str | None = None) -> None:
    """Annonce le mode maintenance : les annonces automatiques sont suspendues."""
    key = environment or current()
    logger.info(
        "%s %s",
        log_prefix(key),
        f"{EMOJI.get(key, '⚠️')} {product_name(key)} est en maintenance : "
        "les annonces automatiques sont suspendues.",
    )

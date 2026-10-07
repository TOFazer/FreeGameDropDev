"""Journalisation sûre : un journal de bord utile, sans secret dedans.

Le journal sert à répondre à une question simple : « pourquoi cette offre n'est
pas arrivée ? ». Il doit donc raconter les étapes (appel de source, offre
détectée, doublon ignoré, alerte envoyée) sans jamais écrire :

- de token, de mot de passe ni de clé d'API ;
- d'adresse e-mail ;
- de contenu de message Discord ni de donnée personnelle inutile.

Deux mécanismes complémentaires :

1. `RedactionFilter` / `RedactingFormatter` masquent les secrets *avant*
   l'écriture, y compris ceux qui apparaissent dans une trace d'exception : toute
   valeur des variables sensibles (`DISCORD_TOKEN`, `DISCORD_CLIENT_SECRET`,
   `DASHBOARD_SECRET_KEY`) est remplacée par `***`, ainsi que les motifs connus
   (jeton de bot, `Authorization: Bearer …`, URL de webhook, `code=` OAuth2) ;
2. `log_event()` produit des lignes `event=… clé=valeur` stables, faciles à
   filtrer avec `grep`, et tronquées pour ne pas déverser de gros contenus.

Les identifiants Discord ne sont pas des secrets : ils servent au diagnostic
(« le membre X n'a pas reçu l'alerte »). `LOG_PSEUDONYMIZE_IDS=true` les
remplace par une empreinte stable si tu préfères ne pas les écrire du tout.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from datetime import date, datetime
from logging.handlers import RotatingFileHandler

import config

MASK = "***"

# Marque les gestionnaires installés par `configure_logging` (pour ne pas doubler
# les lignes si la fonction est appelée deux fois).
HANDLER_FLAG = "_freegamedrop_handler"

# Champs dont la valeur est un identifiant Discord : pseudonymisables.
PERSONAL_ID_KEYS = frozenset(
    {
        "user",
        "user_id",
        "member",
        "member_id",
        "owner_id",
        "author_id",
        "guild",
        "guild_id",
    }
)

# Variables d'environnement dont la valeur ne doit jamais apparaître.
SECRET_ENV_NAMES = ("DISCORD_TOKEN", "DISCORD_CLIENT_SECRET", "DASHBOARD_SECRET_KEY")

_TOKEN_PATTERNS = (
    # Jeton de bot Discord : xxx.yyy.zzz (deux ou trois segments, très longs).
    re.compile(r"\b[MNO][A-Za-z0-9_-]{20,}\.[\w-]{5,}\.[\w-]{20,}\b"),
    re.compile(r"\b[\w-]{20,}\.[\w-]{5,}\.[\w-]{20,}\b"),
)
_KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b(token|secret|password|passwd|mot\s+de\s+passe|api[-_ ]?key|client[-_ ]?secret)\b"
    r"\s*[:=]\s*(\"[^\"]*\"|'[^']*'|\S+)"
)
_AUTHORIZATION_PATTERN = re.compile(r"(?i)\bauthorization\b\s*[:=]\s*(?:bearer\s+)?\S+")
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[\w.\-]{8,}")
_WEBHOOK_PATTERN = re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\S+")
_OAUTH_CODE_PATTERN = re.compile(r"(?i)\b(code|state)=([\w.\-]{8,})")
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")


def redact(value):
    """Masque les secrets et données personnelles d'un texte (ou d'une structure)."""
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        cleaned = [redact(item) for item in value]
        return tuple(cleaned) if isinstance(value, tuple) else cleaned
    return value


def _redact_text(text: str) -> str:
    if not text:
        return text
    for name in SECRET_ENV_NAMES:
        secret = getattr(config, name, "") or ""
        if len(secret) >= 8:
            text = text.replace(secret, MASK)
    text = _WEBHOOK_PATTERN.sub(MASK, text)
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(MASK, text)
    text = _KEY_VALUE_PATTERN.sub(lambda m: f"{m.group(1)}={MASK}", text)
    text = _AUTHORIZATION_PATTERN.sub(f"authorization={MASK}", text)
    text = _BEARER_PATTERN.sub(f"bearer {MASK}", text)
    text = _OAUTH_CODE_PATTERN.sub(lambda m: f"{m.group(1)}={MASK}", text)
    text = _EMAIL_PATTERN.sub(MASK, text)
    return text


class RedactionFilter(logging.Filter):
    """Nettoie le message et ses arguments avant qu'un gestionnaire ne les écrive."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = redact(record.args)
        return True


class RedactingFormatter(logging.Formatter):
    """Filet de sécurité : masque aussi ce qui vient d'une trace d'exception."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def identifier(value, *, kind: str = "id") -> str:
    """Identifiant Discord lisible, ou empreinte stable si `LOG_PSEUDONYMIZE_IDS`."""
    text = str(value)
    if not getattr(config, "LOG_PSEUDONYMIZE_IDS", False):
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return f"{kind}_{digest}"


def configure_logging(level_name: str = "INFO", *, log_file: str | None = None, stream=None):
    """Installe la sortie standard (et, en option, un fichier) sans secret.

    `discord.py` journalise via `discord.*`, qui remonte à la racine : un seul
    gestionnaire suffit donc pour tout le bot.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, str(level_name).upper(), logging.INFO))

    for handler in list(root.handlers):
        if getattr(handler, HANDLER_FLAG, False):
            root.removeHandler(handler)

    formatter = RedactingFormatter(
        "%(asctime)s %(levelname)-8s %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RedactionFilter())
    setattr(handler, HANDLER_FLAG, True)
    root.addHandler(handler)

    file_name = log_file if log_file is not None else getattr(config, "LOG_FILE", "")
    if file_name:
        file_handler = RotatingFileHandler(
            file_name, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(RedactionFilter())
        setattr(file_handler, HANDLER_FLAG, True)
        root.addHandler(file_handler)
    return root


# ---------- Journal d'événements ----------

EVENT_LOGGER_NAME = "freegamedrop.events"

_event_logger = logging.getLogger(EVENT_LOGGER_NAME)


def _format_field(key: str, value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return f"{key}={'true' if value else 'false'}"
    if key in PERSONAL_ID_KEYS:
        return f"{key}={identifier(value, kind='guild' if key.startswith('guild') else 'user')}"
    if isinstance(value, (int, float)):
        return f"{key}={value}"
    if isinstance(value, (datetime, date)):
        return f"{key}={value.isoformat()}"
    text = str(value)
    limit = getattr(config, "LOG_MAX_FIELD_CHARS", 160)
    if len(text) > limit:
        text = text[:limit] + "…"
    text = _redact_text(text)
    if not text:
        return None
    if any(character.isspace() for character in text):
        text = '"' + text.replace('"', "'") + '"'
    return f"{key}={text}"


def format_event(event: str, fields: dict | None = None) -> str:
    """Rend une ligne `event=… clé=valeur` (champs triés : plus simple à filtrer)."""
    parts = [f"event={event}"]
    for key in sorted(fields or {}):
        rendered = _format_field(key, (fields or {})[key])
        if rendered is not None:
            parts.append(rendered)
    return " ".join(parts)


def log_event(event_name: str, level: int = logging.INFO, **fields) -> None:
    """Écrit un événement du journal de bord (jamais de secret, jamais de contenu brut).

    Le premier argument s'appelle `event_name` pour laisser `event=` disponible
    comme champ (`log_event("alert.sent", event="new_offer", user_id=…)`).
    """
    _event_logger.log(level, format_event(event_name, fields))

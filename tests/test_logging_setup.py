"""Journal de bord : utile pour diagnostiquer, inutilisable pour voler un secret."""

import io
import logging

import config
from utils import logging_setup


def _jeton_factice(prefixe="M", corps="a", milieu="b", fin="c"):
    """Jeton de test construit à la volée.

    Un faux jeton écrit en clair a exactement la forme d'un vrai : la protection
    anti-secrets de GitHub bloque alors le push. On garde donc la forme attendue
    (`xxx.yyyyyy.zzzz…`) sans écrire de valeur qui y ressemble dans le fichier.
    """
    return f"{prefixe}{corps * 23}.{milieu * 6}.{fin * 28}"


TOKEN_BOT = _jeton_factice()
TOKEN_CACHE = _jeton_factice(prefixe="N", corps="z", milieu="y", fin="x")


def test_un_jeton_de_bot_ne_sort_jamais_dun_log():
    texte = f"connexion avec {TOKEN_BOT} refusée"

    resultat = logging_setup.redact(texte)

    assert TOKEN_BOT not in resultat
    assert logging_setup.MASK in resultat


def test_les_valeurs_de_configuration_sensibles_sont_masquees(monkeypatch):
    monkeypatch.setattr(config, "DISCORD_TOKEN", "un-token-de-test-tres-long")
    monkeypatch.setattr(config, "DASHBOARD_SECRET_KEY", "une-cle-de-test-tres-longue")

    resultat = logging_setup.redact(
        "token=un-token-de-test-tres-long et secret: une-cle-de-test-tres-longue"
    )

    assert "un-token-de-test-tres-long" not in resultat
    assert "une-cle-de-test-tres-longue" not in resultat


def test_les_mots_de_passe_et_auths_sont_masques():
    resultat = logging_setup.redact(
        "password=hunter2 Authorization: Bearer abcdef123456 code=abcdef123456"
    )

    assert "hunter2" not in resultat
    assert "abcdef123456" not in resultat
    assert resultat.count(logging_setup.MASK) >= 3


def test_les_urls_de_webhook_et_emails_sont_masques():
    texte = (
        "envoi vers https://discord.com/api/webhooks/123/abcdef "
        "depuis contact@example.org"
    )

    resultat = logging_setup.redact(texte)

    assert "webhooks/123" not in resultat
    assert "contact@example.org" not in resultat


def test_le_filtre_protege_aussi_les_arguments_dun_log():
    flux = io.StringIO()
    handler = logging.StreamHandler(flux)
    handler.setFormatter(logging_setup.RedactingFormatter("%(message)s"))
    handler.addFilter(logging_setup.RedactionFilter())
    logger = logging.getLogger("test.secrets")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("envoi du token %s au serveur", TOKEN_BOT)
    finally:
        logger.removeHandler(handler)

    assert TOKEN_BOT not in flux.getvalue()
    assert logging_setup.MASK in flux.getvalue()


def test_une_trace_dexception_est_nettoyee():
    flux = io.StringIO()
    handler = logging.StreamHandler(flux)
    handler.setFormatter(logging_setup.RedactingFormatter("%(message)s", "%(message)s"))
    handler.addFilter(logging_setup.RedactionFilter())
    logger = logging.getLogger("test.exceptions")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        try:
            raise RuntimeError(f"réponse 401 pour le token {TOKEN_BOT}")
        except RuntimeError:
            logger.exception("échec de la requête %s", "https://discord.com/api/webhooks/1/secret")
    finally:
        logger.removeHandler(handler)

    sortie = flux.getvalue()
    assert TOKEN_BOT not in sortie
    assert "webhooks/1/secret" not in sortie


def test_un_evenement_est_lisible_et_trie():
    ligne = logging_setup.format_event(
        "source.failure", {"source": "epic", "error": "délai d'attente dépassé", "attempt": 2}
    )

    assert ligne.startswith("event=source.failure ")
    assert "attempt=2" in ligne
    assert 'error="délai' in ligne


def test_les_valeurs_trop_longues_sont_tronquees(monkeypatch):
    monkeypatch.setattr(config, "LOG_MAX_FIELD_CHARS", 20)

    ligne = logging_setup.format_event("offer.detected", {"title": "x" * 200})

    assert len(ligne) < 60
    assert ligne.endswith("…")


def test_les_champs_vides_sont_ignores():
    ligne = logging_setup.format_event("check.finished", {"announcements": 0, "détail": None})

    assert ligne == "event=check.finished announcements=0"


def test_les_identifiants_sont_lisibles_par_defaut():
    ligne = logging_setup.format_event("alert.sent", {"user_id": 123456789012345678})

    assert "user_id=123456789012345678" in ligne


def test_les_identifiants_peuvent_etre_pseudonymises(monkeypatch):
    monkeypatch.setattr(config, "LOG_PSEUDONYMIZE_IDS", True)

    ligne = logging_setup.format_event("alert.sent", {"user_id": 123456789012345678})

    assert "123456789012345678" not in ligne
    assert "user_id=user_" in ligne


def test_la_pseudonymisation_est_stable():
    assert logging_setup.identifier(42, kind="user") == logging_setup.identifier(42, kind="user")


def test_configure_logging_installe_un_seul_gestionnaire():
    racine = logging.getLogger()
    anciens = list(racine.handlers)
    ancien_niveau = racine.level
    try:
        logging_setup.configure_logging("INFO", log_file="", stream=io.StringIO())
        logging_setup.configure_logging("INFO", log_file="", stream=io.StringIO())
        installes = [
            handler for handler in racine.handlers if getattr(handler, logging_setup.HANDLER_FLAG, False)
        ]
        assert len(installes) == 1
        assert racine.level == logging.INFO
    finally:
        for handler in list(racine.handlers):
            if handler not in anciens:
                racine.removeHandler(handler)
        for handler in anciens:
            if handler not in racine.handlers:
                racine.addHandler(handler)
        racine.setLevel(ancien_niveau)

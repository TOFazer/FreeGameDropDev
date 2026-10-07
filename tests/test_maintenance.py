"""Mode maintenance : suspendre les annonces automatiques sans casser le bot.

`MAINTENANCE_MODE=true` sert pendant les essais : la veille automatique ne publie
plus rien, alors que les commandes d'administration (dont `/test-jeux`) restent
utilisables pour vérifier une configuration.
"""

import logging

import config
from utils import environment


async def test_la_veille_automatique_est_suspendue_en_maintenance(cog, monkeypatch):
    appels = []

    async def verifier(*args, **kwargs):
        appels.append(args)

    monkeypatch.setattr(cog, "run_check", verifier)
    monkeypatch.setattr(config, "MAINTENANCE_MODE", True)

    await cog.check_games()

    assert appels == [], "aucune vérification ne doit partir en mode maintenance"


async def test_la_veille_automatique_repart_hors_maintenance(cog, monkeypatch):
    appels = []

    async def verifier(*args, **kwargs):
        appels.append(args)
        return 0

    monkeypatch.setattr(cog, "run_check", verifier)
    monkeypatch.setattr(config, "MAINTENANCE_MODE", False)

    await cog.check_games()

    assert len(appels) == 1


async def test_une_verification_manuelle_reste_possible_en_maintenance(cog, monkeypatch):
    """`/test-jeux` doit continuer de fonctionner : c'est tout l'intérêt du mode."""
    appels = []

    async def verifier(*, target_guild_id=None):
        appels.append(target_guild_id)
        return 1

    monkeypatch.setattr(cog, "_run_check_once", verifier)
    monkeypatch.setattr(config, "MAINTENANCE_MODE", True)

    assert await cog.run_check() == 1
    assert appels == [None]


async def test_la_suspension_est_journalisee(cog, monkeypatch, caplog):
    monkeypatch.setattr(config, "MAINTENANCE_MODE", True)

    with caplog.at_level(logging.INFO):
        await cog.check_games()

    assert "event=check.skipped" in caplog.text
    assert "maintenance" in caplog.text


async def test_le_mode_maintenance_est_annonce_au_demarrage(caplog):
    with caplog.at_level(logging.INFO):
        environment.log_maintenance(logging.getLogger("test"), "development")

    assert "maintenance" in caplog.text
    assert "[DEVELOPMENT]" in caplog.text


def test_le_mode_maintenance_est_desactive_par_defaut():
    assert config.MAINTENANCE_MODE is False

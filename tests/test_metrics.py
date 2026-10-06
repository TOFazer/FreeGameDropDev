"""Indicateurs d'usage pour les développeurs."""

from types import SimpleNamespace

from utils import metrics


def _bot(guilds, latency=0.05):
    return SimpleNamespace(guilds=guilds, latency=latency)


def test_guild_et_membres_comptes():
    bot = _bot([SimpleNamespace(member_count=10), SimpleNamespace(member_count=5)])

    assert metrics.guild_count(bot) == 2
    assert metrics.member_count(bot) == 15


def test_membres_manquants_comptes_comme_zero():
    bot = _bot([SimpleNamespace(member_count=None), SimpleNamespace()])

    assert metrics.member_count(bot) == 0


async def test_construction_des_statistiques_developpeur(db):
    await db.save_giveaways([{"id": 1, "title": "Jeu", "source": "gamerpower"}])
    bot = _bot([SimpleNamespace(member_count=42)])

    stats = await metrics.build_dev_stats(bot)

    assert stats["guilds"] == 1
    assert stats["members"] == 42
    assert stats["total_offers"] == 1
    assert stats["latency_ms"] == 50


async def test_latence_nan_devient_none(db):
    bot = _bot([], latency=float("nan"))

    stats = await metrics.build_dev_stats(bot)

    assert stats["latency_ms"] is None


def test_rendu_texte_des_statistiques():
    texte = metrics.format_dev_stats_text(
        {
            "guilds": 3,
            "members": 100,
            "total_offers": 50,
            "offers_last_30_days": 10,
            "total_favorites": 7,
            "members_with_favorites": 4,
            "configured_guilds": 2,
            "known_guilds": 3,
            "offers_by_source": {"epic": 5, "gamerpower": 45},
        }
    )

    assert "Serveurs : 3" in texte
    assert "Par source : epic: 5, gamerpower: 45" in texte

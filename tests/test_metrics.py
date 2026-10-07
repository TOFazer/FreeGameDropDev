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


# ---------- Statistiques publiques (/stats) ----------


from datetime import datetime, timedelta, timezone  # noqa: E402


def _public_bot():
    return SimpleNamespace(user=SimpleNamespace(id=999), guilds=[SimpleNamespace()], latency=0.05)


async def test_stats_publiques_comptent_les_offres_actives(db):
    future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    passee = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    await db.save_giveaways(
        [
            {"id": 1, "title": "En cours", "worth": "19,99 €", "end_date": future},
            {"id": 2, "title": "Terminée", "worth": "10,00 €", "end_date": passee},
            {"id": 3, "title": "Sans date", "worth": "N/A"},
        ]
    )

    stats = await metrics.build_public_stats(_public_bot())

    assert stats["guilds"] == 1
    assert stats["total_offers"] == 3
    assert stats["active_offers"] == 2  # future + sans date, pas l'offre terminée
    assert stats["known_value_eur"] == 29.99  # seules les valeurs en euros comptent


async def test_stats_publiques_rennvoient_la_derniere_verification(db):
    hier = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    await db.set_bot_state("last_check_at", hier)

    stats = await metrics.build_public_stats(_public_bot())

    assert stats["last_check_at"] is not None
    assert abs((stats["last_check_at"] - datetime.fromisoformat(hier)).total_seconds()) < 1


async def test_stats_publiques_sans_verification(db):
    stats = await metrics.build_public_stats(_public_bot())

    assert stats["last_check_at"] is None
    assert stats["platforms_watched"] == 4
    assert "gamerpower" in stats["sources"]


def test_rendu_de_la_derniere_verification():
    maintenant = datetime.now(timezone.utc)

    assert metrics.format_last_check(None) == "pas encore vérifié"
    assert metrics.format_last_check(maintenant) == "à l'instant"
    assert metrics.format_last_check(maintenant - timedelta(minutes=3)) == "il y a 3 min"
    assert metrics.format_last_check(maintenant - timedelta(hours=5)) == "il y a 5 h"
    assert metrics.format_last_check(maintenant - timedelta(days=2)) == "il y a 2 j"


async def test_commande_stats_affiche_un_embed_public(db):
    from cogs.setup import Setup, build_stats_embed
    from utils import branding

    class FakeResponse:
        def __init__(self):
            self.sent = None

        async def send_message(self, *args, **kwargs):
            self.sent = (args, kwargs)

    class FakeInteraction:
        def __init__(self):
            self.response = FakeResponse()

    cog = Setup(_public_bot())
    interaction = FakeInteraction()

    await Setup.stats.callback(cog, interaction)

    stats = await metrics.build_public_stats(_public_bot())
    attendu = build_stats_embed(cog.bot, stats)
    args, kwargs = interaction.response.sent
    embed = args[0] if args else kwargs["embed"]
    assert embed.title == attendu.title
    assert embed.url == branding.build_invite_url(999)
    assert "Offres détectées" in embed.fields[0].name
    assert "FreeGameDrop" in embed.footer.text
    assert "ephemeral" not in kwargs  # statistiques publiques, partageables


async def test_etat_bot_enregistre_et_relit(db):
    await db.set_bot_state("last_check_at", "2026-10-07T10:00:00+00:00")

    assert await db.get_bot_state("last_check_at") == "2026-10-07T10:00:00+00:00"
    assert await db.get_bot_state("inconnu") is None

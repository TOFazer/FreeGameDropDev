"""Annonces : bon salon, bonne mention, jamais deux fois."""

import discord
import pytest

import config
from services import gamerpower

STEAM = {"id": 1, "title": "Jeu Steam", "platforms": "PC (Steam)", "worth": "10.00"}
EPIC = {"id": 2, "title": "Jeu Epic", "platforms": "Epic Games Store"}
AUTRE = {"id": 3, "title": "Jeu itch", "platforms": "itch.io"}


@pytest.fixture
def serveur_configure(guild, db, fakes, monkeypatch):
    """Un serveur avec un salon + un rôle pour Steam et pour Epic."""

    async def _configure(jeux):
        category = fakes.Category(guild, "🎮 Jeux gratuits")
        guild.categories.append(category)
        salons = {}
        for key, channel_id, role_id in (("steam", 10, 20), ("epic", 11, 21)):
            channel = fakes.Channel(f"jeux-{key}", category, channel_id=channel_id)
            category.channels.append(channel)
            salons[key] = channel
            await db.set_platform_channel(guild.id, key, channel_id)
            await db.set_platform_role(guild.id, key, role_id)

        async def faux_appel_api():
            return jeux

        monkeypatch.setattr(gamerpower, "fetch_giveaways", faux_appel_api)
        return salons

    return _configure


async def test_chaque_jeu_part_dans_le_bon_salon(cog, serveur_configure):
    salons = await serveur_configure([STEAM, EPIC, AUTRE])

    envoyes = await cog.run_check()

    assert envoyes == 2
    assert len(salons["steam"].sent) == 1 and len(salons["epic"].sent) == 1
    assert salons["steam"].sent[0]["embed"].title == "🔵 Jeu Steam"
    assert salons["steam"].sent[0]["content"] == "<@&20> nouveau jeu gratuit !"
    assert salons["epic"].sent[0]["content"] == "<@&21> nouveau jeu gratuit !"


async def test_un_jeu_nest_pas_annonce_deux_fois(cog, serveur_configure):
    salons = await serveur_configure([STEAM])

    assert await cog.run_check() == 1
    assert await cog.run_check() == 0
    assert len(salons["steam"].sent) == 1


async def test_reset_jeux_permet_de_rejouer(cog, serveur_configure, db, guild):
    await serveur_configure([STEAM])
    await cog.run_check()

    await db.clear_sent(guild.id)

    assert await cog.run_check() == 1


async def test_jeu_multiplateforme_annonce_dans_chaque_salon(cog, serveur_configure):
    salons = await serveur_configure(
        [{"id": 9, "title": "Partout", "platforms": "Steam, Epic Games Store"}]
    )

    assert await cog.run_check() == 2
    assert salons["steam"].sent and salons["epic"].sent


async def test_api_indisponible(cog, serveur_configure):
    salons = await serveur_configure([])

    assert await cog.run_check() == 0
    assert salons["steam"].sent == []


async def test_limite_du_nombre_de_jeux(cog, serveur_configure, monkeypatch):
    monkeypatch.setattr(config, "MAX_GAMES", 1)
    jeux = [dict(STEAM, id=i) for i in range(5)]
    salons = await serveur_configure(jeux)

    assert await cog.run_check() == 1
    assert len(salons["steam"].sent) == 1


async def test_erreur_denvoi_sans_blocage(cog, serveur_configure, caplog):
    salons = await serveur_configure([STEAM, EPIC])

    async def refuse(**kwargs):
        raise discord.HTTPException(_Response(), "boom")

    salons["steam"].send = refuse

    assert await cog.run_check() == 1  # Epic passe quand même
    assert "Envoi impossible" in caplog.text


async def test_salon_supprime_a_la_main(cog, serveur_configure, guild):
    salons = await serveur_configure([STEAM])
    guild.categories[0].channels.remove(salons["steam"])

    assert await cog.run_check() == 0


class _Response:
    status = 500
    reason = "Server Error"


async def test_la_verification_est_horodatee(cog, serveur_configure, db):
    await serveur_configure([STEAM])

    await cog.run_check()

    horodatage = await db.get_bot_state("last_check_at")
    assert horodatage is not None
    from datetime import datetime, timezone

    instant = datetime.fromisoformat(horodatage)
    assert abs((datetime.now(timezone.utc) - instant).total_seconds()) < 60


async def test_annonce_comporte_le_bouton_dinvitation(cog, serveur_configure):
    salons = await serveur_configure([STEAM])

    await cog.run_check()

    kwargs = salons["steam"].sent[0]
    urls = [child.url for child in kwargs["view"].children]
    assert any("oauth2/authorize" in url and "client_id=999" in url for url in urls)
    assert kwargs["embed"].footer.text.startswith("🎁 FreeGameDrop")

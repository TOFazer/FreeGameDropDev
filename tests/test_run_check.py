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


async def test_verifications_simultanees_sans_doublons(cog, serveur_configure):
    import asyncio

    salons = await serveur_configure([STEAM])
    counts = await asyncio.gather(cog.run_check(), cog.run_check())
    assert sum(counts) == 1
    assert len(salons["steam"].sent) == 1


async def test_verification_ciblee_ignore_les_autres_serveurs(cog, serveur_configure):
    salons = await serveur_configure([STEAM])
    assert await cog.run_check(target_guild_id=99999) == 0
    assert not salons["steam"].sent


async def test_les_offres_deja_envoyees_ne_bloquent_plus_epic_ni_la_suite(
    cog, serveur_configure, monkeypatch
):
    """Régression : 25 offres GamerPower + 1 nouveauté Epic avec MAX_GAMES=10.

    Epic doit partir dès le 1er tour (grâce à l'alternance des sources), les tours
    suivants doivent rattraper le reste (sans famine à 0), puis une nouveauté Epic
    apparue plus tard doit partir immédiatement même si les 25 anciennes offres
    GamerPower sont toujours en tête du flux.
    """
    from services import epic_games

    monkeypatch.setattr(config, "MAX_GAMES", 10)
    gp_catalogue = [dict(STEAM, id=f"gp:{i}", title=f"GP {i}") for i in range(1, 26)]
    epic_actuel = [dict(EPIC, id="epic:semaine1", title="Epic Semaine 1", source="epic")]

    salons = await serveur_configure(gp_catalogue)

    async def faux_epic():
        return list(epic_actuel)

    monkeypatch.setattr(epic_games, "fetch_giveaways", faux_epic)

    # 1er passage : 10 annonces, dont l'offre Epic dès maintenant
    assert await cog.run_check() == 10
    assert len(salons["epic"].sent) == 1
    assert salons["epic"].sent[0]["embed"].title == "⚪ Epic Semaine 1"

    # 2e passage : les 10 suivantes (et non 0 !)
    assert await cog.run_check() == 10
    # 3e passage : les 6 dernières
    assert await cog.run_check() == 6
    # 4e passage : tout est à jour
    assert await cog.run_check() == 0

    # Nouvelle semaine Epic alors que les 25 offres GamerPower sont toujours présentes
    epic_actuel.append(dict(EPIC, id="epic:semaine2", title="Epic Semaine 2", source="epic"))
    assert await cog.run_check() == 1
    assert [m["embed"].title for m in salons["epic"].sent] == [
        "⚪ Epic Semaine 1",
        "⚪ Epic Semaine 2",
    ]


async def test_les_plateformes_non_suivies_ne_consomment_pas_le_plafond(
    cog, serveur_configure, monkeypatch
):
    """15 offres itch.io devant 2 offres Epic ne doivent pas gaspiller MAX_GAMES."""
    monkeypatch.setattr(config, "MAX_GAMES", 2)
    offres = [dict(AUTRE, id=f"itch:{i}") for i in range(15)] + [
        dict(EPIC, id="epic:1", title="Epic 1"),
        dict(EPIC, id="epic:2", title="Epic 2"),
    ]
    salons = await serveur_configure(offres)

    assert await cog.run_check() == 2
    assert len(salons["epic"].sent) == 2


async def test_un_serveur_en_rattrapage_ne_bloque_pas_les_autres_serveurs(
    cog_for, fakes, db, monkeypatch
):
    """Le plafond MAX_GAMES est par serveur : un nouveau serveur ne prive pas les anciens."""
    monkeypatch.setattr(config, "MAX_GAMES", 3)

    serveur_ancien = fakes.Guild(guild_id=7)
    cat_a = fakes.Category(serveur_ancien, "🎮 Jeux gratuits")
    serveur_ancien.categories.append(cat_a)
    steam_a = fakes.Channel("jeux-steam", cat_a, channel_id=101)
    epic_a = fakes.Channel("jeux-epic", cat_a, channel_id=102)
    cat_a.channels.extend([steam_a, epic_a])
    await db.set_platform_channel(7, "steam", 101)
    await db.set_platform_channel(7, "epic", 102)

    serveur_neuf = fakes.Guild(guild_id=8)
    cat_b = fakes.Category(serveur_neuf, "🎮 Jeux gratuits")
    serveur_neuf.categories.append(cat_b)
    steam_b = fakes.Channel("jeux-steam", cat_b, channel_id=201)
    epic_b = fakes.Channel("jeux-epic", cat_b, channel_id=202)
    cat_b.channels.extend([steam_b, epic_b])
    await db.set_platform_channel(8, "steam", 201)
    await db.set_platform_channel(8, "epic", 202)

    # Le serveur ancien a déjà reçu les 10 offres Steam, pas le serveur neuf.
    anciens_jeux = [dict(STEAM, id=f"old:{i}", title=f"Ancien {i}") for i in range(10)]
    for jeu in anciens_jeux:
        await db.mark_sent(7, f"{jeu['id']}:steam")

    nouveaute_epic = dict(EPIC, id="epic:nouveau", title="Nouveauté Epic")

    async def faux_appel_api():
        return [*anciens_jeux, nouveaute_epic]

    monkeypatch.setattr(gamerpower, "fetch_giveaways", faux_appel_api)

    instance = cog_for(serveur_ancien)
    tous_les_salons = {101: steam_a, 102: epic_a, 201: steam_b, 202: epic_b}
    instance.bot.get_channel = tous_les_salons.get

    envoyes = await instance.run_check()

    # Serveur neuf : plafonné à 3 rattrapages ; serveur ancien : reçoit immédiatement Epic !
    assert len(steam_b.sent) == 3
    assert len(epic_a.sent) == 1
    assert epic_a.sent[0]["embed"].title == "⚪ Nouveauté Epic"
    assert envoyes == 4


async def test_salon_interdit_ne_consomme_pas_le_plafond_ni_ne_martele_discord(
    cog, serveur_configure, monkeypatch
):
    """Un salon en 403 Forbidden est ignoré pour le reste du tour et laisse passer Epic."""
    from utils import monitoring

    monkeypatch.setattr(config, "MAX_GAMES", 1)
    offres = [dict(STEAM, id=f"s:{i}") for i in range(10)] + [dict(EPIC, id="e:1")]
    salons = await serveur_configure(offres)
    tentatives_steam = 0

    async def interdit(**kwargs):
        nonlocal tentatives_steam
        tentatives_steam += 1
        raise discord.Forbidden(_ForbiddenResponse(), "missing access")

    salons["steam"].send = interdit

    assert await cog.run_check() == 1
    assert tentatives_steam == 1
    assert len(salons["epic"].sent) == 1
    assert monitoring.HEALTH.error_count(15) == 1


class _ForbiddenResponse:
    status = 403
    reason = "Forbidden"


async def test_identifiant_zero_annonce_une_seule_fois(cog, serveur_configure):
    salons = await serveur_configure([dict(STEAM, id=0, title="Jeu ID Zéro")])

    assert await cog.run_check() == 1
    assert await cog.run_check() == 0
    assert len(salons["steam"].sent) == 1

"""Persistance : salons, rôles, accès et historique des envois."""


async def test_salon_des_roles(db):
    assert await db.get_roles_channel(7) is None

    await db.set_roles_channel(7, 111)
    await db.set_roles_channel(7, 222)  # mise à jour, pas de doublon

    assert await db.get_roles_channel(7) == 222
    assert await db.get_all_roles_channels() == {7: 222}


async def test_roles_autorises_remplaces_entierement(db):
    await db.set_roles_channel_access(7, [1, 2, 3])
    await db.set_roles_channel_access(7, [2, 9])

    assert sorted(await db.get_roles_channel_access(7)) == [2, 9]

    await db.set_roles_channel_access(7, [])
    assert await db.get_roles_channel_access(7) == []


async def test_salons_et_roles_par_plateforme(db):
    await db.set_platform_channel(7, "steam", 10)
    await db.set_platform_channel(7, "epic", 11)
    await db.set_platform_role(7, "steam", 20)

    assert await db.get_platform_channels(7) == {"steam": 10, "epic": 11}
    assert await db.get_platform_role(7, "steam") == 20
    assert await db.get_platform_role(7, "gog") is None
    assert await db.get_guild_platform_roles(7) == {"steam": 20}
    assert await db.get_all_platform_roles() == {(7, "steam"): 20}
    assert sorted(await db.get_routes()) == [(7, "epic", 11, "epic"), (7, "steam", 10, "steam")]


async def test_selection_plateformes_desactive_les_routes_non_cochees(db):
    await db.set_platform_channel(7, "steam", 10)
    await db.set_platform_channel(7, "epic", 11)
    assert await db.get_guild_platforms(7) is None  # migration douce des anciennes installations

    await db.set_guild_platforms(7, ["steam", "steam"])

    assert await db.get_guild_platforms(7) == ["steam"]
    assert await db.get_routes() == [(7, "steam", 10, "steam")]
    await db.set_guild_platforms(7, [])
    assert await db.get_guild_platforms(7) == []
    assert await db.get_routes() == []


async def test_panneau_roles_remplace_son_identifiant(db):
    await db.set_roles_panel_message(7, 101)
    await db.set_roles_panel_message(7, 202)

    assert await db.get_roles_panel_message(7) == 202


async def test_historique_des_envois(db):
    assert await db.is_sent(7, "1:steam") is False

    await db.mark_sent(7, "1:steam")
    await db.mark_sent(7, "1:steam")  # deux fois = sans effet

    assert await db.is_sent(7, "1:steam") is True
    assert await db.is_sent(7, "1:epic") is False

    await db.clear_sent(7)
    assert await db.is_sent(7, "1:steam") is False


async def test_isolation_entre_serveurs(db):
    await db.set_roles_channel(7, 111)
    await db.set_roles_channel(8, 222)
    await db.set_platform_channel(8, "steam", 10)
    await db.mark_sent(8, "1:steam")

    await db.clear_guild(7)

    assert await db.get_roles_channel(7) is None
    assert await db.get_roles_channel(8) == 222
    assert await db.get_platform_channels(8) == {"steam": 10}
    assert await db.is_sent(8, "1:steam") is True


async def test_clear_guild_efface_tout(db):
    await db.set_roles_channel(7, 111)
    await db.set_roles_panel_message(7, 112)
    await db.set_roles_channel_access(7, [1, 2])
    await db.set_platform_channel(7, "steam", 10)
    await db.set_platform_role(7, "steam", 20)
    await db.set_guild_platforms(7, ["steam"])
    await db.mark_sent(7, "1:steam")

    await db.clear_guild(7)

    assert await db.get_roles_channel(7) is None
    assert await db.get_roles_panel_message(7) is None
    assert await db.get_roles_channel_access(7) == []
    assert await db.get_platform_channels(7) == {}
    assert await db.get_guild_platforms(7) is None
    assert await db.get_guild_platform_roles(7) == {}
    assert await db.is_sent(7, "1:steam") is False


async def test_init_db_rejouable(db):
    """Un redémarrage du bot ne doit rien casser ni rien perdre."""
    await db.set_roles_channel(7, 111)

    await db.init_db()

    assert await db.get_roles_channel(7) == 111


async def test_catalogue_et_favoris_par_utilisateur(db):
    await db.save_giveaways(
        [
            {
                "id": 123,
                "title": "Un jeu",
                "platforms": "PC (Steam)",
                "open_giveaway_url": "https://example.com/claim",
                "gamerpower_url": "https://example.com/source",
            }
        ]
    )

    assert await db.toggle_favorite(42, "123") is True
    assert await db.toggle_favorite(43, "123") is True
    assert await db.is_favorite(42, "123") is True
    assert await db.get_favorite_ids(42) == {"123"}
    favorites = await db.get_favorites(42)
    assert len(favorites) == 1
    assert favorites[0]["id"] == "123"
    assert favorites[0]["title"] == "Un jeu"
    assert favorites[0]["platforms"] == "PC (Steam)"
    assert favorites[0]["open_giveaway_url"] == "https://example.com/claim"
    assert favorites[0]["gamerpower_url"] == "https://example.com/source"
    assert favorites[0]["favorited_at"]

    assert await db.toggle_favorite(42, "123") is False
    assert await db.get_favorite_ids(42) == set()
    assert await db.get_favorite_ids(43) == {"123"}


async def test_suppression_des_donnees_utilisateur_isolee(db):
    await db.save_giveaways([{"id": 1, "title": "Jeu"}])
    await db.save_giveaways([{"id": 2, "title": "Autre jeu"}])
    await db.toggle_favorite(42, "1")
    await db.toggle_favorite(42, "2")
    await db.toggle_favorite(43, "1")

    assert await db.clear_user_favorites(42) == 2

    assert await db.get_favorite_ids(42) == set()
    assert await db.get_favorite_ids(43) == {"1"}
    remaining = await db.get_favorites(43)
    assert remaining[0]["title"] == "Jeu"


async def test_init_db_cree_le_dossier_de_la_base(tmp_path, monkeypatch):
    """`DB_PATH=data/freegamedrop-dev.db` doit fonctionner sur un dossier neuf."""
    import database

    chemin = tmp_path / "data" / "freegamedrop-dev.db"
    monkeypatch.setattr(database, "DB_PATH", str(chemin))

    await database.init_db()

    assert chemin.exists(), "le dossier `data/` doit être créé au premier démarrage"

    async with __import__("aiosqlite").connect(chemin) as conn:
        curseur = await conn.execute("SELECT COUNT(*) FROM sent_items")
        assert (await curseur.fetchone())[0] == 0

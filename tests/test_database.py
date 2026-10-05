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
    await db.set_roles_channel_access(7, [1, 2])
    await db.set_platform_channel(7, "steam", 10)
    await db.set_platform_role(7, "steam", 20)
    await db.mark_sent(7, "1:steam")

    await db.clear_guild(7)

    assert await db.get_roles_channel(7) is None
    assert await db.get_roles_channel_access(7) == []
    assert await db.get_platform_channels(7) == {}
    assert await db.get_guild_platform_roles(7) == {}
    assert await db.is_sent(7, "1:steam") is False


async def test_init_db_rejouable(db):
    """Un redémarrage du bot ne doit rien casser ni rien perdre."""
    await db.set_roles_channel(7, 111)

    await db.init_db()

    assert await db.get_roles_channel(7) == 111

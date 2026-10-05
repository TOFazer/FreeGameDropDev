import aiosqlite

DB_PATH = "bot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                role_id INTEGER
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS sent_items (
                guild_id INTEGER,
                item_id TEXT,
                PRIMARY KEY (guild_id, item_id)
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS platform_channels (
                guild_id INTEGER,
                platform TEXT,
                channel_id INTEGER,
                PRIMARY KEY (guild_id, platform)
            )"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS platform_roles (
                guild_id INTEGER,
                platform TEXT,
                role_id INTEGER,
                PRIMARY KEY (guild_id, platform)
            )"""
        )
        # salon #choisir-ses-roles de chaque serveur
        await db.execute(
            """CREATE TABLE IF NOT EXISTS roles_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER
            )"""
        )
        # rôles autorisés à VOIR ce salon (vide = tout le monde)
        await db.execute(
            """CREATE TABLE IF NOT EXISTS roles_channel_access (
                guild_id INTEGER,
                role_id INTEGER,
                PRIMARY KEY (guild_id, role_id)
            )"""
        )
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN platforms TEXT")
        except aiosqlite.OperationalError:
            pass  # la colonne existe déjà
        await db.commit()


async def get_channel(guild_id: int):
    """Ancien salon (ancienne commande /setup), utilisé seulement pour le nettoyage."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id FROM guilds WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_platform_channel(guild_id: int, platform: str, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO platform_channels (guild_id, platform, channel_id) VALUES (?, ?, ?)
               ON CONFLICT(guild_id, platform) DO UPDATE SET channel_id = excluded.channel_id""",
            (guild_id, platform, channel_id),
        )
        await db.commit()


async def get_platform_channels(guild_id: int) -> dict:
    """{plateforme: salon_id} pour un serveur."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT platform, channel_id FROM platform_channels WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            return {p: c for p, c in await cursor.fetchall()}


async def get_routes():
    """Retourne (serveur, route, salon, filtre) pour chaque salon à alimenter."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guild_id, platform, channel_id, platform FROM platform_channels"
        ) as cursor:
            return await cursor.fetchall()


async def set_platform_role(guild_id: int, platform: str, role_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO platform_roles (guild_id, platform, role_id) VALUES (?, ?, ?)
               ON CONFLICT(guild_id, platform) DO UPDATE SET role_id = excluded.role_id""",
            (guild_id, platform, role_id),
        )
        await db.commit()


async def get_platform_role(guild_id: int, platform: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role_id FROM platform_roles WHERE guild_id = ? AND platform = ?",
            (guild_id, platform),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_guild_platform_roles(guild_id: int) -> dict:
    """{plateforme: role_id} pour un serveur."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT platform, role_id FROM platform_roles WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            return {p: r for p, r in await cursor.fetchall()}


async def get_all_platform_roles() -> dict:
    """{(serveur, plateforme): role_id} pour tous les serveurs."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guild_id, platform, role_id FROM platform_roles"
        ) as cursor:
            return {(g, p): r for g, p, r in await cursor.fetchall()}


async def set_roles_channel(guild_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO roles_channels (guild_id, channel_id) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id""",
            (guild_id, channel_id),
        )
        await db.commit()


async def get_roles_channel(guild_id: int):
    """Salon #choisir-ses-roles d'un serveur, ou None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id FROM roles_channels WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_all_roles_channels() -> dict:
    """{serveur: salon_id} pour tous les serveurs."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT guild_id, channel_id FROM roles_channels") as cursor:
            return {g: c for g, c in await cursor.fetchall()}


async def set_roles_channel_access(guild_id: int, role_ids):
    """Remplace la liste des rôles autorisés à voir le salon (liste vide = tout le monde)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM roles_channel_access WHERE guild_id = ?", (guild_id,))
        await db.executemany(
            "INSERT OR IGNORE INTO roles_channel_access (guild_id, role_id) VALUES (?, ?)",
            [(guild_id, role_id) for role_id in role_ids],
        )
        await db.commit()


async def get_roles_channel_access(guild_id: int) -> list:
    """[role_id, ...] autorisés à voir le salon. Liste vide = tout le monde."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role_id FROM roles_channel_access WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]


async def is_sent(guild_id: int, item_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM sent_items WHERE guild_id = ? AND item_id = ?",
            (guild_id, item_id),
        ) as cursor:
            return await cursor.fetchone() is not None


async def mark_sent(guild_id: int, item_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sent_items (guild_id, item_id) VALUES (?, ?)",
            (guild_id, item_id),
        )
        await db.commit()


async def clear_sent(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sent_items WHERE guild_id = ?", (guild_id,))
        await db.commit()


async def clear_guild(guild_id: int):
    """Efface toute la configuration d'un serveur."""
    async with aiosqlite.connect(DB_PATH) as db:
        for table in (
            "platform_channels",
            "platform_roles",
            "roles_channels",
            "roles_channel_access",
            "sent_items",
            "guilds",
        ):
            await db.execute(f"DELETE FROM {table} WHERE guild_id = ?", (guild_id,))
        await db.commit()

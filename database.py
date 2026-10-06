"""Stockage SQLite : salons, rôles et annonces déjà envoyées."""

import aiosqlite

import config

# Surchargeable via DB_PATH dans .env (et remplacé par un fichier temporaire dans les tests).
DB_PATH = config.DB_PATH


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
        # Catalogue minimal d'offres publiques : uniquement les champs nécessaires
        # à l'affichage des favoris et aux futures fonctions d'historique/recherche.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS giveaway_items (
                item_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                platforms TEXT NOT NULL DEFAULT '',
                worth TEXT NOT NULL DEFAULT '',
                end_date TEXT NOT NULL DEFAULT '',
                claim_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                thumbnail TEXT NOT NULL DEFAULT '',
                published_date TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        # On ne conserve côté utilisateur que son ID Discord et les offres favorites.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS user_favorites (
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, item_id)
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


def _giveaway_field(game: dict, name: str, fallback: str = "", limit: int = 2048) -> str:
    value = game.get(name) or fallback
    return str(value).strip()[:limit]


async def save_giveaways(games):
    """Enregistre les champs publics utiles d'une liste d'offres GamerPower."""
    rows = []
    for game in games or []:
        if not isinstance(game, dict) or game.get("id") is None:
            continue
        item_id = str(game["id"]).strip()[:128]
        if not item_id:
            continue

        rows.append(
            (
                item_id,
                _giveaway_field(game, "title", "Jeu gratuit", 256) or "Jeu gratuit",
                _giveaway_field(game, "description", limit=4096),
                _giveaway_field(game, "platforms", limit=1000),
                _giveaway_field(game, "worth", limit=100),
                _giveaway_field(game, "end_date", limit=64),
                _giveaway_field(game, "open_giveaway_url", limit=2048),
                _giveaway_field(game, "gamerpower_url", limit=2048),
                _giveaway_field(game, "thumbnail", limit=2048),
                _giveaway_field(game, "published_date", limit=64),
            )
        )

    if not rows:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT INTO giveaway_items (
                   item_id, title, description, platforms, worth, end_date,
                   claim_url, source_url, thumbnail, published_date
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(item_id) DO UPDATE SET
                   title = excluded.title,
                   description = CASE WHEN excluded.description != ''
                       THEN excluded.description ELSE giveaway_items.description END,
                   platforms = CASE WHEN excluded.platforms != ''
                       THEN excluded.platforms ELSE giveaway_items.platforms END,
                   worth = CASE WHEN excluded.worth != ''
                       THEN excluded.worth ELSE giveaway_items.worth END,
                   end_date = CASE WHEN excluded.end_date != ''
                       THEN excluded.end_date ELSE giveaway_items.end_date END,
                   claim_url = CASE WHEN excluded.claim_url != ''
                       THEN excluded.claim_url ELSE giveaway_items.claim_url END,
                   source_url = CASE WHEN excluded.source_url != ''
                       THEN excluded.source_url ELSE giveaway_items.source_url END,
                   thumbnail = CASE WHEN excluded.thumbnail != ''
                       THEN excluded.thumbnail ELSE giveaway_items.thumbnail END,
                   published_date = CASE WHEN excluded.published_date != ''
                       THEN excluded.published_date ELSE giveaway_items.published_date END,
                   last_seen_at = CURRENT_TIMESTAMP""",
            rows,
        )
        await db.execute(
            """DELETE FROM giveaway_items
               WHERE last_seen_at < datetime('now', '-90 days')
                 AND NOT EXISTS (
                     SELECT 1 FROM user_favorites
                     WHERE user_favorites.item_id = giveaway_items.item_id
                 )"""
        )
        await db.commit()


async def toggle_favorite(user_id: int, item_id: str) -> bool:
    """Ajoute ou retire un favori et retourne son nouvel état (True = favori)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO user_favorites (user_id, item_id) VALUES (?, ?)",
            (user_id, str(item_id)),
        )
        is_favorite = cursor.rowcount > 0
        if not is_favorite:
            await db.execute(
                "DELETE FROM user_favorites WHERE user_id = ? AND item_id = ?",
                (user_id, str(item_id)),
            )
        await db.commit()
        return is_favorite


async def is_favorite(user_id: int, item_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM user_favorites WHERE user_id = ? AND item_id = ?",
            (user_id, str(item_id)),
        ) as cursor:
            return await cursor.fetchone() is not None


async def get_favorite_ids(user_id: int) -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT item_id FROM user_favorites WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            return {str(row[0]) for row in await cursor.fetchall()}


async def get_favorites(user_id: int) -> list[dict]:
    """Offres enregistrées par un membre, de la plus récente à la plus ancienne."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT g.item_id, g.title, g.description, g.platforms, g.worth,
                      g.end_date, g.claim_url, g.source_url, g.thumbnail,
                      g.published_date, f.created_at
               FROM user_favorites AS f
               JOIN giveaway_items AS g ON g.item_id = f.item_id
               WHERE f.user_id = ?
               ORDER BY f.created_at DESC, g.title COLLATE NOCASE""",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "description": row[2],
            "platforms": row[3],
            "worth": row[4],
            "end_date": row[5],
            "open_giveaway_url": row[6],
            "gamerpower_url": row[7],
            "thumbnail": row[8],
            "published_date": row[9],
            "favorited_at": row[10],
        }
        for row in rows
    ]


async def clear_user_favorites(user_id: int) -> int:
    """Efface les favoris d'un membre et retourne le nombre de lignes supprimées."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM user_favorites WHERE user_id = ?", (user_id,))
        await db.commit()
        return cursor.rowcount

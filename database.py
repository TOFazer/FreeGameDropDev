"""Stockage SQLite : salons, rôles et annonces déjà envoyées."""

import os
from pathlib import Path

import aiosqlite

import config
from utils.offers import classify_offer_type, normalize_genres

# Surchargeable via DB_PATH dans .env (et remplacé par un fichier temporaire dans les tests).
DB_PATH = config.DB_PATH


def _ensure_parent_directory(path: str) -> None:
    """Crée le dossier de la base (ex. `data/`) s'il n'existe pas encore.

    `:memory:` et les chemins sans dossier (« bot.db ») ne déclenchent rien.
    """
    if not path or path == ":memory:" or path.startswith("file:"):
        return
    parent = Path(path).expanduser().parent
    if str(parent) not in ("", "."):
        os.makedirs(parent, exist_ok=True)


async def init_db():
    _ensure_parent_directory(DB_PATH)
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
        # Message du panneau de rôles à mettre à jour (sans lire/supprimer l'historique).
        await db.execute(
            """CREATE TABLE IF NOT EXISTS roles_panel_messages (
                guild_id INTEGER PRIMARY KEY,
                message_id INTEGER NOT NULL
            )"""
        )
        # Plateformes effectivement suivies par chaque serveur. L'absence de ligne
        # signifie une ancienne configuration : toutes les routes enregistrées restent actives.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS guild_platform_selection (
                guild_id INTEGER PRIMARY KEY,
                platforms TEXT NOT NULL DEFAULT ''
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
        # Préférences personnelles utilisées par /free, les favoris et les alertes DM.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                offer_types TEXT NOT NULL DEFAULT 'game',
                min_worth_eur REAL,
                genres TEXT NOT NULL DEFAULT '',
                timezone TEXT NOT NULL DEFAULT '',
                platforms TEXT NOT NULL DEFAULT ''
            )"""
        )
        # Alertes personnelles (DM) qu'un membre a activées, indépendamment du serveur.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS user_notification_settings (
                user_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_id, event)
            )"""
        )
        # Historique d'envoi des alertes pour éviter les doublons et respecter la cadence.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS alert_history (
                user_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                event TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, item_id, event)
            )"""
        )
        # Salon d'un serveur recevant les rappels « se termine aujourd'hui ».
        await db.execute(
            """CREATE TABLE IF NOT EXISTS guild_reminder_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )"""
        )
        # État interne du bot (par exemple la date de la dernière vérification),
        # utilisé uniquement pour des informations réellement mesurées.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )
        # Sessions du tableau de bord web, créées après l'authentification Discord OAuth2.
        await db.execute(
            """CREATE TABLE IF NOT EXISTS dashboard_sessions (
                session_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                avatar TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL
            )"""
        )
        try:
            await db.execute("ALTER TABLE guilds ADD COLUMN platforms TEXT")
        except aiosqlite.OperationalError:
            pass  # la colonne existe déjà
        try:
            await db.execute("ALTER TABLE user_preferences ADD COLUMN platforms TEXT NOT NULL DEFAULT ''")
        except aiosqlite.OperationalError:
            pass  # la colonne existe déjà
        for column, definition in (
            ("source", "TEXT NOT NULL DEFAULT 'gamerpower'"),
            ("offer_type", "TEXT NOT NULL DEFAULT 'game'"),
            ("genres", "TEXT NOT NULL DEFAULT ''"),
        ):
            try:
                await db.execute(f"ALTER TABLE giveaway_items ADD COLUMN {column} {definition}")
            except aiosqlite.OperationalError:
                pass  # la colonne existe déjà
        # Colonnes ajoutées aux sessions du tableau de bord :
        # - csrf_token : jeton anti-CSRF propre à la session, exigé sur chaque formulaire ;
        # - guilds_json : instantané (id, nom, icône) des serveurs que le membre peut gérer,
        #   pris au moment de la connexion — on ne stocke JAMAIS son jeton OAuth Discord.
        for column, definition in (
            ("csrf_token", "TEXT NOT NULL DEFAULT ''"),
            ("guilds_json", "TEXT NOT NULL DEFAULT ''"),
        ):
            try:
                await db.execute(f"ALTER TABLE dashboard_sessions ADD COLUMN {column} {definition}")
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
    """{plateforme: salon_id} pour un serveur, y compris les salons temporairement désactivés."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT platform, channel_id FROM platform_channels WHERE guild_id = ?",
            (guild_id,),
        ) as cursor:
            return {p: c for p, c in await cursor.fetchall()}


async def set_guild_platforms(guild_id: int, platform_keys) -> None:
    """Remplace la sélection des plateformes, y compris par une liste vide."""
    platforms_text = ",".join(dict.fromkeys(str(key) for key in platform_keys or []))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO guild_platform_selection (guild_id, platforms) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET platforms = excluded.platforms""",
            (guild_id, platforms_text),
        )
        await db.commit()


async def get_guild_platforms(guild_id: int) -> list[str] | None:
    """Plateformes suivies, ou None pour une configuration historique non migrée."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT platforms FROM guild_platform_selection WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return [key for key in (row[0] or "").split(",") if key]


async def get_routes():
    """Retourne (serveur, route, salon, filtre) pour chaque salon actif à alimenter."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT guild_id, platform, channel_id, platform FROM platform_channels"
        ) as cursor:
            routes = await cursor.fetchall()
        async with db.execute(
            "SELECT guild_id, platforms FROM guild_platform_selection"
        ) as cursor:
            selections = {
                guild_id: set((platforms or "").split(","))
                for guild_id, platforms in await cursor.fetchall()
            }
    return [
        route
        for route in routes
        if route[0] not in selections or route[1] in selections[route[0]]
    ]


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


async def set_roles_panel_message(guild_id: int, message_id: int) -> None:
    """Mémorise le panneau pour le mettre à jour directement lors des prochaines configurations."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO roles_panel_messages (guild_id, message_id) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET message_id = excluded.message_id""",
            (guild_id, message_id),
        )
        await db.commit()


async def get_roles_panel_message(guild_id: int) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT message_id FROM roles_panel_messages WHERE guild_id = ?", (guild_id,)
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
            "roles_panel_messages",
            "roles_channel_access",
            "guild_platform_selection",
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

        genres_text = ",".join(normalize_genres(game.get("genres")))
        offer_type = classify_offer_type(game.get("offer_type") or game.get("type"))

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
                _giveaway_field(game, "source", "gamerpower", limit=32) or "gamerpower",
                offer_type,
                genres_text[:500],
            )
        )

    if not rows:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT INTO giveaway_items (
                   item_id, title, description, platforms, worth, end_date,
                   claim_url, source_url, thumbnail, published_date,
                   source, offer_type, genres
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                   source = excluded.source,
                   offer_type = excluded.offer_type,
                   genres = CASE WHEN excluded.genres != ''
                       THEN excluded.genres ELSE giveaway_items.genres END,
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


def _row_to_giveaway(row) -> dict:
    return {
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
        "source": row[10],
        "offer_type": row[11],
        "genres": [g for g in (row[12] or "").split(",") if g],
        "first_seen_at": row[13],
    }


_GIVEAWAY_COLUMNS = (
    "item_id, title, description, platforms, worth, end_date, claim_url, "
    "source_url, thumbnail, published_date, source, offer_type, genres, first_seen_at"
)


async def get_recent_giveaways(
    limit: int = 50,
    *,
    platform: str | None = None,
    offer_type: str | None = None,
    source: str | None = None,
) -> list[dict]:
    """Historique des offres connues, de la plus récente à la plus ancienne."""
    clauses = []
    params: list = []
    if platform:
        clauses.append("platforms LIKE ?")
        params.append(f"%{platform}%")
    if offer_type:
        clauses.append("offer_type = ?")
        params.append(offer_type)
    if source:
        clauses.append("source = ?")
        params.append(source)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""SELECT {_GIVEAWAY_COLUMNS} FROM giveaway_items
                {where}
                ORDER BY first_seen_at DESC, rowid DESC
                LIMIT ?""",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_giveaway(row) for row in rows]


async def search_giveaways(query: str, limit: int = 20) -> list[dict]:
    """Recherche plein texte (titre puis description) parmi les offres connues."""
    needle = f"%{query.strip()}%"
    if query.strip() == "":
        return []
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"""SELECT {_GIVEAWAY_COLUMNS} FROM giveaway_items
                WHERE title LIKE ? OR description LIKE ?
                ORDER BY first_seen_at DESC, rowid DESC
                LIMIT ?""",
            (needle, needle, limit),
        ) as cursor:
            rows = await cursor.fetchall()
    return [_row_to_giveaway(row) for row in rows]


async def get_giveaway_stats() -> dict:
    """Statistiques globales du catalogue, utilisées par le tableau de bord développeur."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM giveaway_items") as cursor:
            (total,) = await cursor.fetchone()

        async with db.execute(
            "SELECT source, COUNT(*) FROM giveaway_items GROUP BY source"
        ) as cursor:
            by_source = {source: count for source, count in await cursor.fetchall()}

        async with db.execute(
            "SELECT offer_type, COUNT(*) FROM giveaway_items GROUP BY offer_type"
        ) as cursor:
            by_type = {offer_type: count for offer_type, count in await cursor.fetchall()}

        async with db.execute(
            "SELECT COUNT(*) FROM giveaway_items WHERE first_seen_at >= datetime('now', '-30 days')"
        ) as cursor:
            (last_30_days,) = await cursor.fetchone()

        async with db.execute("SELECT COUNT(*) FROM user_favorites") as cursor:
            (total_favorites,) = await cursor.fetchone()

        async with db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM user_favorites"
        ) as cursor:
            (members_with_favorites,) = await cursor.fetchone()

        async with db.execute("SELECT COUNT(*) FROM guilds") as cursor:
            (known_guilds,) = await cursor.fetchone()
        async with db.execute(
            """SELECT COUNT(DISTINCT channels.guild_id)
               FROM platform_channels AS channels
               LEFT JOIN guild_platform_selection AS selected USING (guild_id)
               WHERE selected.guild_id IS NULL
                  OR instr(',' || selected.platforms || ',', ',' || channels.platform || ',') > 0"""
        ) as cursor:
            (configured_guilds,) = await cursor.fetchone()

    return {
        "total_offers": total,
        "offers_by_source": by_source,
        "offers_by_type": by_type,
        "offers_last_30_days": last_30_days,
        "total_favorites": total_favorites,
        "members_with_favorites": members_with_favorites,
        "known_guilds": known_guilds,
        "configured_guilds": configured_guilds,
    }


async def get_offer_rows_for_stats() -> list[tuple[str, str]]:
    """(end_date, worth) de chaque offre du catalogue, pour les statistiques publiques.

    Seules des valeurs réellement enregistrées sont renvoyées : aucun calcul, aucune
    estimation — l'interprétation (offre active, valeur en euros) est faite par l'appelant.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT end_date, worth FROM giveaway_items") as cursor:
            return [(end_date or "", worth or "") for end_date, worth in await cursor.fetchall()]


async def ping() -> bool:
    """Vérifie que la base répond réellement (une requête triviale).

    Utilisé par `utils.monitoring` : un échec ici déclenche l'alerte « la base ne
    répond plus ». Les exceptions remontent volontairement à l'appelant, qui sait
    quoi en faire (compter l'erreur, alerter, ne pas interrompre le bot).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1") as cursor:
            row = await cursor.fetchone()
    return bool(row and row[0] == 1)


async def set_bot_state(key: str, value: str) -> None:
    """Mémorise un état interne du bot (ex. date de la dernière vérification)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO bot_state (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        await db.commit()


async def get_bot_state(key: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM bot_state WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


# ---------- Préférences personnelles ----------


async def set_user_preferences(
    user_id: int,
    *,
    offer_types: list[str] | None = None,
    min_worth_eur: float | None = None,
    genres: list[str] | None = None,
    timezone: str | None = None,
    platforms: list[str] | None = None,
) -> None:
    offer_types_text = ",".join(offer_types) if offer_types else "game"
    genres_text = ",".join(genres) if genres else ""
    platforms_text = ",".join(platforms) if platforms else ""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_preferences
                   (user_id, offer_types, min_worth_eur, genres, timezone, platforms)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   offer_types = excluded.offer_types,
                   min_worth_eur = excluded.min_worth_eur,
                   genres = excluded.genres,
                   timezone = excluded.timezone,
                   platforms = excluded.platforms""",
            (user_id, offer_types_text, min_worth_eur, genres_text, timezone or "", platforms_text),
        )
        await db.commit()


async def get_user_preferences(user_id: int) -> dict:
    """Préférences d'un membre, avec des valeurs par défaut sûres si aucune n'est enregistrée."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT offer_types, min_worth_eur, genres, timezone, platforms
               FROM user_preferences WHERE user_id = ?""",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return {
            "offer_types": ["game"],
            "min_worth_eur": None,
            "genres": [],
            "timezone": "",
            "platforms": [],
        }

    offer_types, min_worth_eur, genres, timezone, platforms = row
    return {
        "offer_types": [t for t in (offer_types or "game").split(",") if t],
        "min_worth_eur": min_worth_eur,
        "genres": [g for g in (genres or "").split(",") if g],
        "timezone": timezone or "",
        "platforms": [p for p in (platforms or "").split(",") if p],
    }


# ---------- Alertes personnelles (DM) ----------


async def set_user_notification(user_id: int, event: str, enabled: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_notification_settings (user_id, event, enabled) VALUES (?, ?, ?)
               ON CONFLICT(user_id, event) DO UPDATE SET enabled = excluded.enabled""",
            (user_id, event, int(enabled)),
        )
        await db.commit()


async def get_user_notifications(user_id: int) -> dict[str, bool]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT event, enabled FROM user_notification_settings WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            return {event: bool(enabled) for event, enabled in await cursor.fetchall()}


async def get_users_subscribed(event: str) -> list[int]:
    """Membres ayant activé une alerte DM donnée."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM user_notification_settings WHERE event = ? AND enabled = 1",
            (event,),
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]


async def was_alert_sent_recently(user_id: int, item_id: str, event: str, within_hours: float) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT 1 FROM alert_history
               WHERE user_id = ? AND item_id = ? AND event = ?
                 AND sent_at >= datetime('now', ?)""",
            (user_id, str(item_id), event, f"-{within_hours} hours"),
        ) as cursor:
            return await cursor.fetchone() is not None


async def record_alert_sent(user_id: int, item_id: str, event: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO alert_history (user_id, item_id, event, sent_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, item_id, event) DO UPDATE SET sent_at = CURRENT_TIMESTAMP""",
            (user_id, str(item_id), event),
        )
        await db.commit()


# ---------- Rappels serveur ----------


async def set_guild_reminder_channel(guild_id: int, channel_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO guild_reminder_channels (guild_id, channel_id) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id""",
            (guild_id, channel_id),
        )
        await db.commit()


async def get_guild_reminder_channel(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id FROM guild_reminder_channels WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_all_guild_reminder_channels() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT guild_id, channel_id FROM guild_reminder_channels") as cursor:
            return {g: c for g, c in await cursor.fetchall()}


# ---------- Sessions du tableau de bord web ----------


async def create_dashboard_session(
    session_id: str,
    user_id: int,
    username: str,
    avatar: str,
    expires_at: str,
    csrf_token: str = "",
    guilds_json: str = "",
) -> None:
    """`expires_at` doit être au format SQLite ``YYYY-MM-DD HH:MM:SS`` (UTC), comparable
    directement à ``CURRENT_TIMESTAMP``."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO dashboard_sessions
                   (session_id, user_id, username, avatar, expires_at, csrf_token, guilds_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   user_id = excluded.user_id,
                   username = excluded.username,
                   avatar = excluded.avatar,
                   expires_at = excluded.expires_at,
                   csrf_token = excluded.csrf_token,
                   guilds_json = excluded.guilds_json""",
            (session_id, user_id, username, avatar, expires_at, csrf_token, guilds_json),
        )
        await db.commit()


async def get_dashboard_session(session_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT user_id, username, avatar, expires_at, csrf_token, guilds_json
               FROM dashboard_sessions
               WHERE session_id = ? AND expires_at > CURRENT_TIMESTAMP""",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return {
        "user_id": row[0],
        "username": row[1],
        "avatar": row[2],
        "expires_at": row[3],
        "csrf_token": row[4] or "",
        "guilds_json": row[5] or "",
    }


async def delete_dashboard_session(session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM dashboard_sessions WHERE session_id = ?", (session_id,))
        await db.commit()


async def purge_expired_sessions() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM dashboard_sessions WHERE expires_at <= CURRENT_TIMESTAMP")
        await db.commit()


async def count_user_data(user_id: int) -> dict:
    """Résumé de ce que le bot conserve pour un membre (page « Compte » du tableau de bord)."""
    queries = {
        "favorites": "SELECT COUNT(*) FROM user_favorites WHERE user_id = ?",
        "preferences": "SELECT COUNT(*) FROM user_preferences WHERE user_id = ?",
        "notifications": "SELECT COUNT(*) FROM user_notification_settings WHERE user_id = ?",
        "alert_history": "SELECT COUNT(*) FROM alert_history WHERE user_id = ?",
    }
    summary = {}
    async with aiosqlite.connect(DB_PATH) as db:
        for key, query in queries.items():
            async with db.execute(query, (user_id,)) as cursor:
                row = await cursor.fetchone()
                summary[key] = row[0] if row else 0
    return summary


async def delete_user_data(user_id: int) -> None:
    """Efface tout ce qui est lié à un membre : favoris, préférences, alertes, historique
    et sessions du tableau de bord. Les informations publiques des offres sont conservées."""
    async with aiosqlite.connect(DB_PATH) as db:
        for table in (
            "user_favorites",
            "user_preferences",
            "user_notification_settings",
            "alert_history",
            "dashboard_sessions",
        ):
            await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        await db.commit()

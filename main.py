"""Point d'entrée du bot : python main.py

Au démarrage, l'environnement déclaré (`ENVIRONMENT` dans `.env`) est vérifié avant
toute connexion Discord : jeton, identifiant d'application et fichier SQLite doivent
tous désigner le même environnement, sinon le bot refuse de démarrer (voir
utils/environment.py et ENVIRONMENTS.md).
"""

import logging
import math

import discord
from discord.ext import commands

import config
import database
from utils import environment
from utils.logging_setup import configure_logging, log_event

log = logging.getLogger(__name__)

EXTENSIONS = ("cogs.setup", "cogs.jeux", "cogs.sante")


class ReleaseBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.dashboard_runner = None

    async def setup_hook(self):
        await database.init_db()
        # Confirme le fichier SQLite réellement utilisé : DEV et PROD n'y touchent pas ensemble.
        environment.log_database(log, db_path=database.DB_PATH)
        for extension in EXTENSIONS:
            await self.load_extension(extension)

        if config.DASHBOARD_ENABLED:
            from web.dashboard_server import start_dashboard

            try:
                self.dashboard_runner = await start_dashboard(self)
            except OSError as e:
                log.warning("Tableau de bord web non démarré : %s", e)

        # Supprime les anciennes copies de commandes laissées sur le serveur de test
        # (évite les doublons et le message « commande obsolète »).
        if config.TEST_GUILD_ID:
            try:
                guild = discord.Object(id=config.TEST_GUILD_ID)
                self.tree.clear_commands(guild=guild)
                await self.tree.sync(guild=guild)
            except discord.HTTPException as e:
                log.warning("Nettoyage du serveur de test ignoré : %s", e)

        synced = await self.tree.sync()
        log.info("Commandes envoyées à Discord : %s", [c.name for c in synced])

    async def on_ready(self):
        # Le bandeau rappelle l'environnement : si le mauvais bot a démarré, ça se voit ici.
        log.info("Connecté en tant que %s", self.user)
        environment.log_connected(log, user=self.user, guilds=len(self.guilds))
        latency_ms = round(self.latency * 1000) if math.isfinite(self.latency) else None
        log_event(
            "discord.ready",
            guilds=len(self.guilds),
            latency_ms=latency_ms,
            environment=environment.current(),
        )

    async def on_disconnect(self):
        log.warning("Connexion Discord perdue ; discord.py va tenter de se reconnecter")
        log_event("discord.disconnected", level=logging.WARNING)

    async def on_resumed(self):
        log.info("Connexion Discord rétablie")
        log_event("discord.resumed")

    async def close(self):
        if self.dashboard_runner is not None:
            from web.dashboard_server import stop_dashboard

            await stop_dashboard(self.dashboard_runner)
        await super().close()


def main():
    # Journalisation sûre : les secrets (token, clés OAuth, jetons de webhook) sont
    # masqués avant l'écriture, sur la sortie standard comme dans LOG_FILE.
    configure_logging(config.LOG_LEVEL)
    if not config.DISCORD_TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN manquant : copie .env.example en .env et renseigne ton token."
        )

    # Garde-fou DEV / PROD : jeton, application Discord et base SQLite doivent désigner
    # l'environnement déclaré. En cas d'incohérence, rien n'est tenté côté Discord.
    try:
        environment.verify_startup(config)
    except environment.EnvironmentRefused as refused:
        raise SystemExit(str(refused)) from refused

    environment.log_start(
        log,
        db_path=config.DB_PATH,
        application_id=config.DISCORD_APPLICATION_ID,
        maintenance=config.MAINTENANCE_MODE,
    )
    if config.MAINTENANCE_MODE:
        environment.log_maintenance(log)

    log_event(
        "bot.starting",
        environment=config.ENVIRONMENT,
        sources=len(config.OFFER_SOURCES),
        maintenance=config.MAINTENANCE_MODE,
    )
    ReleaseBot().run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

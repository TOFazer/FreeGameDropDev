"""Point d'entrée du bot : python main.py"""

import logging

import discord
from discord.ext import commands

import config
import database

log = logging.getLogger(__name__)

EXTENSIONS = ("cogs.setup", "cogs.jeux")


class ReleaseBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.dashboard_runner = None

    async def setup_hook(self):
        await database.init_db()
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
        log.info("Connecté en tant que %s", self.user)

    async def close(self):
        if self.dashboard_runner is not None:
            from web.dashboard_server import stop_dashboard

            await stop_dashboard(self.dashboard_runner)
        await super().close()


def main():
    discord.utils.setup_logging(level=getattr(logging, config.LOG_LEVEL, logging.INFO))
    if not config.DISCORD_TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN manquant : copie .env.example en .env et renseigne ton token."
        )
    ReleaseBot().run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

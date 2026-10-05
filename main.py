import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

import database

load_dotenv()

# Serveur de test où d'anciennes copies de commandes avaient été envoyées.
# Le nettoyage ci-dessous évite les doublons et le message "commande obsolète".
TEST_GUILD_ID = 1391429196105912452


class ReleaseBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        await database.init_db()
        await self.load_extension("cogs.setup")
        await self.load_extension("cogs.jeux")

        # supprime les anciennes copies de commandes sur le serveur de test
        try:
            guild = discord.Object(id=TEST_GUILD_ID)
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
        except discord.HTTPException as e:
            print("Nettoyage du serveur de test ignoré :", e)

        synced = await self.tree.sync()
        print("Commandes envoyées à Discord :", [c.name for c in synced])

    async def on_ready(self):
        print(f"Connecté en tant que {self.user}")


bot = ReleaseBot()
bot.run(os.getenv("DISCORD_TOKEN"))
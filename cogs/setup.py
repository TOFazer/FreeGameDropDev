import discord
from discord import app_commands
from discord.ext import commands


class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Vérifie que le bot répond")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong ! {ms} ms")


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
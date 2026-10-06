"""Commandes générales du bot : ping et informations publiques."""

import math

import discord
from discord import app_commands
from discord.ext import commands

import config


def build_info_embed(bot: commands.Bot) -> discord.Embed:
    """Construit la fiche /info à partir de l'état actuel du bot."""
    latency = getattr(bot, "latency", float("inf"))
    latency_text = f"{round(latency * 1000)} ms" if math.isfinite(latency) else "indisponible"

    embed = discord.Embed(
        title="🎮 FreeGameDrop",
        description="Les jeux gratuits du moment, annoncés automatiquement sur Discord.",
        colour=discord.Colour.blurple(),
    )
    embed.add_field(name="Latence", value=latency_text, inline=True)
    embed.add_field(name="Serveurs", value=f"{len(bot.guilds):,}", inline=True)

    links = []
    if bot.user is not None:
        permissions = discord.Permissions(
            manage_channels=True,
            manage_roles=True,
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            embed_links=True,
            manage_messages=True,
        ).value
        invite_url = (
            "https://discord.com/oauth2/authorize?"
            f"client_id={bot.user.id}&permissions={permissions}"
            "&scope=bot%20applications.commands"
        )
        links.append(f"[Ajouter le bot]({invite_url})")
    if config.PROJECT_URL:
        links.append(f"[Projet]({config.PROJECT_URL})")
    if config.SUPPORT_URL:
        links.append(f"[Support]({config.SUPPORT_URL})")
    if config.VOTE_URL:
        links.append(f"[Voter]({config.VOTE_URL})")

    embed.add_field(
        name="Liens utiles", value=" · ".join(links) or "Aucun lien configuré.", inline=False
    )
    embed.set_footer(text="FreeGameDrop • Merci de faire partie de la communauté !")
    return embed


class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Vérifie que le bot répond")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"Pong ! {ms} ms")

    @app_commands.command(name="info", description="Affiche la latence, les serveurs et les liens utiles")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_info_embed(self.bot), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))

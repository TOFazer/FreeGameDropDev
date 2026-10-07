"""Commandes générales du bot : ping, informations publiques et statistiques."""

import math

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import branding, metrics


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
        links.append(f"[Ajouter le bot]({branding.build_invite_url(bot.user.id)})")
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


def build_stats_embed(bot: commands.Bot, stats: dict) -> discord.Embed:
    """Construit la fiche /stats : uniquement des chiffres réellement mesurés."""
    sources = ", ".join(stats.get("sources") or []) or "—"
    last_check = metrics.format_last_check(stats.get("last_check_at"))

    embed = discord.Embed(
        title="📊 FreeGameDrop en chiffres",
        description="Tout ce qui suit provient des vérifications réellement effectuées par le bot.",
        colour=discord.Colour.blurple(),
    )
    if bot.user is not None:
        embed.url = branding.build_invite_url(bot.user.id)
    embed.add_field(name="🎮 Offres détectées", value=f"{stats.get('total_offers', 0):,}", inline=True)
    embed.add_field(name="🟢 Offres actives", value=f"{stats.get('active_offers', 0):,}", inline=True)
    embed.add_field(
        name="🆕 Ce mois-ci", value=f"{stats.get('offers_last_30_days', 0):,}", inline=True
    )
    embed.add_field(
        name="💰 Valeur connue",
        value=f"{stats.get('known_value_eur', 0):,.2f} €\n*(offres libellées en euros)*",
        inline=True,
    )
    embed.add_field(
        name="🏪 Plateformes suivies", value=f"{stats.get('platforms_watched', 0):,}", inline=True
    )
    embed.add_field(name="🛰️ Sources", value=sources, inline=True)
    embed.add_field(name="🏠 Serveurs", value=f"{stats.get('guilds', 0):,}", inline=True)
    embed.add_field(name="⏱️ Dernière vérification", value=last_check, inline=True)
    embed.set_footer(text="FreeGameDrop • Ajoute le bot à ton serveur depuis le titre !")
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

    @app_commands.command(
        name="stats", description="Les chiffres du bot : offres détectées, actives, valeur connue"
    )
    async def stats(self, interaction: discord.Interaction):
        stats = await metrics.build_public_stats(self.bot)
        await interaction.response.send_message(
            embed=build_stats_embed(self.bot, stats), allowed_mentions=discord.AllowedMentions.none()
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))

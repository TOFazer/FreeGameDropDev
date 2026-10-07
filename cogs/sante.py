"""Surveillance : commande `/sante` et alertes automatiques.

La boucle `monitor_health` mesure l'état réel du bot (base de données, sources
d'offres, tâches de fond) puis envoie les alertes dues dans le salon configuré
(`MONITOR_ALERT_CHANNEL_ID`) ou, à défaut, en message privé au propriétaire du
bot (`MONITOR_OWNER_ID`). Sans destinataire joignable, les alertes restent dans
le journal et l'état est consultable par `/sante` et par `/api/health`.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from utils import monitoring, rate_limits
from utils.logging_setup import log_event

log = logging.getLogger(__name__)


class Sante(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.alert_book = monitoring.AlertBook(config.MONITOR_ALERT_COOLDOWN_MINUTES)
        if config.MONITOR_ENABLED:
            self.monitor_health.change_interval(minutes=config.MONITOR_INTERVAL_MINUTES)
            self.monitor_health.start()

    async def cog_unload(self):
        self.monitor_health.cancel()

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Répond proprement à une limite atteinte, sinon journalise l'erreur."""
        if isinstance(error, rate_limits.RateLimited):
            message = str(error)
        else:
            monitoring.HEALTH.record_error()
            log.error(
                "Erreur de commande /%s : %s",
                getattr(interaction.command, "name", "inconnue"),
                error,
                exc_info=(type(error), error, error.__traceback__),
            )
            message = "La commande n'a pas pu être exécutée. Réessaie dans quelques instants."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            log.warning("Impossible d'envoyer le retour d'erreur à l'interaction Discord")

    # ----- boucle de surveillance -----

    @tasks.loop(minutes=5)
    async def monitor_health(self):
        interval = config.MONITOR_INTERVAL_MINUTES * 60
        try:
            await monitoring.run_check(self.bot, book=self.alert_book, send=self.send_alert)
        except Exception as error:
            monitoring.HEALTH.record_task_run(
                "monitoring",
                interval_seconds=interval,
                error=f"{type(error).__name__}: {error}",
            )
            monitoring.HEALTH.record_error()
            log_event("task.failure", level=logging.ERROR, task="monitoring", error=error)
            log.exception("Erreur pendant la surveillance")
        else:
            monitoring.HEALTH.record_task_run("monitoring", interval_seconds=interval)

    @monitor_health.before_loop
    async def before_monitor_health(self):
        monitoring.HEALTH.register_task(
            "monitoring", interval_seconds=config.MONITOR_INTERVAL_MINUTES * 60
        )
        await self.bot.wait_until_ready()

    async def _owner_id(self) -> int | None:
        if config.MONITOR_OWNER_ID:
            return config.MONITOR_OWNER_ID
        try:
            info = await self.bot.application_info()
        except Exception:
            log.warning("Impossible de lire le propriétaire de l'application Discord")
            return None
        owner = getattr(info, "owner", None)
        return getattr(owner, "id", None)

    async def send_alert(self, alert: monitoring.Alert) -> bool:
        """Envoie une alerte au destinataire configuré. Retourne True si elle est partie."""
        text = f"🛠️ **FreeGameDrop — surveillance**\n{alert.text}"

        if config.MONITOR_ALERT_CHANNEL_ID:
            channel = self.bot.get_channel(config.MONITOR_ALERT_CHANNEL_ID)
            if channel is None:
                log.warning(
                    "Salon d'alerte %s introuvable ; alerte envoyée au propriétaire",
                    config.MONITOR_ALERT_CHANNEL_ID,
                )
            else:
                try:
                    await rate_limits.spaced_send(
                        channel.send, key=f"channel:{channel.id}", content=text
                    )
                    return True
                except Exception:
                    log.exception("Alerte de surveillance non envoyée dans le salon")

        owner_id = await self._owner_id()
        if owner_id is None:
            log.warning("Aucun destinataire d'alerte disponible ; alerte uniquement journalisée")
            return False
        try:
            user = self.bot.get_user(owner_id) or await self.bot.fetch_user(owner_id)
            await rate_limits.spaced_send(user.send, key=f"dm:{owner_id}", content=text)
            return True
        except Exception:
            log.exception("Alerte de surveillance non envoyée au propriétaire")
            return False

    # ----- commande publique -----

    @app_commands.command(name="sante", description="État du bot, des sources et des dernières tâches")
    @rate_limits.limited("sante")
    async def sante(self, interaction: discord.Interaction):
        """Affiche en privé l'état mesuré, sans secret ni détail technique sensible."""
        report = await monitoring.status_report(self.bot)
        await interaction.response.send_message(
            f"```\n{report}\n```",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Sante(bot))

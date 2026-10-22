"""Commandes et surveillance des jeux gratuits.

Ce cog ne contient que la logique Discord : les messages sont construits dans
`utils.embeds`, les permissions dans `utils.permissions`, les réglages dans
`config.py` et l'appel à l'API dans `services.gamerpower`.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database
from services import offer_engine
from utils import (
    branding,
    design,
    environment,
    metrics,
    monitoring,
    notifications,
    platforms,
    rate_limits,
)
from utils.embeds import build_game_message, build_roles_embed, source_label
from utils.logging_setup import log_event
from utils.offers import (
    classify_free_kind,
    filter_offers,
    is_dlc_offer,
    normalize_genres,
    normalize_platforms,
)
from utils.permissions import (
    admin_note,
    category_overwrites,
    clean_access_roles,
    describe_access,
    game_channel_overwrites,
    inactive_game_channel_overwrites,
    missing_setup_permissions,
    roles_channel_overwrites,
)

log = logging.getLogger(__name__)

ROLES_CHANNEL_HINT = f"`#{config.ROLES_CHANNEL}`"


# ---------- Boutons de choix des rôles ----------


class RoleButton(discord.ui.Button):
    """Bouton d'un rôle d'alerte : une plateforme, ou le salon des DLC gratuits."""

    def __init__(self, key: str):
        is_dlc = key == config.DLC_ROUTE
        super().__init__(
            label=config.DLC_ROLE_LABEL if is_dlc else platforms.display_name(key),
            emoji=config.DLC_EMOJI if is_dlc else platforms.emoji(key),
            style=discord.ButtonStyle.secondary,
            custom_id=f"role:{key}",
        )
        self.key = key

    @property
    def is_dlc(self) -> bool:
        return self.key == config.DLC_ROUTE

    async def callback(self, interaction: discord.Interaction):
        decision, limit = rate_limits.consume_command_with_limit("roles", interaction)
        if not decision.allowed:
            await interaction.response.send_message(
                rate_limits.format_limit_message(limit, decision.retry_after), ephemeral=True
            )
            return
        if self.is_dlc:
            # Le salon des DLC peut être masqué par un admin : le bouton ne doit
            # alors attribuer aucun rôle, sinon il donnerait accès à un salon caché.
            if not await database.is_dlc_active(interaction.guild.id):
                await interaction.response.send_message(
                    "Le salon des DLC gratuits n'est pas activé sur ce serveur. "
                    "Demande à un admin de relancer `/setup-auto`.",
                    ephemeral=True,
                )
                return
            role_id = await database.get_dlc_role(interaction.guild.id)
        else:
            selected = await database.get_guild_platforms(interaction.guild.id)
            if selected is not None and self.key not in selected:
                await interaction.response.send_message(
                    "Cette plateforme n'est plus suivie sur ce serveur. "
                    "Demande à un admin de relancer `/setup-auto`.",
                    ephemeral=True,
                )
                return
            role_id = await database.get_platform_role(interaction.guild.id, self.key)
        role = interaction.guild.get_role(role_id) if role_id else None
        if role is not None and getattr(role, "permissions", discord.Permissions.none()).value:
            await interaction.response.send_message(
                "Ce rôle possède des permissions : attribution automatique refusée. Contacte un admin.",
                ephemeral=True,
            )
            return
        if role is None:
            await interaction.response.send_message(
                "Ce rôle n'existe plus. Un admin doit relancer `/setup-auto`.",
                ephemeral=True,
            )
            return
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                msg = f"Rôle **{role.name}** retiré."
            else:
                await interaction.user.add_roles(role)
                quoi = "les nouveaux DLC et contenus" if self.is_dlc else "les nouveaux jeux"
                msg = (
                    f"Rôle **{role.name}** ajouté. Le salon est maintenant visible "
                    f"et tu seras mentionné pour {quoi}."
                )
        except discord.Forbidden:
            msg = (
                "Je ne peux pas gérer ce rôle. Vérifie que le bot a **Gérer les rôles** et que son rôle "
                "est placé au-dessus de ce rôle dans les paramètres du serveur."
            )
        except discord.HTTPException:
            log.exception("Erreur Discord pendant la gestion du rôle %s", role.id)
            msg = "Discord n'a pas pu modifier ce rôle. Réessaie dans quelques instants."
        await interaction.response.send_message(msg, ephemeral=True)


class RolesView(discord.ui.View):
    def __init__(self, keys: list):
        super().__init__(timeout=None)  # permanent : survit aux redémarrages
        for key in keys:
            self.add_item(RoleButton(key))


# ---------- Menus de configuration ----------


class PlatformSelect(discord.ui.Select):
    def __init__(self, selected=()):
        options = [
            discord.SelectOption(
                label=platforms.display_name(key),
                value=key,
                emoji=platforms.emoji(key),
                default=key in selected,
            )
            for key in config.PLATFORM_KEYS
        ]
        super().__init__(
            placeholder="1️⃣ Coche les plateformes à suivre",
            min_values=1,
            max_values=len(options),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.platforms = list(self.values)
        for option in self.options:
            option.default = option.value in self.values
        await self.view.refresh(interaction)


class AccessRoleSelect(discord.ui.RoleSelect):
    """Qui a le droit de VOIR le salon des rôles (personne ne peut y écrire de toute façon)."""

    def __init__(self, defaults=()):
        kwargs = dict(
            placeholder="Optionnel : limiter l'accès au panneau (vide = tout le monde)",
            min_values=0,
            max_values=config.MAX_ACCESS_ROLES,
            row=1,
        )
        try:
            super().__init__(default_values=list(defaults), **kwargs)
        except TypeError:  # discord.py < 2.4 : pas de valeurs pré-cochées
            super().__init__(**kwargs)

    async def callback(self, interaction: discord.Interaction):
        self.view.access_roles = clean_access_roles(interaction.guild, self.values)
        await self.view.refresh(interaction)


class ConfigView(discord.ui.View):
    """Base commune : garde le menu des rôles d'accès à jour."""

    def __init__(self, cog, access_roles=()):
        super().__init__(timeout=300)
        self.cog = cog
        self.message = None
        self.busy = False
        self.access_roles = list(access_roles)
        self.access_select = AccessRoleSelect(self.access_roles)
        self.add_item(self.access_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Cette configuration est réservée aux administrateurs du serveur.", ephemeral=True
            )
            return False
        if self.busy or self.is_finished():
            await interaction.response.send_message(
                "Ce panneau est déjà utilisé ou expiré. Relance `/setup-auto`.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        if self.message is not None and not self.busy:
            try:
                await self.message.edit(
                    content="Panneau expiré : relance `/setup-auto`. Tes réglages sont conservés.",
                    view=None,
                )
            except discord.HTTPException:
                pass

    async def on_error(self, interaction, error, item):
        log.error("Erreur du panneau de configuration", exc_info=(type(error), error, error.__traceback__))
        message = "La configuration a été interrompue. Relance `/setup-auto` pour reprendre."
        if interaction.response.is_done():
            await interaction.edit_original_response(content=message, view=None)
        else:
            await interaction.response.send_message(message, ephemeral=True)
        self.stop()

    def summary(self) -> str:
        raise NotImplementedError

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=self.summary(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def reset_access_select(self):
        """Remet le menu à zéro pour que l'affichage colle au choix « tout le monde »."""
        self.access_roles = []
        self.remove_item(self.access_select)
        self.access_select = AccessRoleSelect()
        self.add_item(self.access_select)

    @discord.ui.button(label="Tout le monde", emoji="👥", style=discord.ButtonStyle.secondary, row=2)
    async def everyone(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.reset_access_select()
        await self.refresh(interaction)

    async def finish(self, interaction: discord.Interaction, report: str):
        await interaction.edit_original_response(
            content=report, view=None, allowed_mentions=discord.AllowedMentions.none()
        )
        self.stop()


class SetupView(ConfigView):
    """/setup-auto : plateformes suivies, salon des DLC et accès au panneau des rôles."""

    def __init__(
        self, cog, platform_keys=(), access_roles=(), *, already_configured=None, include_dlc=True
    ):
        super().__init__(cog, access_roles)
        self.platforms = list(platform_keys)
        self.already_configured = bool(platform_keys) if already_configured is None else already_configured
        self.include_dlc = bool(include_dlc)
        self.add_item(PlatformSelect(self.platforms))
        self.dlc_button = discord.ui.Button(
            emoji=config.DLC_EMOJI, style=discord.ButtonStyle.secondary, row=2
        )
        self.dlc_button.callback = self.toggle_dlc
        self._sync_dlc_button()
        self.add_item(self.dlc_button)

    def _sync_dlc_button(self):
        self.dlc_button.label = "Salon DLC : inclus" if self.include_dlc else "Salon DLC : masqué"
        self.dlc_button.style = (
            discord.ButtonStyle.success if self.include_dlc else discord.ButtonStyle.secondary
        )

    async def toggle_dlc(self, interaction: discord.Interaction):
        """Ajoute ou retire le salon des DLC sans toucher aux jeux complets."""
        self.include_dlc = not self.include_dlc
        self._sync_dlc_button()
        await self.refresh(interaction)

    def summary(self) -> str:
        chosen = ", ".join(platforms.display_name(k) for k in self.platforms) or "—"
        if self.already_configured:
            welcome = (
                "**🎁 Serveur déjà configuré : je mets à jour les réglages sans créer de doublons.**\n"
                "Les salons ou rôles supprimés seront réparés au prochain clic.\n"
            )
        else:
            welcome = (
                "**🎁 Bienvenue sur FreeGameDrop !**\n"
                "Je vais créer automatiquement les salons, rôles et notifications de jeux gratuits.\n"
            )
        dlc_line = (
            f"3️⃣ Salon `#{config.DLC_CHANNEL}` : **inclus** "
            "(extensions et contenus gratuits séparés des jeux complets)\n"
            if self.include_dlc
            else f"3️⃣ Salon `#{config.DLC_CHANNEL}` : **masqué**\n"
        )
        return (
            welcome
            + f"1️⃣ Coche les plateformes à suivre : **{chosen}**\n"
            + f"2️⃣ (Optionnel) Qui voit {ROLES_CHANNEL_HINT} : {describe_access(self.access_roles)}\n"
            + "Laisse l'accès du panneau vide pour le rendre visible à tous.\n"
            + dlc_line
            + "🔒 Les salons sont en lecture seule pour les membres ; les boutons restent utilisables.\n"
            + "Clique sur **Créer / mettre à jour** pour terminer."
        )

    @discord.ui.button(
        label="Créer / mettre à jour", emoji="✅", style=discord.ButtonStyle.success, row=2
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.platforms:
            await interaction.response.send_message(
                "Coche d'abord au moins une plateforme dans le menu 1️⃣.", ephemeral=True
            )
            return
        self.busy = True
        await interaction.response.edit_message(content="⏳ Configuration en cours…", view=None)
        report = await self.cog.apply_setup(
            interaction.guild,
            self.platforms,
            self.access_roles,
            include_dlc=self.include_dlc,
        )
        if report.startswith("✅"):
            try:
                sent = await self.cog.run_check(target_guild_id=interaction.guild.id)
                if sent:
                    report += f"\n\n🔎 Première vérification terminée : **{sent} annonce(s)** envoyée(s)."
                else:
                    report += (
                        "\n\n🔎 Aucune annonce : offres déjà annoncées, absentes ou source indisponible ; "
                        "la surveillance automatique continue ensuite."
                    )
            except Exception:
                log.exception("La configuration est terminée, mais la vérification immédiate a échoué")
                report += (
                    "\n\n⚠️ La configuration est terminée, mais la première vérification a échoué. "
                    "Le bot réessaiera automatiquement."
                )
        await self.finish(interaction, report)


class AccessView(ConfigView):
    """/acces-salon-roles : change qui voit le salon sans tout reconstruire."""

    def summary(self) -> str:
        return (
            f"**Accès à {ROLES_CHANNEL_HINT}**\n"
            f"Visible par : {describe_access(self.access_roles)}\n"
            "🔒 Le salon reste en **lecture seule** pour tout le monde.\n"
            "Laisse le menu vide (ou clique sur **Tout le monde**) pour l'ouvrir à tous, "
            "puis clique sur **Appliquer**."
        )

    @discord.ui.button(label="Appliquer", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="⏳ Mise à jour des permissions…", view=None)
        report = await self.cog.apply_access(interaction.guild, self.access_roles)
        await self.finish(interaction, report)


class GamePageButton(discord.ui.Button):
    """Bouton précédent/suivant du navigateur d'offres."""

    def __init__(self, browser: "GameBrowserView", direction: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=1)
        self.browser = browser
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        await self.browser.change_page(interaction, self.direction)


class FavoriteToggleButton(discord.ui.Button):
    """Ajoute ou retire l'offre affichée des favoris du membre qui a lancé la commande."""

    def __init__(self, browser: "GameBrowserView"):
        super().__init__(style=discord.ButtonStyle.secondary, row=0)
        self.browser = browser
        self.sync_label()

    def sync_label(self):
        game_id = str(self.browser.current_game.get("id"))
        saved = game_id in self.browser.favorite_ids
        self.label = "Retirer des favoris" if saved else "Ajouter aux favoris"
        self.emoji = "💔" if saved else "❤️"

    async def callback(self, interaction: discord.Interaction):
        await self.browser.toggle_favorite(interaction)


class GameBrowserView(discord.ui.View):
    """Pagination éphémère des offres avec un bouton de favoris par membre."""

    def __init__(
        self,
        games: list[dict],
        owner_id: int,
        favorite_ids=(),
        *,
        showing_favorites: bool = False,
        timeout: float = 180,
    ):
        super().__init__(timeout=timeout)
        self.games = list(games)
        if not self.games:
            raise ValueError("GameBrowserView requires at least one game")
        self.owner_id = owner_id
        self.favorite_ids = {str(item_id) for item_id in favorite_ids}
        self.showing_favorites = showing_favorites
        self.page = 0
        self.message = None
        self.claim_button = None
        self.favorite_button = FavoriteToggleButton(self)
        self.previous_button = GamePageButton(self, -1, "Précédent")
        self.next_button = GamePageButton(self, 1, "Suivant")
        self.add_item(self.favorite_button)
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self._sync_components()

    @property
    def current_game(self) -> dict:
        return self.games[self.page]

    @property
    def page_count(self) -> int:
        return len(self.games)

    def current_embed(self) -> discord.Embed:
        embed, _ = build_game_message(self.current_game)
        label = source_label(self.current_game)
        embed.set_footer(
            text=f"{design.FOOTER} · Source : {label} · {self.page + 1}/{self.page_count}"
        )
        return embed

    def _sync_components(self):
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.page_count - 1
        self.favorite_button.sync_label()

        if self.claim_button is not None:
            self.remove_item(self.claim_button)
            self.claim_button = None

        url = self.current_game.get("open_giveaway_url") or self.current_game.get("gamerpower_url")
        if url:
            self.claim_button = discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="Récupérer le jeu",
                emoji="🎁",
                url=url,
                row=0,
            )
            self.add_item(self.claim_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Seule la personne qui a lancé la commande peut parcourir cette liste.",
                ephemeral=True,
            )
            return False
        decision = rate_limits.consume(rate_limits.LIMITS["interactions"], interaction.user.id)
        if not decision.allowed:
            await interaction.response.send_message(
                rate_limits.format_limit_message(
                    rate_limits.LIMITS["interactions"], decision.retry_after
                ),
                ephemeral=True,
            )
            return False
        return True

    async def change_page(self, interaction: discord.Interaction, direction: int):
        self.page = min(max(self.page + direction, 0), self.page_count - 1)
        self._sync_components()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    async def toggle_favorite(self, interaction: discord.Interaction):
        game_id = str(self.current_game.get("id"))
        is_saved = await database.toggle_favorite(self.owner_id, game_id)
        if is_saved:
            self.favorite_ids.add(game_id)
        else:
            self.favorite_ids.discard(game_id)
            if self.showing_favorites:
                self.games.pop(self.page)
                if not self.games:
                    self.stop()
                    await interaction.response.edit_message(
                        content="Tu n'as plus aucun favori enregistré.", embed=None, view=None
                    )
                    return
                self.page = min(self.page, self.page_count - 1)

        self._sync_components()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.style is not discord.ButtonStyle.link:
                item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class ConfirmDeleteDataView(discord.ui.View):
    """Confirmation avant d'effacer les favoris associés à un compte Discord."""

    def __init__(self, owner_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Seule la personne qui a lancé la commande peut confirmer cette suppression.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Supprimer mes favoris", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        count = await database.clear_user_favorites(self.owner_id)
        await interaction.response.edit_message(
            content=f"Suppression terminée : **{count}** favori(s) effacé(s).",
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Annulé, aucune donnée n'a été supprimée.", view=None)
        self.stop()


class ConfirmReset(discord.ui.View):
    """/reset-all : garde-fou avant la suppression."""

    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.button(label="Tout supprimer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Nettoyage en cours...", view=None)
        report = await self.cog.wipe_guild(interaction.guild)
        try:
            await interaction.edit_original_response(content=report)
        except discord.HTTPException:
            pass  # par exemple si la commande a été lancée dans un salon supprimé

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Annulé, rien n'a été supprimé.", view=None)


# ---------- Le cog ----------


class Jeux(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.roles_channels = {}  # {serveur: salon des rôles} pour le nettoyage des messages
        self.check_games.change_interval(hours=config.CHECK_INTERVAL_HOURS)
        self.check_games.start()

    async def cog_load(self):
        # Les boutons survivent aux redémarrages, y compris celui du salon des DLC.
        self.bot.add_view(RolesView([*config.PLATFORM_KEYS, config.DLC_ROUTE]))
        self.roles_channels = await database.get_all_roles_channels()

    async def cog_unload(self):
        self.check_games.cancel()

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """Répond proprement aux refus de permission et aux erreurs de commande inattendues."""
        if isinstance(error, app_commands.MissingPermissions):
            message = "Cette commande est réservée aux administrateurs du serveur."
        elif isinstance(error, rate_limits.RateLimited):
            message = str(error)
        elif isinstance(error, app_commands.CommandOnCooldown):
            wait = max(1, math.ceil(error.retry_after))
            message = f"Réessaie dans {wait} seconde(s)."
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

    # ----- création / mise à jour -----

    async def ensure_platform_role(self, guild: discord.Guild, key: str) -> discord.Role:
        """Crée le rôle de la plateforme, ou remet son nom et sa couleur à jour."""
        wanted = platforms.role_name(key)
        role = None
        role_id = await database.get_platform_role(guild.id, key)
        if role_id:
            role = guild.get_role(role_id)
        if role is None:
            role = discord.utils.get(guild.roles, name=wanted) or discord.utils.get(
                guild.roles, name=f"Jeux {platforms.display_name(key)}"
            )
        if role is None:
            role = await guild.create_role(
                name=wanted,
                colour=platforms.role_colour(key),
                mentionable=True,
                reason="Rôle d'alerte jeux gratuits",
            )
        else:
            if getattr(role, "permissions", discord.Permissions.none()).value:
                raise ValueError(
                    "Un rôle de plateforme possède des permissions : renomme-le ou retire ses permissions."
                )
            await role.edit(
                name=wanted,
                colour=platforms.role_colour(key),
                mentionable=True,
                reason="Mise à jour du rôle jeux gratuits",
            )
        await database.set_platform_role(guild.id, key, role.id)
        return role

    @staticmethod
    def _find_named_channel(guild: discord.Guild, category: discord.CategoryChannel, name: str):
        """Refuse les homonymes non enregistrés plutôt que de modifier leurs accès."""
        candidates = [*category.text_channels, *getattr(guild, "text_channels", [])]
        if any(channel.name == name for channel in candidates):
            raise ValueError(
                f"Un salon non enregistré porte déjà le nom #{name}. "
                "Renomme ce salon pour éviter de modifier ses accès ou ses messages."
            )
        return None


    async def ensure_platform_channel(
        self,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        key: str,
        role: discord.Role,
        known_id=None,
    ) -> discord.TextChannel:
        """Crée ou répare le salon : un nom déjà présent sur le serveur est réutilisé."""
        overwrites = game_channel_overwrites(guild, role)
        name = platforms.channel_name(key)
        channel = guild.get_channel(known_id) if known_id else None
        if channel is None:
            channel = self._find_named_channel(guild, category, name)
        if channel is None:
            channel = await category.create_text_channel(
                name,
                topic=f"Jeux gratuits : {platforms.display_name(key)}",
                overwrites=overwrites,
            )
        else:
            updates = {
                "name": name,
                "topic": f"Jeux gratuits : {platforms.display_name(key)}",
                "overwrites": overwrites,
            }
            if getattr(channel, "category", None) is not category:
                updates["category"] = category
            await channel.edit(**updates)
        await database.set_platform_channel(guild.id, key, channel.id)
        return channel

    async def ensure_dlc_role(self, guild: discord.Guild) -> discord.Role:
        """Crée le rôle du salon des DLC, ou remet son nom et sa couleur à jour."""
        wanted = config.DLC_ROLE_NAME
        role = None
        role_id = await database.get_dlc_role(guild.id)
        if role_id:
            role = guild.get_role(role_id)
        if role is None:
            role = discord.utils.get(guild.roles, name=wanted)
        if role is None:
            role = await guild.create_role(
                name=wanted,
                colour=discord.Colour(config.DLC_COLOUR),
                mentionable=True,
                reason="Rôle d'alerte DLC gratuits",
            )
        else:
            if getattr(role, "permissions", discord.Permissions.none()).value:
                raise ValueError(
                    "Le rôle du salon des DLC possède des permissions : "
                    "renomme-le ou retire ses permissions."
                )
            await role.edit(
                name=wanted,
                colour=discord.Colour(config.DLC_COLOUR),
                mentionable=True,
                reason="Mise à jour du rôle DLC gratuits",
            )
        await database.set_dlc_role(guild.id, role.id)
        return role

    async def ensure_dlc_channel(
        self,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        role: discord.Role,
    ) -> discord.TextChannel:
        """Crée ou répare le salon unique des DLC gratuits.

        Un salon masqué reste retrouvé par son identifiant : le réactiver ne crée
        donc jamais de doublon.
        """
        overwrites = game_channel_overwrites(guild, role)
        channel_id = await database.get_dlc_channel(guild.id, include_inactive=True)
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            channel = self._find_named_channel(guild, category, config.DLC_CHANNEL)
        if channel is None:
            channel = await category.create_text_channel(
                config.DLC_CHANNEL, topic=config.DLC_TOPIC, overwrites=overwrites
            )
        else:
            updates = {
                "name": config.DLC_CHANNEL,
                "topic": config.DLC_TOPIC,
                "overwrites": overwrites,
            }
            if getattr(channel, "category", None) is not category:
                updates["category"] = category
            await channel.edit(**updates)
        await database.set_dlc_channel(guild.id, channel.id, active=True)
        return channel

    async def set_dlc_enabled(
        self, guild: discord.Guild, category: discord.CategoryChannel, enabled: bool
    ) -> tuple[str | None, discord.TextChannel | None]:
        """Active ou masque le salon des DLC, sans jamais supprimer son contenu."""
        if enabled:
            role = await self.ensure_dlc_role(guild)
            channel = await self.ensure_dlc_channel(guild, category, role)
            return f"{channel.mention} → {role.mention} (DLC et contenus)", channel

        channel_id = await database.get_dlc_channel(guild.id, include_inactive=True)
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            await database.set_dlc_active(guild.id, False)
            return None, None
        await channel.edit(overwrites=inactive_game_channel_overwrites(guild))
        await database.set_dlc_active(guild.id, False)
        return f"{channel.mention} (masqué, réactivable via `/setup-auto`)", None

    async def ensure_roles_channel(
        self, guild: discord.Guild, category: discord.CategoryChannel, access_roles: list
    ) -> discord.TextChannel:
        """Crée ou répare le panneau de rôles, même s'il a été renommé/déplacé."""
        overwrites = roles_channel_overwrites(guild, access_roles)
        channel_id = await database.get_roles_channel(guild.id)
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            channel = self._find_named_channel(guild, category, config.ROLES_CHANNEL)

        if channel is None:
            channel = await category.create_text_channel(
                config.ROLES_CHANNEL, topic=config.ROLES_TOPIC, overwrites=overwrites
            )
        else:
            updates = {
                "name": config.ROLES_CHANNEL,
                "overwrites": overwrites,
                "topic": config.ROLES_TOPIC,
            }
            if getattr(channel, "category", None) is not category:
                updates["category"] = category
            await channel.edit(**updates)

        await database.set_roles_channel(guild.id, channel.id)
        await database.set_roles_channel_access(guild.id, [r.id for r in access_roles])
        self.roles_channels[guild.id] = channel.id
        return channel

    async def deactivate_unselected_channels(
        self, guild: discord.Guild, selected_keys: set[str]
    ) -> list[str]:
        """Masque les salons décochés sans les supprimer : ils pourront être réactivés."""
        disabled = []
        known_channels = await database.get_platform_channels(guild.id)
        for key, channel_id in known_channels.items():
            if key in selected_keys:
                continue
            channel = guild.get_channel(channel_id)
            if channel is None:
                continue
            await channel.edit(overwrites=inactive_game_channel_overwrites(guild))
            disabled.append(platforms.display_name(key))
        return disabled

    async def post_roles_message(self, channel: discord.TextChannel, keys: list):
        """Met à jour le panneau en place sans permission de lecture/suppression de messages."""
        guild_id = channel.guild.id
        message_id = await database.get_roles_panel_message(guild_id)
        if message_id is not None:
            partial = channel.get_partial_message(message_id)
            try:
                await partial.edit(embed=build_roles_embed(), view=RolesView(keys))
                return
            except discord.NotFound:
                log.info("Le panneau des rôles du serveur %s a été supprimé, je le recrée", guild_id)

        # Migration douce : nettoie les anciens panneaux seulement si ces permissions sont
        # déjà accordées. Elles ne sont plus nécessaires au parcours de configuration.
        permissions = channel.guild.me.guild_permissions
        if (
            message_id is None
            and getattr(permissions, "read_message_history", False)
            and getattr(permissions, "manage_messages", False)
        ):
            try:
                async for old in channel.history(limit=50):
                    if old.author.id == channel.guild.me.id:
                        await old.delete()
            except discord.HTTPException:
                log.warning("Impossible de nettoyer les anciens panneaux sur le serveur %s", guild_id)

        message = await rate_limits.spaced_send(
            channel.send, key=f"channel:{channel.id}", embed=build_roles_embed(), view=RolesView(keys)
        )
        await database.set_roles_panel_message(guild_id, message.id)

    async def apply_setup(
        self,
        guild: discord.Guild,
        platform_keys: list,
        access_roles: list,
        *,
        include_dlc: bool = True,
    ) -> str:
        """Met à jour une configuration sans doublons ; les relances réparent l'état partiel."""
        if not hasattr(self, "_setup_locks"):
            self._setup_locks = {}
        lock = self._setup_locks.setdefault(guild.id, asyncio.Lock())
        async with lock:
            return await self._apply_setup_locked(
                guild, platform_keys, access_roles, include_dlc=include_dlc
            )

    async def _apply_setup_locked(
        self,
        guild: discord.Guild,
        platform_keys: list,
        access_roles: list,
        *,
        include_dlc: bool = True,
    ) -> str:
        selected = list(dict.fromkeys(key for key in platform_keys if key in config.PLATFORM_KEYS))
        if not selected:
            return "⚠️ Coche au moins une plateforme, puis relance `/setup-auto`."

        missing = missing_setup_permissions(guild)
        if missing:
            invite = branding.build_invite_url(self.bot.user.id) if self.bot.user else None
            return (
                "⚠️ Je ne peux pas terminer la configuration : permission(s) manquante(s) : **"
                + "**, **".join(missing)
                + "**.\nRéinvite FreeGameDrop avec ces permissions et relance `/setup-auto`."
                + (f"\nLien d'autorisation : {invite}" if invite else "")
            )

        access_roles = clean_access_roles(guild, access_roles)
        created = []
        try:
            # Enregistre d'abord la sélection : une vérification parallèle ne doit pas annoncer
            # une plateforme décochée pendant que Discord crée/répare les salons.
            await database.set_guild_platforms(guild.id, selected)
            category = discord.utils.get(guild.categories, name=config.CATEGORY_NAME)
            if category is None:
                category = await guild.create_category(
                    config.CATEGORY_NAME, overwrites=category_overwrites(guild)
                )

            known_channels = await database.get_platform_channels(guild.id)
            for key in selected:
                role = await self.ensure_platform_role(guild, key)
                channel = await self.ensure_platform_channel(
                    guild, category, key, role, known_channels.get(key)
                )
                created.append(f"{channel.mention} → {role.mention}")

            disabled = await self.deactivate_unselected_channels(guild, set(selected))
            dlc_report, _ = await self.set_dlc_enabled(guild, category, include_dlc)
            roles_channel = await self.ensure_roles_channel(guild, category, access_roles)
            await roles_channel.move(beginning=True, category=category)
            panel_keys = list(selected)
            if include_dlc:
                panel_keys.append(config.DLC_ROUTE)
            await self.post_roles_message(roles_channel, panel_keys)

        except ValueError as error:
            return f"⚠️ {error} Puis relance `/setup-auto`."
        except discord.Forbidden:
            log.exception("Discord a refusé une action de configuration sur le serveur %s", guild.id)
            return (
                "⚠️ Discord a refusé une action. Vérifie que le bot a **Gérer les salons** et "
                "**Gérer les rôles**, et que son rôle est au-dessus des rôles de plateforme. "
                "Les éléments déjà créés sont conservés : relance `/setup-auto` pour réparer "
                "la configuration."
            )
        except discord.HTTPException as error:
            log.exception("Erreur Discord pendant /setup-auto sur le serveur %s", guild.id)
            return (
                f"⚠️ Discord a rencontré une erreur (code {error.status}). La configuration peut être "
                "partielle, mais rien n'est perdu : corrige le problème puis relance `/setup-auto`."
            )
        except Exception:
            log.exception("Erreur inattendue pendant /setup-auto sur le serveur %s", guild.id)
            return (
                "⚠️ Une erreur inattendue a interrompu la configuration. Les éléments déjà créés "
                "sont conservés ; relance `/setup-auto` pour reprendre."
            )

        disabled_note = (
            "\nPlateformes décochées masquées (elles restent réactivables) : " + ", ".join(disabled) + "."
            if disabled
            else ""
        )
        if include_dlc and "gamerpower_loot" not in config.OFFER_SOURCES:
            dlc_report += (
                " — ⚠️ source `gamerpower_loot` absente de `OFFER_SOURCES` : "
                "seuls les DLC fournis par les autres sources arriveront."
            )
        dlc_note = f"\nSalon des DLC gratuits : {dlc_report}" if dlc_report else ""
        return (
            "✅ **Configuration terminée !**\n"
            + "\n".join(created)
            + dlc_note
            + f"\nPanneau de choix : {roles_channel.mention} "
            + f"(lecture seule, visible par : {describe_access(access_roles)})"
            + disabled_note
            + admin_note(guild)
        )

    async def apply_access(self, guild: discord.Guild, access_roles: list) -> str:
        """Change qui voit le salon des rôles, sans toucher au reste."""
        access_roles = clean_access_roles(guild, access_roles)
        channel_id = await database.get_roles_channel(guild.id)
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None:
            category = discord.utils.get(guild.categories, name=config.CATEGORY_NAME)
            if category is not None:
                channel = discord.utils.get(category.text_channels, name=config.ROLES_CHANNEL)
        if channel is None:
            return "Je ne trouve pas le salon des rôles. Lance d'abord `/setup-auto`."

        try:
            await channel.edit(
                overwrites=roles_channel_overwrites(guild, access_roles), topic=config.ROLES_TOPIC
            )
        except discord.Forbidden:
            return "Il me manque la permission **Gérer les salons** pour modifier ce salon."

        await database.set_roles_channel(guild.id, channel.id)
        await database.set_roles_channel_access(guild.id, [r.id for r in access_roles])
        self.roles_channels[guild.id] = channel.id
        return (
            f"{channel.mention} est en **lecture seule** et visible par : "
            f"{describe_access(access_roles)}." + admin_note(guild)
        )

    # ----- nettoyage -----

    async def wipe_guild(self, guild: discord.Guild) -> str:
        """Supprime tout ce que le bot a créé (salons, rôles, catégorie) et ses anciens messages."""
        deleted = set()
        n_channels = n_roles = n_msgs = 0
        problems = set()

        async def delete_channel(channel):
            nonlocal n_channels
            try:
                await channel.delete(reason="Nettoyage /reset-all")
                deleted.add(channel.id)
                n_channels += 1
            except discord.Forbidden:
                problems.add("**Gérer les salons**")
            except discord.HTTPException:
                pass

        # salons de jeux enregistrés
        for channel_id in (await database.get_platform_channels(guild.id)).values():
            channel = guild.get_channel(channel_id)
            if channel:
                await delete_channel(channel)

        # salon des DLC enregistré, y compris s'il a été masqué par un admin
        dlc_channel_id = await database.get_dlc_channel(guild.id, include_inactive=True)
        dlc_channel = guild.get_channel(dlc_channel_id) if dlc_channel_id else None
        if dlc_channel and dlc_channel.id not in deleted:
            await delete_channel(dlc_channel)

        # salon des rôles enregistré
        roles_channel_id = await database.get_roles_channel(guild.id)
        roles_channel = guild.get_channel(roles_channel_id) if roles_channel_id else None
        if roles_channel and roles_channel.id not in deleted:
            await delete_channel(roles_channel)

        # rôles enregistrés
        for role_id in (await database.get_guild_platform_roles(guild.id)).values():
            role = guild.get_role(role_id)
            if role:
                try:
                    await role.delete(reason="Nettoyage /reset-all")
                    n_roles += 1
                except discord.Forbidden:
                    problems.add("**Gérer les rôles**")
                except discord.HTTPException:
                    pass

        # rôle du salon des DLC
        dlc_role_id = await database.get_dlc_role(guild.id)
        dlc_role = guild.get_role(dlc_role_id) if dlc_role_id else None
        if dlc_role:
            try:
                await dlc_role.delete(reason="Nettoyage /reset-all")
                n_roles += 1
            except discord.Forbidden:
                problems.add("**Gérer les rôles**")
            except discord.HTTPException:
                pass

        # Ne jamais supprimer un salon non enregistré sur la seule base de son nom.
        category = discord.utils.get(guild.categories, name=config.CATEGORY_NAME)
        if category:
            if all(c.id in deleted for c in category.channels):
                try:
                    await category.delete(reason="Nettoyage /reset-all")
                    n_channels += 1
                except discord.HTTPException:
                    pass

        # anciens messages du bot dans l'ancien salon (ancienne commande /setup)
        legacy_id = await database.get_channel(guild.id)
        legacy = guild.get_channel(legacy_id) if legacy_id else None
        if legacy and legacy.id not in deleted:
            try:
                async for msg in legacy.history(limit=100):
                    if msg.author.id == guild.me.id:
                        await msg.delete()
                        n_msgs += 1
            except discord.HTTPException:
                problems.add("**Voir les anciens messages**")

        await database.clear_guild(guild.id)
        self.roles_channels.pop(guild.id, None)

        report = (
            f"Nettoyage terminé : **{n_channels}** salon(s)/catégorie, "
            f"**{n_roles}** rôle(s) et **{n_msgs}** message(s) supprimés.\n"
            "Relance `/setup-auto` pour tout recréer."
        )
        if problems:
            report += "\nPermission(s) manquante(s) : " + ", ".join(sorted(problems)) + "."
        return report

    # ----- surveillance -----

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        message = (
            "🎁 **Bienvenue sur FreeGameDrop !**\n"
            "Un administrateur peut lancer `/setup-auto`, choisir ses plateformes et cliquer sur "
            "**Créer / mettre à jour**. Je crée les salons et les rôles, puis vérifie les offres.\n"
            "Les membres choisissent ensuite leurs alertes dans le panneau de rôles."
        )
        candidates = [guild.system_channel, *guild.text_channels]
        seen = set()
        for channel in candidates:
            if channel is None or channel.id in seen:
                continue
            seen.add(channel.id)
            permissions = channel.permissions_for(guild.me)
            if not permissions.view_channel or not permissions.send_messages:
                continue
            try:
                await rate_limits.spaced_send(
                    channel.send,
                    key=f"channel:{channel.id}",
                    content=message,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            except discord.HTTPException:
                continue
        log.info("Accueil impossible sur le serveur %s ; /setup-auto reste disponible", guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Le salon de choix des rôles est strictement réservé aux boutons :
        tout message qui n'est pas celui du bot est supprimé (même celui d'un admin,
        que les permissions Discord ne peuvent pas bloquer)."""
        if message.guild is None or message.author.id == self.bot.user.id:
            return
        channel = message.channel
        known_id = self.roles_channels.get(message.guild.id)
        if known_id is not None:
            if channel.id != known_id:
                return
        else:
            category = getattr(channel, "category", None)
            if (
                getattr(channel, "name", None) != config.ROLES_CHANNEL
                or category is None
                or category.name != config.CATEGORY_NAME
            ):
                return
        try:
            await message.delete()
        except discord.Forbidden:
            log.warning(
                "Impossible de supprimer un message dans #%s : il me faut la permission Gérer les messages.",
                config.ROLES_CHANNEL,
            )
        except discord.HTTPException:
            pass

    async def run_check(self, *, target_guild_id: int | None = None) -> int:
        """Envoie les jeux gratuits sans doublonner les vérifications parallèles."""
        if not hasattr(self, "_run_check_lock"):
            self._run_check_lock = asyncio.Lock()
        async with self._run_check_lock:
            return await self._run_check_once(target_guild_id=target_guild_id)

    async def _announce_offer(
        self,
        game: dict,
        targets: list[tuple],
        *,
        mention: str,
        invite_url: str | None,
    ) -> tuple[int, bool]:
        """Envoie une offre à ses salons cibles, une seule fois par salon.

        `targets` contient `(serveur, salon, rôle, clé anti-doublon)`. Retourne
        `(annonces envoyées, au moins un salon prévenu)`.
        """
        embed, view = build_game_message(game, invite_url=invite_url)
        item_id = str(game.get("id"))
        sent = 0
        for guild_id, channel_id, role_id, sent_key in targets:
            if await database.is_sent(guild_id, sent_key):
                continue
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                log.warning(
                    "Salon %s du serveur %s introuvable ; relance /setup-auto pour le réparer",
                    channel_id,
                    guild_id,
                )
                continue
            content = f"<@&{role_id}> {mention}" if role_id else None
            try:
                await rate_limits.spaced_send(
                    channel.send,
                    key=f"channel:{channel_id}",
                    content=content,
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )
                await database.mark_sent(guild_id, sent_key)
                sent += 1
                log_event(
                    "announce.sent",
                    offer_id=item_id,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    route=sent_key.rsplit(":", 1)[-1],
                    offer_type=game.get("offer_type"),
                )
            except discord.Forbidden as error:
                monitoring.HEALTH.record_error()
                log.warning(
                    "Discord refuse l'envoi sur le serveur %s (vérifie Voir les salons, "
                    "Envoyer des messages et Intégrer des liens) : %s",
                    guild_id,
                    error,
                )
            except discord.HTTPException as error:
                monitoring.HEALTH.record_error()
                log.warning("Envoi impossible sur le serveur %s : %s", guild_id, error)
        return sent, sent > 0

    async def _run_check_once(self, *, target_guild_id: int | None = None) -> int:
        """Envoie les offres pas encore annoncées. Retourne le nombre d'annonces.

        Séparation stricte : les jeux complets partent dans le salon de leur
        plateforme, les DLC/contenus dans le salon unique des DLC. Une offre ne
        peut donc plus atterrir dans les deux.
        """
        log_event("check.started", sources=len(config.OFFER_SOURCES))
        response = await offer_engine.fetch_offers()
        log_event("check.fetched", offers=len(response))
        games = [game for game in response if isinstance(game, dict) and game.get("id") is not None]
        await database.save_giveaways(games)
        await database.set_bot_state("last_check_at", datetime.now(timezone.utc).isoformat())
        routes = await database.get_routes()
        dlc_routes = await database.get_all_dlc_routes()
        guild_platforms = await database.get_all_guild_platforms()
        if target_guild_id is not None:
            routes = [route for route in routes if route[0] == target_guild_id]
            dlc_routes = {
                guild_id: targets
                for guild_id, targets in dlc_routes.items()
                if guild_id == target_guild_id
            }
        roles = await database.get_all_platform_roles()
        invite_url = branding.build_invite_url(self.bot.user.id) if self.bot.user else None
        new_games = []
        sent = 0

        # 1️⃣ Jeux complets → un salon par plateforme.
        game_offers = [game for game in games if not is_dlc_offer(game)][: config.MAX_GAMES]
        for game in game_offers:
            item_id = str(game.get("id"))
            targets = [
                (guild_id, channel_id, roles.get((guild_id, route)), f"{item_id}:{route}")
                for guild_id, route, channel_id, _ in routes
                if platforms.matches(game, [route])
            ]
            count, announced = await self._announce_offer(
                game, targets, mention="nouveau jeu gratuit !", invite_url=invite_url
            )
            sent += count
            if announced:
                new_games.append(game)

        # 2️⃣ DLC et contenus → salon unique des DLC, dans la limite dédiée.
        dlc_offers = [game for game in games if is_dlc_offer(game)][: config.MAX_DLC_GAMES]
        for game in dlc_offers:
            item_id = str(game.get("id"))
            targets = []
            for guild_id, (channel_id, role_id) in dlc_routes.items():
                selection = guild_platforms.get(guild_id)
                # Le salon des DLC respecte les plateformes suivies par le serveur ;
                # une configuration historique sans sélection reçoit tout.
                if selection is not None and not platforms.matches(game, selection):
                    continue
                targets.append(
                    (guild_id, channel_id, role_id, f"{item_id}:{config.DLC_ROUTE}")
                )
            count, announced = await self._announce_offer(
                game, targets, mention="nouveau DLC gratuit !", invite_url=invite_url
            )
            sent += count
            if announced:
                new_games.append(game)

        log_event(
            "check.finished",
            announcements=sent,
            new_offers=len(new_games),
            game_offers=len(game_offers),
            dlc_offers=len(dlc_offers),
        )
        if target_guild_id is not None:
            return sent

        for label, callback, args in (
            ("nouvelles offres DM", notifications.notify_new_offers, (self.bot, new_games)),
            ("rappels DM", notifications.notify_ending_soon, (self.bot, games)),
            ("rappels serveur", notifications.send_guild_reminders, (self.bot, games)),
        ):
            try:
                await callback(*args)
            except Exception:
                log.exception("Erreur pendant l'envoi des %s", label)
        return sent

    @tasks.loop(hours=1)
    async def check_games(self):
        interval = config.CHECK_INTERVAL_HOURS * 3600
        # Mode maintenance : la veille automatique est suspendue, mais les commandes
        # d'administration (`/test-jeux`, `/check`) restent utilisables pour tester.
        if config.MAINTENANCE_MODE:
            log_event("check.skipped", reason="maintenance")
            log.info(
                "🔧 %s en maintenance : vérification automatique ignorée.",
                environment.product_name(),
            )
            return
        try:
            await self.run_check()
        except Exception as error:
            monitoring.HEALTH.record_task_run(
                "check_games", interval_seconds=interval, error=f"{type(error).__name__}: {error}"
            )
            monitoring.HEALTH.record_error()
            log_event("task.failure", level=logging.ERROR, task="check_games", error=error)
            log.exception("Erreur pendant la vérification des jeux")
        else:
            monitoring.HEALTH.record_task_run("check_games", interval_seconds=interval)
            log_event("task.run", task="check_games")

    @check_games.before_loop
    async def before_check_games(self):
        monitoring.HEALTH.register_task(
            "check_games", interval_seconds=config.CHECK_INTERVAL_HOURS * 3600
        )
        await self.bot.wait_until_ready()

    # ----- commandes -----

    async def _browse_offers(self, interaction: discord.Interaction, games: list, empty_message: str):
        """Affiche une liste d'offres en privé, avec pagination et favoris."""
        if not games:
            await interaction.followup.send(empty_message, ephemeral=True)
            return
        view = GameBrowserView(
            games,
            owner_id=interaction.user.id,
            favorite_ids=await database.get_favorite_ids(interaction.user.id),
        )
        view.message = await interaction.followup.send(
            embed=view.current_embed(), view=view, ephemeral=True, wait=True
        )

    @app_commands.command(name="free", description="Parcourt les offres de jeux gratuits du moment")
    @app_commands.describe(
        plateforme="Ne montrer que cette plateforme",
        type="Ne montrer que ce type d'offre",
        echeance="Filtrer par date de fin",
    )
    @app_commands.choices(
        plateforme=[
            app_commands.Choice(name=platforms.display_name(key), value=key)
            for key in config.PLATFORM_KEYS
        ],
        type=[
            app_commands.Choice(name=label, value=key)
            for key, label in config.OFFER_TYPE_LABELS.items()
        ],
        echeance=[
            app_commands.Choice(name="Se termine aujourd'hui", value="ends_today"),
            app_commands.Choice(name="Se termine bientôt (24h)", value="ending_soon"),
        ],
    )
    @rate_limits.limited("free")
    async def free(
        self,
        interaction: discord.Interaction,
        plateforme: str | None = None,
        type: str | None = None,
        echeance: str | None = None,
    ):
        """Liste les offres actuelles en privé et permet de les ajouter aux favoris."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            response = await offer_engine.fetch_offers(use_cache=True)
        except Exception:
            log.exception("Impossible de récupérer les offres pour /free")
            await interaction.followup.send(
                "Impossible de récupérer les offres pour le moment. Réessaie un peu plus tard.",
                ephemeral=True,
            )
            return

        if not isinstance(response, list):
            response = []
        games = [game for game in response if isinstance(game, dict) and game.get("id") is not None]
        await database.save_giveaways(games)

        preferences = await database.get_user_preferences(interaction.user.id)
        timezone_name = preferences.get("timezone") or config.DEFAULT_TIMEZONE
        games = filter_offers(
            games,
            platform=plateforme,
            offer_type=type,
            period=echeance,
            timezone_name=timezone_name,
        )
        await self._browse_offers(
            interaction,
            games,
            "Aucun jeu gratuit trouvé pour le moment, ou la source est temporairement indisponible.",
        )

    @app_commands.command(
        name="dlc", description="Parcourt les DLC, extensions et contenus gratuits du moment"
    )
    @app_commands.describe(echeance="Filtrer par date de fin")
    @app_commands.choices(
        echeance=[
            app_commands.Choice(name="Se termine aujourd'hui", value="ends_today"),
            app_commands.Choice(name="Se termine bientôt (24h)", value="ending_soon"),
        ],
    )
    @rate_limits.limited("dlc")
    async def dlc(self, interaction: discord.Interaction, echeance: str | None = None):
        """Comme `/free`, mais uniquement les DLC et contenus : jamais les jeux complets."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            response = await offer_engine.fetch_offers(use_cache=True)
        except Exception:
            log.exception("Impossible de récupérer les offres pour /dlc")
            await interaction.followup.send(
                "Impossible de récupérer les DLC pour le moment. Réessaie un peu plus tard.",
                ephemeral=True,
            )
            return

        games = [game for game in response if isinstance(game, dict) and game.get("id") is not None]
        await database.save_giveaways(games)

        preferences = await database.get_user_preferences(interaction.user.id)
        timezone_name = preferences.get("timezone") or config.DEFAULT_TIMEZONE
        dlc_games = filter_offers(
            [game for game in games if is_dlc_offer(game)],
            period=echeance,
            timezone_name=timezone_name,
        )
        await self._browse_offers(
            interaction,
            dlc_games,
            "Aucun DLC gratuit trouvé pour le moment, ou la source est temporairement indisponible.",
        )

    @app_commands.command(
        name="recap", description="Récapitule les offres découvertes ces dernières heures"
    )
    @app_commands.describe(heures="Fenêtre en heures (1 à 168, 24 par défaut)")
    @rate_limits.limited("recap")
    async def recap(self, interaction: discord.Interaction, heures: int = 24):
        """Un seul message pour voir les nouveautés, jeux complets et DLC confondus."""
        heures = min(max(int(heures), 1), 168)
        try:
            games = await database.get_offers_since(hours=heures, limit=50)
        except Exception:
            log.exception("Impossible de lire le récapitulatif des offres")
            await interaction.response.send_message(
                "Impossible de lire le catalogue pour le moment. Réessaie plus tard.",
                ephemeral=True,
            )
            return

        if not games:
            await interaction.response.send_message(
                f"Aucune nouvelle offre découverte depuis {heures} h. "
                "Le bot vérifie régulièrement : réessaie plus tard.",
                ephemeral=True,
            )
            return

        dlc_count = sum(1 for game in games if is_dlc_offer(game))
        permanent = sum(1 for game in games if classify_free_kind(game) == "permanent")
        summary = [
            f"**{len(games) - dlc_count}** jeu(x) complet(s)",
            f"**{dlc_count}** DLC/contenu(s)",
        ]
        if permanent:
            summary.append(f"**{permanent}** gratuit(s) en permanence")
        view = GameBrowserView(
            games,
            owner_id=interaction.user.id,
            favorite_ids=await database.get_favorite_ids(interaction.user.id),
        )
        await interaction.response.send_message(
            content=f"📬 Offres découvertes ces {heures} dernières heures : " + " · ".join(summary),
            embed=view.current_embed(),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = await interaction.original_response()

    @app_commands.command(name="favoris", description="Consulte et gère tes jeux favoris")
    @rate_limits.limited("favoris")
    async def favoris(self, interaction: discord.Interaction):
        """Affiche la liste privée des favoris du compte Discord."""
        try:
            games = await database.get_favorites(interaction.user.id)
        except Exception:
            log.exception("Impossible de lire les favoris pour /favoris")
            await interaction.response.send_message(
                "Impossible de lire tes favoris pour le moment. Réessaie plus tard.", ephemeral=True
            )
            return

        if not games:
            await interaction.response.send_message(
                "Tu n'as pas encore de favori. Lance `/free`, puis clique sur ❤️.", ephemeral=True
            )
            return

        view = GameBrowserView(
            games,
            owner_id=interaction.user.id,
            favorite_ids={str(game["id"]) for game in games},
            showing_favorites=True,
        )
        await interaction.response.send_message(
            embed=view.current_embed(), view=view, ephemeral=True
        )
        view.message = await interaction.original_response()

    @app_commands.command(
        name="mes-donnees", description="Supprime les favoris associés à ton compte Discord"
    )
    @rate_limits.limited("mes_donnees")
    async def mes_donnees(self, interaction: discord.Interaction):
        """Permet à un membre d'effacer ses données de favoris."""
        view = ConfirmDeleteDataView(interaction.user.id)
        await interaction.response.send_message(
            "Cette action supprimera tes favoris. Les informations publiques sur les offres "
            "ne sont pas liées à ton compte et seront conservées.",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(
        name="historique", description="Parcourt les dernières offres connues du bot"
    )
    @app_commands.describe(
        plateforme="Ne montrer que cette plateforme",
        type="Ne montrer que ce type d'offre",
    )
    @app_commands.choices(
        plateforme=[
            app_commands.Choice(name=platforms.display_name(key), value=key)
            for key in config.PLATFORM_KEYS
        ],
        type=[
            app_commands.Choice(name=label, value=key)
            for key, label in config.OFFER_TYPE_LABELS.items()
        ],
    )
    @rate_limits.limited("historique")
    async def historique(
        self,
        interaction: discord.Interaction,
        plateforme: str | None = None,
        type: str | None = None,
    ):
        """Historique des offres déjà vues par le bot, utile pour retrouver une ancienne annonce."""
        games = await database.get_recent_giveaways(
            limit=50, platform=platforms.display_name(plateforme) if plateforme else None, offer_type=type
        )
        if not games:
            await interaction.response.send_message(
                "Aucune offre connue pour ces filtres.", ephemeral=True
            )
            return

        favorite_ids = await database.get_favorite_ids(interaction.user.id)
        view = GameBrowserView(games, owner_id=interaction.user.id, favorite_ids=favorite_ids)
        await interaction.response.send_message(embed=view.current_embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @app_commands.command(name="recherche", description="Recherche une offre par titre ou description")
    @app_commands.describe(terme="Mot-clé à chercher")
    @rate_limits.limited("recherche")
    async def recherche(self, interaction: discord.Interaction, terme: str):
        games = await database.search_giveaways(terme, limit=20)
        if not games:
            await interaction.response.send_message(
                f"Aucune offre trouvée pour « {terme} ».", ephemeral=True
            )
            return

        favorite_ids = await database.get_favorite_ids(interaction.user.id)
        view = GameBrowserView(games, owner_id=interaction.user.id, favorite_ids=favorite_ids)
        await interaction.response.send_message(embed=view.current_embed(), view=view, ephemeral=True)
        view.message = await interaction.original_response()

    @app_commands.command(
        name="preferences", description="Personnalise les offres affichées et reçues en alerte"
    )
    @app_commands.describe(
        types="Types d'offres séparés par une virgule (ex : game,dlc)",
        prix_min="Ignore les offres valant moins que ce prix, en euros",
        genres="Genres séparés par une virgule (ex : rpg,action)",
        plateformes="Plateformes séparées par une virgule (ex : steam,epic,gog,ubisoft) ; vide = toutes",
        fuseau="Fuseau horaire IANA (ex : Europe/Paris), vide pour revenir au défaut",
    )
    @rate_limits.limited("preferences")
    async def preferences(
        self,
        interaction: discord.Interaction,
        types: str | None = None,
        prix_min: float | None = None,
        genres: str | None = None,
        plateformes: str | None = None,
        fuseau: str | None = None,
    ):
        current = await database.get_user_preferences(interaction.user.id)
        offer_types = (
            [t.strip() for t in types.split(",") if t.strip() in config.OFFER_TYPE_KEYS]
            if types is not None
            else current["offer_types"]
        )
        new_genres = normalize_genres(genres.split(",")) if genres is not None else current["genres"]
        new_platforms = (
            normalize_platforms(plateformes.split(","))
            if plateformes is not None
            else current["platforms"]
        )

        await database.set_user_preferences(
            interaction.user.id,
            offer_types=offer_types or ["game"],
            min_worth_eur=prix_min if prix_min is not None else current["min_worth_eur"],
            genres=new_genres,
            platforms=new_platforms,
            timezone=fuseau if fuseau is not None else current["timezone"],
        )
        saved = await database.get_user_preferences(interaction.user.id)
        types_label = ", ".join(config.OFFER_TYPE_LABELS.get(t, t) for t in saved["offer_types"]) or "—"
        genres_label = ", ".join(config.GENRE_LABELS.get(g, g) for g in saved["genres"]) or "tous"
        platforms_label = (
            ", ".join(platforms.display_name(p) for p in saved["platforms"]) or "toutes"
        )
        await interaction.response.send_message(
            "✅ Préférences enregistrées.\n"
            f"Types : **{types_label}**\n"
            f"Plateformes : **{platforms_label}**\n"
            f"Prix minimum : **{saved['min_worth_eur'] if saved['min_worth_eur'] is not None else '—'} €**\n"
            f"Genres : **{genres_label}**\n"
            f"Fuseau horaire : **{saved['timezone'] or config.DEFAULT_TIMEZONE} (défaut)**",
            ephemeral=True,
        )

    @app_commands.command(
        name="alertes", description="Active ou désactive tes alertes personnelles par message privé"
    )
    @app_commands.describe(
        type="L'alerte à modifier",
        active="Activer (True) ou désactiver (False) cette alerte",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name=label, value=key)
            for key, label in {**config.USER_NOTIFICATION_EVENT_LABELS}.items()
        ]
    )
    @rate_limits.limited("alertes")
    async def alertes(self, interaction: discord.Interaction, type: str, active: bool):
        await database.set_user_notification(interaction.user.id, type, active)
        label = config.USER_NOTIFICATION_EVENT_LABELS.get(type, type)
        etat = "activée ✅" if active else "désactivée ⛔"
        note = "" if active else "\n(Vérifie aussi que tes messages privés sont ouverts pour ce bot.)"
        await interaction.response.send_message(f"Alerte **{label}** {etat}.{note}", ephemeral=True)

    @app_commands.command(
        name="rappel-salon",
        description="Choisit le salon où envoyer les rappels « se termine aujourd'hui »",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @app_commands.describe(salon="Salon qui recevra les rappels (par défaut : ce salon)")
    @rate_limits.limited("admin")
    @app_commands.checks.has_permissions(administrator=True)
    async def rappel_salon(
        self, interaction: discord.Interaction, salon: discord.TextChannel | None = None
    ):
        channel = salon or interaction.channel
        await database.set_guild_reminder_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"Les rappels « se termine aujourd'hui » seront envoyés dans {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="dev-stats", description="Statistiques internes du bot (réservé au développeur)"
    )
    @rate_limits.limited("admin")
    async def dev_stats(self, interaction: discord.Interaction):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                "Commande réservée au développeur du bot.", ephemeral=True
            )
            return
        stats = await metrics.build_dev_stats(self.bot)
        await interaction.response.send_message(
            f"```\n{metrics.format_dev_stats_text(stats)}\n```", ephemeral=True
        )

    async def saved_access_roles(self, guild: discord.Guild) -> list:
        saved = await database.get_roles_channel_access(guild.id)
        return clean_access_roles(guild, [guild.get_role(role_id) for role_id in saved])

    async def show_config_panel(self, interaction: discord.Interaction):
        guild = interaction.guild
        known = await database.get_platform_channels(guild.id)
        selected = await database.get_guild_platforms(guild.id)
        if selected is None:  # anciennes installations ou configuration via le tableau de bord
            selected = [key for key in config.PLATFORM_KEYS if key in known]
        roles_channel_id = await database.get_roles_channel(guild.id)
        if not known and not selected and not roles_channel_id:
            selected = ["steam", "epic"]
        # Aucun salon DLC enregistré : la mise à jour l'ajoute, comme pour un nouveau
        # serveur. Un salon masqué explicitement reste masqué.
        known_dlc = await database.get_dlc_channel(guild.id, include_inactive=True)
        include_dlc = True if known_dlc is None else await database.is_dlc_active(guild.id)
        view = SetupView(
            self,
            [key for key in config.PLATFORM_KEYS if key in selected],
            await self.saved_access_roles(guild),
            already_configured=bool(known or roles_channel_id),
            include_dlc=include_dlc,
        )
        await interaction.response.send_message(
            view.summary(),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        view.message = await interaction.original_response()

    @app_commands.command(
        name="setup-auto",
        description="Crée les salons privés, les rôles et le salon de choix des rôles",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @rate_limits.limited("admin")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_auto(self, interaction: discord.Interaction):
        await self.show_config_panel(interaction)

    @app_commands.command(name="config", description="Ouvre le panneau de configuration du serveur")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @rate_limits.limited("admin")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_panel(self, interaction: discord.Interaction):
        await self.show_config_panel(interaction)

    @app_commands.command(
        name="acces-salon-roles",
        description="Choisit les rôles qui voient #choisir-ses-roles (toujours en lecture seule)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @rate_limits.limited("admin")
    @app_commands.checks.has_permissions(administrator=True)
    async def acces_salon_roles(self, interaction: discord.Interaction):
        view = AccessView(self, await self.saved_access_roles(interaction.guild))
        await interaction.response.send_message(
            view.summary(),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="reset-all",
        description="Supprime tout ce que le bot a créé et envoyé (salons, rôles, messages)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @rate_limits.limited("admin_heavy")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_all(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"⚠️ Cela supprime **tous** les salons de jeux, {ROLES_CHANNEL_HINT}, la catégorie, "
            "les rôles de plateforme et les anciens messages du bot. C'est **définitif**.\n"
            "Conseil : lance cette commande depuis un autre salon que ceux du bot.",
            view=ConfirmReset(self),
            ephemeral=True,
        )

    @app_commands.command(
        name="reset-jeux", description="Rejoue les annonces (vide l'historique des envois)"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @rate_limits.limited("admin_heavy")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_jeux(self, interaction: discord.Interaction):
        await database.clear_sent(interaction.guild.id)
        await interaction.response.send_message(
            "Historique vidé. `/test-jeux` renverra les jeux récents.", ephemeral=True
        )

    @app_commands.command(name="test-jeux", description="Force une vérification des jeux gratuits")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    @rate_limits.limited("admin_heavy")
    @app_commands.checks.has_permissions(administrator=True)
    async def test_jeux(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self.run_check()
        await interaction.followup.send(f"{count} annonce(s) envoyée(s).", ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(Jeux(bot))

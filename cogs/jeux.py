"""Commandes et surveillance des jeux gratuits.

Ce cog ne contient que la logique Discord : les messages sont construits dans
`utils.embeds`, les permissions dans `utils.permissions`, les réglages dans
`config.py` et l'appel à l'API dans `services.gamerpower`.
"""

import logging
import math
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import database
from services import offer_engine
from utils import branding, metrics, notifications, platforms
from utils.embeds import build_game_message, build_roles_embed, source_label
from utils.offers import filter_offers, normalize_genres, normalize_platforms
from utils.permissions import (
    admin_note,
    category_overwrites,
    clean_access_roles,
    describe_access,
    game_channel_overwrites,
    roles_channel_overwrites,
)

log = logging.getLogger(__name__)

ROLES_CHANNEL_HINT = f"`#{config.ROLES_CHANNEL}`"


# ---------- Boutons de choix des rôles ----------


class RoleButton(discord.ui.Button):
    def __init__(self, key: str):
        super().__init__(
            label=platforms.display_name(key),
            emoji=platforms.emoji(key),
            style=discord.ButtonStyle.secondary,
            custom_id=f"role:{key}",
        )
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        role_id = await database.get_platform_role(interaction.guild.id, self.key)
        role = interaction.guild.get_role(role_id) if role_id else None
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
                msg = (
                    f"Rôle **{role.name}** ajouté. Le salon est maintenant visible "
                    "et tu seras mentionné pour les nouveaux jeux."
                )
        except discord.Forbidden:
            msg = "Je ne peux pas gérer ce rôle. Un admin doit me donner la permission **Gérer les rôles**."
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
            placeholder="1️⃣ Plateformes à suivre",
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
            placeholder="2️⃣ Rôles qui voient le salon (vide = tout le monde)",
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
        self.access_roles = list(access_roles)
        self.access_select = AccessRoleSelect(self.access_roles)
        self.add_item(self.access_select)

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
    """/setup-auto : plateformes à suivre + qui voit le salon des rôles."""

    def __init__(self, cog, platform_keys=(), access_roles=()):
        super().__init__(cog, access_roles)
        self.platforms = list(platform_keys)
        self.add_item(PlatformSelect(self.platforms))

    def summary(self) -> str:
        chosen = ", ".join(platforms.display_name(k) for k in self.platforms) or "—"
        return (
            "**Configuration des jeux gratuits**\n"
            f"1️⃣ Plateformes : **{chosen}**\n"
            f"2️⃣ Qui voit {ROLES_CHANNEL_HINT} : {describe_access(self.access_roles)}\n"
            "🔒 Dans tous les cas le salon est en **lecture seule** : on peut le voir, "
            "le lire et cliquer sur les boutons, mais personne ne peut y écrire.\n"
            "Puis clique sur **Créer / mettre à jour**."
        )

    @discord.ui.button(
        label="Créer / mettre à jour", emoji="✅", style=discord.ButtonStyle.success, row=2
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.platforms:
            await interaction.response.send_message(
                "Choisis d'abord au moins une plateforme dans le menu 1️⃣.", ephemeral=True
            )
            return
        await interaction.response.edit_message(content="⏳ Création en cours…", view=None)
        report = await self.cog.apply_setup(interaction.guild, self.platforms, self.access_roles)
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
        embed.set_footer(text=f"Source : {label} • {self.page + 1}/{self.page_count}")
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
        self.bot.add_view(RolesView(config.PLATFORM_KEYS))
        self.roles_channels = await database.get_all_roles_channels()

    async def cog_unload(self):
        self.check_games.cancel()

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
            await role.edit(
                name=wanted,
                colour=platforms.role_colour(key),
                mentionable=True,
                reason="Mise à jour du rôle jeux gratuits",
            )
        await database.set_platform_role(guild.id, key, role.id)
        return role

    async def ensure_platform_channel(
        self,
        guild: discord.Guild,
        category: discord.CategoryChannel,
        key: str,
        role: discord.Role,
        known_id=None,
    ) -> discord.TextChannel:
        """Salon de la plateforme : invisible sans le rôle, lecture seule avec."""
        overwrites = game_channel_overwrites(guild, role)
        name = platforms.channel_name(key)
        channel = guild.get_channel(known_id) if known_id else None
        if channel is None:
            channel = discord.utils.get(category.text_channels, name=name)
        if channel is None:
            channel = await category.create_text_channel(
                name,
                topic=f"Jeux gratuits : {platforms.display_name(key)}",
                overwrites=overwrites,
            )
        else:
            await channel.edit(overwrites=overwrites)
        await database.set_platform_channel(guild.id, key, channel.id)
        return channel

    async def ensure_roles_channel(
        self, guild: discord.Guild, category: discord.CategoryChannel, access_roles: list
    ) -> discord.TextChannel:
        """Crée ou répare le salon des rôles : lecture seule, visible par les rôles choisis."""
        overwrites = roles_channel_overwrites(guild, access_roles)

        channel = None
        channel_id = await database.get_roles_channel(guild.id)
        if channel_id:
            channel = guild.get_channel(channel_id)
        if channel is None:
            channel = discord.utils.get(category.text_channels, name=config.ROLES_CHANNEL)

        if channel is None:
            channel = await category.create_text_channel(
                config.ROLES_CHANNEL, topic=config.ROLES_TOPIC, overwrites=overwrites
            )
        else:
            await channel.edit(overwrites=overwrites, topic=config.ROLES_TOPIC)

        await database.set_roles_channel(guild.id, channel.id)
        await database.set_roles_channel_access(guild.id, [r.id for r in access_roles])
        self.roles_channels[guild.id] = channel.id
        return channel

    async def post_roles_message(self, channel: discord.TextChannel, keys: list):
        async for old in channel.history(limit=20):
            if old.author.id == channel.guild.me.id:
                await old.delete()
        await channel.send(embed=build_roles_embed(), view=RolesView(keys))

    async def apply_setup(self, guild: discord.Guild, platform_keys: list, access_roles: list) -> str:
        """Crée/met à jour la catégorie, les rôles, les salons et le panneau des rôles."""
        access_roles = clean_access_roles(guild, access_roles)
        created = []
        try:
            category = discord.utils.get(guild.categories, name=config.CATEGORY_NAME)
            if category is None:
                category = await guild.create_category(
                    config.CATEGORY_NAME, overwrites=category_overwrites(guild)
                )

            known_channels = await database.get_platform_channels(guild.id)
            for key in platform_keys:
                role = await self.ensure_platform_role(guild, key)
                channel = await self.ensure_platform_channel(
                    guild, category, key, role, known_channels.get(key)
                )
                created.append(f"{channel.mention} → {role.mention}")

            roles_channel = await self.ensure_roles_channel(guild, category, access_roles)
            await roles_channel.move(beginning=True, category=category)

            saved = await database.get_guild_platform_roles(guild.id)
            await self.post_roles_message(roles_channel, [k for k in config.PLATFORM_KEYS if k in saved])

        except discord.Forbidden:
            return (
                "Il me manque une permission. Donne-moi **Gérer les salons**, "
                "**Gérer les rôles** et **Gérer les messages**, puis relance `/setup-auto`."
            )

        return (
            "Prêt !\n"
            + "\n".join(created)
            + f"\nChoix des rôles : {roles_channel.mention} "
            + f"(lecture seule, visible par : {describe_access(access_roles)})"
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

        # salons restants de la catégorie, puis la catégorie si elle est vide
        category = discord.utils.get(guild.categories, name=config.CATEGORY_NAME)
        if category:
            for channel in list(category.text_channels):
                if channel.id in deleted:
                    continue
                cree_par_le_bot = channel.name == config.ROLES_CHANNEL or channel.name.startswith(
                    config.GAME_CHANNEL_PREFIX
                )
                if cree_par_le_bot:
                    await delete_channel(channel)
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

    async def run_check(self) -> int:
        """Envoie les jeux gratuits pas encore annoncés. Retourne le nombre d'annonces."""
        response = await offer_engine.fetch_offers()
        games = [game for game in response if isinstance(game, dict) and game.get("id") is not None]
        await database.save_giveaways(games)
        await database.set_bot_state("last_check_at", datetime.now(timezone.utc).isoformat())
        routes = await database.get_routes()
        roles = await database.get_all_platform_roles()
        mentions = discord.AllowedMentions(roles=True)
        invite_url = branding.build_invite_url(self.bot.user.id) if self.bot.user else None
        new_games = []
        sent = 0
        for game in games[: config.MAX_GAMES]:
            item_id = str(game.get("id"))
            embed, view = build_game_message(game, invite_url=invite_url)
            announced_anywhere = False
            for guild_id, route, channel_id, _ in routes:
                if not platforms.matches(game, [route]):
                    continue
                sent_key = f"{item_id}:{route}"
                if await database.is_sent(guild_id, sent_key):
                    continue
                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    continue
                role_id = roles.get((guild_id, route))
                content = f"<@&{role_id}> nouveau jeu gratuit !" if role_id else None
                try:
                    await channel.send(
                        content=content,
                        embed=embed,
                        view=view,
                        allowed_mentions=mentions,
                    )
                    await database.mark_sent(guild_id, sent_key)
                    sent += 1
                    announced_anywhere = True
                except discord.HTTPException as e:
                    log.warning("Envoi impossible sur le serveur %s : %s", guild_id, e)
            if announced_anywhere:
                new_games.append(game)

        try:
            await notifications.notify_new_offers(self.bot, new_games)
            await notifications.notify_ending_soon(self.bot, games)
            await notifications.send_guild_reminders(self.bot, games)
        except Exception:
            log.exception("Erreur pendant l'envoi des alertes personnelles")
        return sent

    @tasks.loop(hours=1)
    async def check_games(self):
        try:
            await self.run_check()
        except Exception:
            log.exception("Erreur pendant la vérification des jeux")

    @check_games.before_loop
    async def before_check_games(self):
        await self.bot.wait_until_ready()

    # ----- commandes -----

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
    @app_commands.checks.cooldown(1, 15.0, key=lambda interaction: interaction.user.id)
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
            response = await offer_engine.fetch_offers()
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
        if not games:
            await interaction.followup.send(
                "Aucun jeu gratuit trouvé pour le moment, ou la source est temporairement indisponible.",
                ephemeral=True,
            )
            return

        view = GameBrowserView(
            games,
            owner_id=interaction.user.id,
            favorite_ids=await database.get_favorite_ids(interaction.user.id),
        )
        view.message = await interaction.followup.send(
            embed=view.current_embed(), view=view, ephemeral=True, wait=True
        )

    @free.error
    async def free_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            retry_after = max(1, math.ceil(error.retry_after))
            message = f"Attends encore {retry_after} seconde(s) avant de relancer `/free`."
        else:
            log.error("Erreur pendant la commande /free : %s", error)
            message = "La commande `/free` a rencontré une erreur. Réessaie un peu plus tard."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="favoris", description="Consulte et gère tes jeux favoris")
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
        view = SetupView(
            self,
            [key for key in config.PLATFORM_KEYS if key in known],
            await self.saved_access_roles(guild),
        )
        await interaction.response.send_message(
            view.summary(),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="setup-auto",
        description="Crée les salons privés, les rôles et le salon de choix des rôles",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_auto(self, interaction: discord.Interaction):
        await self.show_config_panel(interaction)

    @app_commands.command(name="config", description="Ouvre le panneau de configuration du serveur")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def config_panel(self, interaction: discord.Interaction):
        await self.show_config_panel(interaction)

    @app_commands.command(
        name="acces-salon-roles",
        description="Choisit les rôles qui voient #choisir-ses-roles (toujours en lecture seule)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
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
    async def reset_jeux(self, interaction: discord.Interaction):
        await database.clear_sent(interaction.guild.id)
        await interaction.response.send_message(
            "Historique vidé. `/test-jeux` renverra les jeux récents.", ephemeral=True
        )

    @app_commands.command(name="test-jeux", description="Force une vérification des jeux gratuits")
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def test_jeux(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self.run_check()
        await interaction.followup.send(f"{count} annonce(s) envoyée(s).", ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(Jeux(bot))

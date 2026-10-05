import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import database
from services import gamerpower

log = logging.getLogger(__name__)

# clé -> (nom affiché, mots-clés cherchés dans le champ "platforms" de l'API)
PLATFORMS = {
    "steam": ("Steam", ["steam"]),
    "epic": ("Epic Games Store", ["epic games"]),
    "gog": ("GOG", ["gog"]),
    "ubisoft": ("Ubisoft", ["ubisoft"]),
}

# clé -> (emoji, couleur du rôle et des annonces)
STYLE = {
    "steam": ("🔵", 0x66C0F4),
    "epic": ("⚪", 0xD9D9D9),
    "gog": ("🟣", 0xA855F7),
    "ubisoft": ("🔷", 0x0070FF),
}
DEFAULT_STYLE = ("🎁", 0xF1C40F)

AUTO_KEYS = list(PLATFORMS)

MAX_GAMES = 10  # nombre de jeux récents examinés à chaque vérification
CATEGORY_NAME = "🎮 Jeux gratuits"
ROLES_CHANNEL = "choisir-ses-roles"
ROLES_TOPIC = "Clique sur un bouton pour recevoir les alertes • salon en lecture seule"
ROLES_CHANNEL_HINT = f"`#{ROLES_CHANNEL}`"
MAX_ACCESS_ROLES = 10  # rôles maximum autorisés à voir le salon des rôles


def role_name(key: str) -> str:
    return f"{STYLE.get(key, DEFAULT_STYLE)[0]} {PLATFORMS[key][0]}"


def role_color(key: str) -> discord.Colour:
    return discord.Colour(STYLE.get(key, DEFAULT_STYLE)[1])


def matches(game: dict, selected: list) -> bool:
    text = (game.get("platforms") or "").lower()
    for key in selected:
        if key in PLATFORMS and any(kw in text for kw in PLATFORMS[key][1]):
            return True
    return False


def detect_platform(game: dict):
    for key in AUTO_KEYS:
        if matches(game, [key]):
            return key
    return None


# ---------- Jolis messages ----------


def format_end_date(raw: str) -> str:
    """'2026-10-05 23:59:00' -> compte à rebours + date complète (heure locale de chacun)."""
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        ts = int(dt.timestamp())
        return f"<t:{ts}:R>\n<t:{ts}:f>"
    except (ValueError, TypeError):
        return "Pas de date limite connue"


def format_price(worth) -> str:
    if not worth or str(worth).strip().upper() == "N/A":
        return "**GRATUIT**"
    return f"~~{worth}~~ ➜ **GRATUIT**"


def clean_description(text: str, limit: int = 220) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def build_message(game: dict):
    key = detect_platform(game)
    emoji, color = STYLE.get(key, DEFAULT_STYLE)
    title = game.get("title", "Jeu gratuit").replace(" Giveaway", "")
    url = game.get("open_giveaway_url") or game.get("gamerpower_url")

    embed = discord.Embed(
        title=f"{emoji} {title}",
        url=url,
        description=clean_description(game.get("description")),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name="🎁 NOUVEAU JEU GRATUIT")
    embed.add_field(name="💰 Prix", value=format_price(game.get("worth")), inline=True)
    embed.add_field(name="⏳ Fin de l'offre", value=format_end_date(game.get("end_date")), inline=True)
    embed.add_field(name="🖥️ Plateformes", value=game.get("platforms") or "N/A", inline=False)
    if game.get("thumbnail"):
        embed.set_image(url=game["thumbnail"])
    embed.set_footer(text="Source : GamerPower")

    view = discord.ui.View()
    if url:
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="Récupérer le jeu",
                emoji="🎁",
                url=url,
            )
        )
    return embed, view


# ---------- Permissions des salons ----------

# Tout ce qu'on retire dans un salon en lecture seule : écrire, réagir, ouvrir un fil,
# lancer un sondage, envoyer un vocal, utiliser une commande... bref, regarder et c'est tout.
READONLY_DENY = (
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
    "manage_threads",
    "add_reactions",
    "send_tts_messages",
    "attach_files",
    "embed_links",
    "mention_everyone",
    "manage_messages",
    "use_application_commands",
    "send_voice_messages",
    "create_polls",
    "send_polls",
)

BOT_ALLOW = (
    "view_channel",
    "read_message_history",
    "send_messages",
    "embed_links",
    "attach_files",
    "manage_messages",  # pour nettoyer le salon des rôles
)


def _overwrite(**flags) -> discord.PermissionOverwrite:
    """PermissionOverwrite en ignorant les permissions absentes de cette version de discord.py."""
    known = discord.Permissions.VALID_FLAGS
    return discord.PermissionOverwrite(**{k: v for k, v in flags.items() if k in known})


def _bot_can(guild: discord.Guild, name: str) -> bool:
    """Discord refuse qu'on autorise/interdise une permission que le bot n'a pas lui-même."""
    return bool(getattr(guild.me.guild_permissions, name, False))


def bot_overwrite(guild: discord.Guild) -> discord.PermissionOverwrite:
    return _overwrite(**{name: True for name in BOT_ALLOW if _bot_can(guild, name)})


def readonly_overwrite(guild: discord.Guild) -> discord.PermissionOverwrite:
    """Voir le salon, le lire, cliquer sur les boutons. Rien d'autre."""
    flags = {name: False for name in READONLY_DENY if _bot_can(guild, name)}
    flags["view_channel"] = True
    flags["read_message_history"] = True
    return _overwrite(**flags)


def hidden_overwrite(guild: discord.Guild) -> discord.PermissionOverwrite:
    """Salon masqué, et verrouillé en écriture au cas où la vue serait rendue ailleurs."""
    flags = {name: False for name in READONLY_DENY if _bot_can(guild, name)}
    flags["view_channel"] = False
    return _overwrite(**flags)


def category_overwrites(guild: discord.Guild) -> dict:
    """Catégorie verrouillée en écriture (sans toucher à la visibilité)."""
    flags = {name: False for name in READONLY_DENY if _bot_can(guild, name)}
    return {guild.default_role: _overwrite(**flags), guild.me: bot_overwrite(guild)}


def game_channel_overwrites(guild: discord.Guild, role: discord.Role) -> dict:
    return {
        guild.default_role: hidden_overwrite(guild),
        role: readonly_overwrite(guild),
        guild.me: bot_overwrite(guild),
    }


def clean_access_roles(guild: discord.Guild, roles) -> list:
    """Garde les rôles réellement utilisables ; @everyone revient à « tout le monde »."""
    cleaned = []
    for role in roles or []:
        if role is None or role.is_default() or role in cleaned:
            continue
        cleaned.append(role)
    return cleaned[:MAX_ACCESS_ROLES]


def roles_channel_overwrites(guild: discord.Guild, access_roles=None) -> dict:
    """Salon des rôles : personne ne peut écrire, jamais.

    - sans rôle précisé : visible par tout le monde, en lecture seule ;
    - avec des rôles : visible uniquement par ces rôles, toujours en lecture seule.
    """
    access_roles = clean_access_roles(guild, access_roles)
    overwrites = {guild.me: bot_overwrite(guild)}
    if access_roles:
        overwrites[guild.default_role] = hidden_overwrite(guild)
        for role in access_roles:
            overwrites[role] = readonly_overwrite(guild)
    else:
        overwrites[guild.default_role] = readonly_overwrite(guild)
    return overwrites


def describe_access(access_roles) -> str:
    if access_roles:
        return ", ".join(role.mention for role in access_roles)
    return "tout le monde (`@everyone`)"


# ---------- Boutons de choix des rôles ----------


class RoleButton(discord.ui.Button):
    def __init__(self, key: str):
        super().__init__(
            label=PLATFORMS[key][0],
            emoji=STYLE.get(key, DEFAULT_STYLE)[0],
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
                msg = f"Rôle **{role.name}** ajouté. Le salon est maintenant visible et tu seras mentionné pour les nouveaux jeux."
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
                label=PLATFORMS[key][0],
                value=key,
                emoji=STYLE.get(key, DEFAULT_STYLE)[0],
                default=key in selected,
            )
            for key in AUTO_KEYS
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
            max_values=MAX_ACCESS_ROLES,
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
    def __init__(self, cog, platforms=(), access_roles=()):
        super().__init__(cog, access_roles)
        self.platforms = list(platforms)
        self.add_item(PlatformSelect(self.platforms))

    def summary(self) -> str:
        plats = ", ".join(PLATFORMS[k][0] for k in self.platforms) if self.platforms else "—"
        return (
            "**Configuration des jeux gratuits**\n"
            f"1️⃣ Plateformes : **{plats}**\n"
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


# ---------- Le cog ----------


class Jeux(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.roles_channels = {}  # {serveur: salon des rôles} pour le nettoyage des messages
        self.check_games.start()

    async def cog_load(self):
        self.bot.add_view(RolesView(AUTO_KEYS))
        self.roles_channels = await database.get_all_roles_channels()

    async def cog_unload(self):
        self.check_games.cancel()

    # ----- création / mise à jour -----

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
            channel = discord.utils.get(category.text_channels, name=ROLES_CHANNEL)

        if channel is None:
            channel = await category.create_text_channel(
                ROLES_CHANNEL, topic=ROLES_TOPIC, overwrites=overwrites
            )
        else:
            await channel.edit(overwrites=overwrites, topic=ROLES_TOPIC)

        await database.set_roles_channel(guild.id, channel.id)
        await database.set_roles_channel_access(guild.id, [r.id for r in access_roles])
        self.roles_channels[guild.id] = channel.id
        return channel

    async def post_roles_message(self, channel: discord.TextChannel, keys: list):
        async for old in channel.history(limit=20):
            if old.author.id == channel.guild.me.id:
                await old.delete()
        embed = discord.Embed(
            title="🎮 Choisis tes alertes jeux gratuits",
            description=(
                "Clique sur un bouton pour **recevoir** le rôle d'une plateforme "
                "et débloquer son salon. Reclique pour le **retirer**.\n\n"
                "Tu seras mentionné quand un jeu gratuit sort sur cette plateforme."
            ),
            color=discord.Color.gold(),
        )
        embed.set_footer(text="Salon en lecture seule : seuls les boutons fonctionnent ici.")
        await channel.send(embed=embed, view=RolesView(keys))

    async def apply_setup(self, guild: discord.Guild, platforms: list, access_roles: list) -> str:
        access_roles = clean_access_roles(guild, access_roles)
        created = []
        try:
            category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
            if category is None:
                category = await guild.create_category(
                    CATEGORY_NAME, overwrites=category_overwrites(guild)
                )

            saved_channels = await database.get_platform_channels(guild.id)
            for key in platforms:
                new_name = role_name(key)
                color = role_color(key)

                # 1) le rôle (réutilisé et recoloré s'il existe déjà)
                role = None
                role_id = await database.get_platform_role(guild.id, key)
                if role_id:
                    role = guild.get_role(role_id)
                if role is None:
                    role = discord.utils.get(guild.roles, name=new_name) or discord.utils.get(
                        guild.roles, name=f"Jeux {PLATFORMS[key][0]}"
                    )
                if role is None:
                    role = await guild.create_role(
                        name=new_name,
                        colour=color,
                        mentionable=True,
                        reason="Rôle d'alerte jeux gratuits",
                    )
                else:
                    await role.edit(
                        name=new_name,
                        colour=color,
                        mentionable=True,
                        reason="Mise à jour du rôle jeux gratuits",
                    )
                await database.set_platform_role(guild.id, key, role.id)

                # 2) le salon : caché sans le rôle, lecture seule
                name = f"jeux-{key}"
                overwrites = game_channel_overwrites(guild, role)
                channel = None
                channel_id = saved_channels.get(key)
                if channel_id:
                    channel = guild.get_channel(channel_id)
                if channel is None:
                    channel = discord.utils.get(category.text_channels, name=name)
                if channel is None:
                    channel = await category.create_text_channel(
                        name,
                        topic=f"Jeux gratuits : {PLATFORMS[key][0]}",
                        overwrites=overwrites,
                    )
                else:
                    await channel.edit(overwrites=overwrites)
                await database.set_platform_channel(guild.id, key, channel.id)
                created.append(f"{channel.mention} → {role.mention}")

            # 3) le salon de choix des rôles : lecture seule, en premier
            roles_channel = await self.ensure_roles_channel(guild, category, access_roles)
            await roles_channel.move(beginning=True, category=category)

            saved = await database.get_guild_platform_roles(guild.id)
            await self.post_roles_message(roles_channel, [k for k in AUTO_KEYS if k in saved])

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
            + admin_note(roles_channel.guild)
        )

    async def apply_access(self, guild: discord.Guild, access_roles: list) -> str:
        access_roles = clean_access_roles(guild, access_roles)
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        channel_id = await database.get_roles_channel(guild.id)
        channel = guild.get_channel(channel_id) if channel_id else None
        if channel is None and category is not None:
            channel = discord.utils.get(category.text_channels, name=ROLES_CHANNEL)
        if channel is None:
            return "Je ne trouve pas le salon des rôles. Lance d'abord `/setup-auto`."

        try:
            await channel.edit(
                overwrites=roles_channel_overwrites(guild, access_roles), topic=ROLES_TOPIC
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
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if category:
            for channel in list(category.text_channels):
                if channel.id in deleted:
                    continue
                if channel.name == ROLES_CHANNEL or channel.name.startswith("jeux-"):
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
                getattr(channel, "name", None) != ROLES_CHANNEL
                or category is None
                or category.name != CATEGORY_NAME
            ):
                return
        try:
            await message.delete()
        except discord.Forbidden:
            log.warning(
                "Impossible de supprimer un message dans #%s : il me faut la permission Gérer les messages.",
                ROLES_CHANNEL,
            )
        except discord.HTTPException:
            pass

    async def run_check(self) -> int:
        games = await gamerpower.fetch_giveaways()
        routes = await database.get_routes()
        roles = await database.get_all_platform_roles()
        mentions = discord.AllowedMentions(roles=True)
        sent = 0
        for game in games[:MAX_GAMES]:
            item_id = str(game.get("id"))
            embed, view = build_message(game)
            for guild_id, route, channel_id, _ in routes:
                if not matches(game, [route]):
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
                except discord.HTTPException as e:
                    log.warning("Envoi impossible sur le serveur %s : %s", guild_id, e)
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

    @app_commands.command(
        name="setup-auto",
        description="Crée les salons privés, les rôles et le salon de choix des rôles",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_auto(self, interaction: discord.Interaction):
        guild = interaction.guild
        platforms = [k for k in AUTO_KEYS if k in await database.get_platform_channels(guild.id)]
        saved_access = await database.get_roles_channel_access(guild.id)
        access_roles = clean_access_roles(guild, [guild.get_role(r) for r in saved_access])
        view = SetupView(self, platforms, access_roles)
        await interaction.response.send_message(
            view.summary(),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(
        name="acces-salon-roles",
        description="Choisit les rôles qui voient #choisir-ses-roles (toujours en lecture seule)",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def acces_salon_roles(self, interaction: discord.Interaction):
        guild = interaction.guild
        saved_access = await database.get_roles_channel_access(guild.id)
        access_roles = clean_access_roles(guild, [guild.get_role(r) for r in saved_access])
        view = AccessView(self, access_roles)
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
            "⚠️ Cela supprime **tous** les salons de jeux, `#choisir-ses-roles`, la catégorie, "
            "les rôles de plateforme et les anciens messages du bot. C'est **définitif**.\n"
            "Conseil : lance cette commande depuis un autre salon que ceux du bot.",
            view=ConfirmReset(self),
            ephemeral=True,
        )

    @app_commands.command(name="reset-jeux", description="Rejoue les annonces (vide l'historique des envois)")
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


# ---------- /reset-all ----------


class ConfirmReset(discord.ui.View):
    def __init__(self, cog: Jeux):
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


def admin_note(guild: discord.Guild) -> str:
    """Les permissions de salon ne bloquent pas les admins : on prévient que le bot nettoie."""
    if _bot_can(guild, "manage_messages"):
        return "\nℹ️ Les admins passent outre les permissions Discord : leurs messages y sont supprimés automatiquement."
    return (
        "\n⚠️ Donne-moi la permission **Gérer les messages** : sans elle je ne peux pas effacer "
        "les messages des administrateurs, que Discord laisse toujours écrire partout."
    )


async def setup(bot: commands.Bot):
    await bot.add_cog(Jeux(bot))

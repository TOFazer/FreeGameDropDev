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


def bot_overwrite() -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        read_message_history=True,
    )


def readonly_overwrite(view: bool) -> discord.PermissionOverwrite:
    """Lecture seule : ni écrire, ni réagir, ni créer de fil."""
    return discord.PermissionOverwrite(
        view_channel=view,
        read_message_history=True if view else None,
        send_messages=False,
        add_reactions=False,
        create_public_threads=False,
        create_private_threads=False,
        send_messages_in_threads=False,
        use_application_commands=False,
    )


def game_channel_overwrites(guild: discord.Guild, role: discord.Role) -> dict:
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        role: readonly_overwrite(view=True),
        guild.me: bot_overwrite(),
    }


def roles_channel_overwrites(guild: discord.Guild) -> dict:
    return {
        guild.default_role: readonly_overwrite(view=True),
        guild.me: bot_overwrite(),
    }


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


# ---------- /setup-auto ----------


class CreateChannelsSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=PLATFORMS[key][0], value=key, emoji=STYLE.get(key, DEFAULT_STYLE)[0]
            )
            for key in AUTO_KEYS
        ]
        super().__init__(
            placeholder="Quelles plateformes ?",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        try:
            category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
            if category is None:
                category = await guild.create_category(
                    CATEGORY_NAME,
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(send_messages=False),
                        guild.me: bot_overwrite(),
                    },
                )

            created = []
            for key in self.values:
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

            # 3) le salon de choix des rôles : visible par tous, en premier
            ro = roles_channel_overwrites(guild)
            roles_channel = discord.utils.get(category.text_channels, name=ROLES_CHANNEL)
            if roles_channel is None:
                roles_channel = await category.create_text_channel(
                    ROLES_CHANNEL,
                    topic="Clique sur un bouton pour recevoir les alertes",
                    overwrites=ro,
                )
            else:
                await roles_channel.edit(overwrites=ro)
            await roles_channel.move(beginning=True, category=category)

            saved = await database.get_guild_platform_roles(guild.id)
            keys = [k for k in AUTO_KEYS if k in saved]

            async for old in roles_channel.history(limit=20):
                if old.author.id == guild.me.id:
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
            await roles_channel.send(embed=embed, view=RolesView(keys))

        except discord.Forbidden:
            await interaction.edit_original_response(
                content=(
                    "Il me manque une permission. Donne-moi **Gérer les salons** "
                    "et **Gérer les rôles**, puis relance `/setup-auto`."
                ),
                view=None,
            )
            return

        await interaction.edit_original_response(
            content="Prêt !\n" + "\n".join(created) + f"\nChoix des rôles : {roles_channel.mention}",
            view=None,
        )


# ---------- /reset-all ----------


async def wipe_guild(guild: discord.Guild) -> str:
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

    report = (
        f"Nettoyage terminé : **{n_channels}** salon(s)/catégorie, "
        f"**{n_roles}** rôle(s) et **{n_msgs}** message(s) supprimés.\n"
        "Relance `/setup-auto` pour tout recréer."
    )
    if problems:
        report += "\nPermission(s) manquante(s) : " + ", ".join(sorted(problems)) + "."
    return report


class ConfirmReset(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Tout supprimer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Nettoyage en cours...", view=None)
        report = await wipe_guild(interaction.guild)
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
        self.check_games.start()

    async def cog_load(self):
        self.bot.add_view(RolesView(AUTO_KEYS))

    async def cog_unload(self):
        self.check_games.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Le salon de choix des rôles est strictement réservé aux boutons :
        tout message qui n'est pas celui du bot est supprimé (même celui d'un admin)."""
        if message.guild is None or message.author.id == self.bot.user.id:
            return
        channel = message.channel
        category = getattr(channel, "category", None)
        if channel.name != ROLES_CHANNEL or category is None or category.name != CATEGORY_NAME:
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

    @app_commands.command(
        name="setup-auto",
        description="Crée les salons privés, les rôles et le salon de choix des rôles",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def setup_auto(self, interaction: discord.Interaction):
        view = discord.ui.View(timeout=120)
        view.add_item(CreateChannelsSelect())
        await interaction.response.send_message(
            "Choisis les plateformes (un salon privé et un rôle seront créés ou mis à jour pour chacune) :",
            view=view,
            ephemeral=True,
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
            view=ConfirmReset(),
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


async def setup(bot: commands.Bot):
    await bot.add_cog(Jeux(bot))
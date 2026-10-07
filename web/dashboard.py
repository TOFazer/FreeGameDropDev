"""Logique du tableau de bord web : pages HTML et échanges OAuth2 Discord.

Ce module ne connaît pas aiohttp.web : il construit des chaînes de caractères
et fait des appels réseau isolés dans de petites fonctions, pour rester
testable sans serveur HTTP réel. `web.dashboard_server` s'occupe du routage.

Sécurité :
- l'OAuth demande uniquement `identify guilds` : jamais l'accès aux messages ;
- le jeton OAuth du membre n'est JAMAIS stocké — seule la liste (id, nom,
  icône) des serveurs qu'il peut gérer est photographiée à la connexion ;
- chaque formulaire embarque un jeton anti-CSRF propre à la session ;
- tout contenu dynamique passe par `html.escape`.
"""

from __future__ import annotations

import html
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import aiohttp

import config
import database
from utils import branding, design, environment
from utils import platforms as platform_utils
from utils.offers import parse_end_datetime

SESSION_COOKIE = "fgd_session"
SESSION_DURATION_HOURS = 24 * 7

# Partagé avec les liens /info et les annonces pour éviter des permissions contradictoires.
INVITE_PERMISSIONS = branding.INVITE_PERMISSIONS

# Bits OAuth : un membre peut configurer un serveur s'il en est propriétaire,
# administrateur ou s'il possède « Gérer le serveur ».
_PERM_ADMINISTRATOR = 0x8
_PERM_MANAGE_GUILD = 0x20

# Permissions indispensables à la configuration et aux annonces. Lire l'historique
# et gérer les messages peuvent améliorer la modération, mais ne sont pas obligatoires.
REQUIRED_BOT_PERMISSIONS = (
    ("view_channel", "Voir les salons", "accéder aux salons d'annonces"),
    ("send_messages", "Envoyer des messages", "poster les annonces de jeux gratuits"),
    ("embed_links", "Intégrer des liens", "afficher les offres avec images et boutons"),
    ("manage_channels", "Gérer les salons", "créer et réparer la catégorie et les salons"),
    ("manage_roles", "Gérer les rôles", "créer et attribuer les rôles de plateformes"),
)


# ---------- OAuth2 Discord ----------


def build_authorize_url(state: str) -> str:
    """URL vers laquelle rediriger un visiteur pour se connecter avec Discord."""
    params = {
        "client_id": config.DISCORD_CLIENT_ID,
        "redirect_uri": config.DISCORD_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
    }
    return f"{config.DISCORD_API_BASE_URL}/oauth2/authorize?{urlencode(params)}"


def build_invite_url(guild_id: int | str | None = None) -> str:
    """Lien « Ajouter à Discord », éventuellement pré-ciblé sur un serveur."""
    params = {
        "client_id": config.DISCORD_CLIENT_ID,
        "permissions": INVITE_PERMISSIONS,
        "scope": "bot applications.commands",
    }
    if guild_id:
        params["guild_id"] = str(guild_id)
    return f"https://discord.com/oauth2/authorize?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict | None:
    """Échange le code OAuth2 contre un jeton d'accès Discord."""
    data = {
        "client_id": config.DISCORD_CLIENT_ID,
        "client_secret": config.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.DISCORD_OAUTH_REDIRECT_URI,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{config.DISCORD_API_BASE_URL}/oauth2/token", data=data) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


async def fetch_discord_user(access_token: str) -> dict | None:
    """Identité Discord minimale (id, pseudo, avatar) associée à un jeton d'accès."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{config.DISCORD_API_BASE_URL}/users/@me", headers=headers) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


async def fetch_user_guilds(access_token: str) -> list[dict] | None:
    """Serveurs du membre (scope `guilds`) : id, nom, icône et permissions."""
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{config.DISCORD_API_BASE_URL}/users/@me/guilds", headers=headers
        ) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


def filter_manageable_guilds(guilds: list[dict] | None) -> list[dict]:
    """Ne garde que les serveurs que le membre peut réellement administrer.

    Un membre ne peut PAS configurer tous les serveurs où il se trouve : il faut
    être propriétaire, administrateur ou avoir « Gérer le serveur ».
    """
    manageable = []
    for guild in guilds or []:
        try:
            permissions = int(guild.get("permissions") or 0)
        except (TypeError, ValueError):
            permissions = 0
        if (
            guild.get("owner")
            or permissions & _PERM_ADMINISTRATOR
            or permissions & _PERM_MANAGE_GUILD
        ):
            manageable.append(
                {
                    "id": str(guild.get("id", "")),
                    "name": str(guild.get("name", "")),
                    "icon": guild.get("icon") or "",
                }
            )
    return manageable


# ---------- Sessions ----------


def new_state_token() -> str:
    return secrets.token_urlsafe(24)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(hours=SESSION_DURATION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")


async def start_login(bot) -> tuple[str, str]:
    """Retourne (state, url_de_connexion) ; `state` doit être stocké dans un cookie court."""
    state = new_state_token()
    return state, build_authorize_url(state)


async def complete_login(code: str) -> dict | None:
    """Échange le code contre un jeton puis crée une session. Retourne la session créée.

    Le jeton OAuth sert uniquement ici, le temps de lire l'identité et la liste
    des serveurs gérables ; il n'est jamais écrit en base.
    """
    token_payload = await exchange_code_for_token(code)
    if not token_payload or "access_token" not in token_payload:
        return None

    access_token = token_payload["access_token"]
    user = await fetch_discord_user(access_token)
    if not user or "id" not in user:
        return None

    manageable = filter_manageable_guilds(await fetch_user_guilds(access_token))

    session_id = new_session_id()
    csrf_token = new_csrf_token()
    await database.create_dashboard_session(
        session_id,
        int(user["id"]),
        user.get("username", ""),
        user.get("avatar") or "",
        session_expiry(),
        csrf_token=csrf_token,
        guilds_json=json.dumps(manageable),
    )
    return {"session_id": session_id, "user": user, "csrf_token": csrf_token}


async def current_session(session_id: str | None) -> dict | None:
    if not session_id:
        return None
    session = await database.get_dashboard_session(session_id)
    if session is None:
        return None
    try:
        session["guilds"] = json.loads(session.get("guilds_json") or "[]")
    except (TypeError, ValueError):
        session["guilds"] = []
    return session


def session_guild(session: dict | None, guild_id: str) -> dict | None:
    """Le serveur demandé, uniquement s'il fait partie de ceux que le membre peut gérer."""
    if not session:
        return None
    for guild in session.get("guilds") or []:
        if str(guild.get("id")) == str(guild_id):
            return guild
    return None


def guild_icon_url(guild: dict) -> str:
    if guild.get("icon"):
        return f"https://cdn.discordapp.com/icons/{guild['id']}/{guild['icon']}.png?size=64"
    return ""


# ---------- Habillage HTML ----------


def _environment_banner() -> str:
    """Bandeau DEV / maintenance, invisible en production nominale.

    Un tableau de bord de développement ne doit jamais ressembler à celui de la
    production : le titre et le bandeau le disent avant même de lire la page.
    """
    if environment.is_development(config.ENVIRONMENT):
        parts = [
            f"{environment.emoji_of()} <strong>{html.escape(environment.product_name())}</strong>"
            " — environnement de développement, base et application Discord dédiées."
        ]
    else:
        parts = []
    if config.MAINTENANCE_MODE:
        parts.append("🔧 Maintenance : les annonces automatiques sont suspendues.")
    if not parts:
        return ""
    return f'<div class="notice env-banner">{" ".join(parts)}</div>'


def _page(title: str, body: str, user: dict | None = None, active: str = "") -> str:
    page_title = environment.page_title(title)
    site_name = environment.product_name()
    badge = ""
    footer_note = ""
    if environment.is_development(config.ENVIRONMENT):
        tag = environment.TAG[environment.DEVELOPMENT]
        badge = f'<span class="badge new env-tag">{environment.emoji_of()} {tag}</span>'
        footer_note = f" · {environment.emoji_of()} {environment.label_of()}"
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>{html.escape(page_title)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{design.GOOGLE_FONTS_URL}" rel="stylesheet">
<style>
{design.css_variables()}
* {{ box-sizing: border-box; }}
body {{ font-family: {design.FONT_FAMILY}; font-size: 15px; line-height: {design.LINE_HEIGHT};
        margin: 0; background: var(--fgd-background); color: var(--fgd-text); }}
h1 {{ font-size: 28px; font-weight: 800; }}
h2 {{ font-size: 22px; font-weight: 700; }}
h3 {{ font-size: 17px; font-weight: 600; }}
a {{ color: var(--fgd-primary-hover); }}
header {{ padding: 16px 24px; background: var(--fgd-surface); border-bottom: 1px solid var(--fgd-border);
          display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }}
header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
header h1 a {{ color: inherit; text-decoration: none; }}
nav {{ display: flex; gap: 4px; flex-wrap: wrap; margin-left: auto; }}
nav a {{ color: var(--fgd-text-muted); text-decoration: none; padding: 8px 12px;
         border-radius: {design.BUTTON_RADIUS}; font-size: 14px; font-weight: 600; }}
nav a:hover {{ background: var(--fgd-card); color: var(--fgd-text); }}
nav a.active {{ background: var(--fgd-primary-soft); color: var(--fgd-text); }}
main {{ padding: 24px; max-width: 960px; margin: 0 auto; }}
footer {{ text-align: center; padding: 24px; font-size: 12px; color: var(--fgd-text-muted); }}
.card {{ background: var(--fgd-card); border: 1px solid var(--fgd-border);
         border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }}
.grid-offers {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }}
a.button, button.button {{ display: inline-flex; align-items: center; justify-content: center; gap: 6px;
            background: var(--fgd-primary); color: #ffffff; height: {design.BUTTON_HEIGHT};
            padding: 0 {design.BUTTON_PADDING_X}; border-radius: {design.BUTTON_RADIUS};
            text-decoration: none; font-weight: 600; font-size: 14px; border: none; cursor: pointer; }}
a.button:hover, button.button:hover {{ background: var(--fgd-primary-hover); }}
a.button:active, button.button:active {{ background: var(--fgd-primary-active); }}
a.button.secondary, button.button.secondary {{ background: #232a3d; color: var(--fgd-text); }}
a.button.secondary:hover, button.button.secondary:hover {{ background: #2a3149; }}
a.button.danger, button.button.danger {{ background: var(--fgd-danger); }}
a.button.danger:hover, button.button.danger:hover {{ background: var(--fgd-danger-hover); }}
button.button:disabled, a.button.disabled {{ background: var(--fgd-surface);
            color: var(--fgd-text-muted); cursor: not-allowed; }}
table {{ width: 100%; border-collapse: collapse; }}
td, th {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--fgd-border); }}
select, input[type=text] {{ background: var(--fgd-background); color: var(--fgd-text);
          border: 1px solid var(--fgd-border); border-radius: 8px; padding: 8px; min-width: 200px; }}
label.check {{ display: block; padding: 6px 0; }}
.ok {{ color: var(--fgd-success); }}
.warn {{ color: var(--fgd-warning); }}
.urgent {{ color: var(--fgd-urgent); }}
.critical {{ color: var(--fgd-critical); }}
.muted {{ color: var(--fgd-text-muted); font-size: 13px; }}
.badge {{ display: inline-block; background: var(--fgd-card); border: 1px solid var(--fgd-border);
          color: var(--fgd-text); border-radius: 999px; padding: 2px 10px; font-size: 12px;
          font-weight: 600; margin-right: 6px; text-decoration: none; }}
a.badge:hover {{ border-color: var(--fgd-primary); }}
a.badge.active {{ background: var(--fgd-primary-soft); border-color: var(--fgd-primary); color: #ffffff; }}
.badge.free {{ background: var(--fgd-primary); border-color: var(--fgd-primary); color: #ffffff; }}
.badge.new {{ color: var(--fgd-secondary); border-color: var(--fgd-secondary); }}
.badge.ending {{ color: var(--fgd-urgent); border-color: var(--fgd-urgent); }}
.badge.ended {{ color: var(--fgd-ended); border-color: var(--fgd-ended); }}
.badge.platform-steam {{ color: var(--fgd-platform-steam); border-color: var(--fgd-platform-steam); }}
.badge.platform-epic {{ color: var(--fgd-platform-epic); border-color: var(--fgd-platform-epic); }}
.badge.platform-gog {{ color: var(--fgd-platform-gog); border-color: var(--fgd-platform-gog); }}
.badge.platform-ubisoft {{ color: var(--fgd-platform-ubisoft); border-color: var(--fgd-platform-ubisoft); }}
.offer-thumb {{ width: 100%; aspect-ratio: {design.IMAGE_RATIO}; object-fit: {design.IMAGE_FIT};
          border-radius: {design.IMAGE_RADIUS}; background: var(--fgd-surface); display: block;
          margin-bottom: 12px; }}
.offer-badges {{ margin-bottom: 8px; }}
.hero {{ text-align: center; padding: 48px 16px; }}
.hero .button {{ margin: 8px; }}
.guild-row {{ display: flex; align-items: center; gap: 12px; }}
.guild-row img {{ width: 40px; height: 40px; border-radius: 50%; }}
.guild-row .spacer {{ margin-left: auto; }}
.filters a {{ margin-right: 8px; }}
.notice {{ background: rgba(74, 222, 128, 0.08); border: 1px solid rgba(74, 222, 128, 0.35);
           border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; }}
.notice.env-banner {{ background: rgba(250, 204, 21, 0.08); border-color: rgba(250, 204, 21, 0.35); }}
.env-tag {{ margin-left: 8px; }}
</style>
</head>
<body>
<header>
<h1><a href="/">🎮 {html.escape(site_name)}</a></h1>{badge}
{_nav(user, active)}
</header>
<main>
{_environment_banner()}
{body}
</main>
<footer>{html.escape(design.FOOTER)}{footer_note}</footer>
</body>
</html>"""


def _nav(user: dict | None, active: str) -> str:
    if not user:
        return (
            '<nav><a href="/offres"'
            + (' class="active"' if active == "offres" else "")
            + '>🎁 Offres</a>'
            '<a href="/login">Se connecter</a></nav>'
        )
    links = (
        ("/", "accueil", "🏠 Accueil"),
        ("/serveurs", "serveurs", "🖥️ Serveurs"),
        ("/offres", "offres", "🎁 Offres"),
        ("/alertes", "alertes", "🔔 Alertes"),
        ("/compte", "compte", "🔐 Compte"),
    )
    items = "".join(
        f'<a href="{href}" class="active">{label}</a>'
        if key == active
        else f'<a href="{href}">{label}</a>'
        for href, key, label in links
    )
    return f"<nav>{items}</nav>"


def _csrf_field(csrf_token: str) -> str:
    return f'<input type="hidden" name="csrf" value="{html.escape(csrf_token)}">'


# ---------- Pages ----------


def render_home(stats: dict, user: dict | None) -> str:
    if not user:
        body = f"""
<div class="hero">
<h2>Les jeux gratuits, directement sur Discord.</h2>
<p class="muted">Steam, Epic Games Store, GOG, Ubisoft : FreeGameDrop surveille les offres
et les annonce dans tes salons.</p>
<p>
<a class="button" href="{html.escape(build_invite_url())}">➕ Ajouter à Discord</a>
<a class="button secondary" href="/login">Se connecter avec Discord</a>
</p>
</div>
{_stats_cards(stats)}
"""
        return _page("FreeGameDrop — Les jeux gratuits sur Discord", body, user=None, active="accueil")

    body = f"""
<p>Connecté en tant que <strong>{html.escape(user.get('username', ''))}</strong>
· <a href="/logout">Se déconnecter</a></p>
{_stats_cards(stats)}
<div class="card">
<h3>Et maintenant ?</h3>
<p><a class="button" href="/serveurs">🖥️ Gérer mes serveurs</a>
<a class="button secondary" href="/alertes">🔔 Mes alertes</a></p>
</div>
"""
    return _page("FreeGameDrop — Tableau de bord", body, user=user, active="accueil")


def _stats_cards(stats: dict) -> str:
    cards = "".join(
        f'<div class="card"><h3>{html.escape(str(value))}</h3><p>{html.escape(label)}</p></div>'
        for label, value in (
            ("Serveurs", stats.get("guilds", 0)),
            ("Offres suivies", stats.get("total_offers", 0)),
            ("Offres (30 jours)", stats.get("offers_last_30_days", 0)),
            ("Favoris enregistrés", stats.get("total_favorites", 0)),
        )
    )
    sources = stats.get("offers_by_source") or {}
    sources_rows = "".join(
        f"<tr><td>{html.escape(source)}</td><td>{count}</td></tr>"
        for source, count in sorted(sources.items())
    )
    return f"""
<div class="grid">{cards}</div>
<div class="card">
<h3>Offres par source</h3>
<table><tr><th>Source</th><th>Offres</th></tr>{sources_rows}</table>
</div>
"""


def render_guilds(user: dict, guilds: list[dict]) -> str:
    """`guilds` : [{id, name, icon, bot_present}] — déjà filtrés côté serveur."""
    if not guilds:
        rows = (
            '<div class="card"><p>Aucun serveur gérable trouvé sur ton compte.</p>'
            '<p class="muted">Il faut être propriétaire, administrateur ou avoir la permission '
            "« Gérer le serveur ». Reconnecte-toi si tu viens d'obtenir ces droits.</p></div>"
        )
    else:
        rows = ""
        for guild in guilds:
            icon = guild_icon_url(guild)
            icon_html = f'<img src="{html.escape(icon)}" alt="">' if icon else "<span>🖥️</span>"
            if guild.get("bot_present"):
                status = '<span class="ok">🟢 FreeGameDrop installé</span>'
                action = f'<a class="button" href="/serveurs/{html.escape(str(guild["id"]))}">Configurer</a>'
            else:
                status = '<span class="muted">⚪ FreeGameDrop non installé</span>'
                action = (
                    f'<a class="button secondary" href="{html.escape(build_invite_url(guild["id"]))}">'
                    "Ajouter FreeGameDrop</a>"
                )
            rows += f"""
<div class="card guild-row">
{icon_html}
<div><strong>{html.escape(guild.get('name', ''))}</strong><br>{status}</div>
<div class="spacer">{action}</div>
</div>
"""
    body = f"<h2>Mes serveurs</h2>{rows}"
    return _page("FreeGameDrop — Mes serveurs", body, user=user, active="serveurs")


def render_guild_config(
    user: dict,
    guild: dict,
    *,
    channels: list[tuple[int, str]],
    roles: list[tuple[int, str]],
    platform_channels: dict,
    platform_roles: dict,
    reminder_channel_id: int | None,
    permissions: list[tuple[str, str, bool]],
    csrf_token: str,
    saved: bool = False,
) -> str:
    """Page de configuration d'un serveur où le bot est installé.

    `permissions` : [(label, description, accordée)].
    """
    notice = '<div class="notice">✅ Configuration enregistrée.</div>' if saved else ""

    missing = [label for label, _desc, ok in permissions if not ok]
    perm_rows = "".join(
        f'<tr><td>{"✅" if ok else "⚠️"}</td><td>{html.escape(label)}</td>'
        f'<td class="muted">{html.escape(desc)}</td></tr>'
        for label, desc, ok in permissions
    )
    perm_warning = ""
    if missing:
        perm_warning = f"""
<p class="warn">⚠️ Permissions manquantes : {html.escape(', '.join(missing))}.
FreeGameDrop ne pourra pas fonctionner complètement sans elles.</p>
<p><a class="button secondary" href="{html.escape(build_invite_url(guild['id']))}">
Corriger (ré-inviter le bot)</a></p>
"""

    def channel_select(name: str, selected: int | None) -> str:
        options = '<option value="">— aucun —</option>'
        for channel_id, channel_name in channels:
            chosen = " selected" if selected == channel_id else ""
            options += (
                f'<option value="{channel_id}"{chosen}># {html.escape(channel_name)}</option>'
            )
        return f'<select name="{html.escape(name)}">{options}</select>'

    def role_select(name: str, selected: int | None) -> str:
        options = '<option value="">— aucun —</option>'
        for role_id, role_name in roles:
            chosen = " selected" if selected == role_id else ""
            options += f'<option value="{role_id}"{chosen}>@ {html.escape(role_name)}</option>'
        return f'<select name="{html.escape(name)}">{options}</select>'

    platform_rows = ""
    for key in config.PLATFORM_KEYS:
        platform = config.PLATFORMS[key]
        platform_rows += f"""
<tr>
<td>{platform.emoji} {html.escape(platform.name)}</td>
<td>{channel_select(f'channel_{key}', platform_channels.get(key))}</td>
<td>{role_select(f'role_{key}', platform_roles.get(key))}</td>
</tr>
"""

    body = f"""
<p><a href="/serveurs">← Mes serveurs</a></p>
<h2>⚙️ {html.escape(guild.get('name', ''))}</h2>
{notice}
<div class="card">
<h3>🛡️ Permissions de FreeGameDrop</h3>
<table>{perm_rows}</table>
{perm_warning}
</div>
<form method="post" action="/serveurs/{html.escape(str(guild['id']))}">
{_csrf_field(csrf_token)}
<div class="card">
<h3>📢 Salons d'annonces et rôles par plateforme</h3>
<p class="muted">Laisse « — aucun — » pour ne rien changer. Tu peux aussi tout créer d'un coup
avec la commande <code>/setup-auto</code> sur Discord.</p>
<table>
<tr><th>Plateforme</th><th>Salon des annonces</th><th>Rôle à mentionner</th></tr>
{platform_rows}
</table>
</div>
<div class="card">
<h3>⏰ Rappels « se termine aujourd'hui »</h3>
<p>{channel_select('reminder_channel', reminder_channel_id)}</p>
</div>
<p><button class="button" type="submit">Enregistrer</button></p>
</form>
"""
    return _page(
        f"FreeGameDrop — {guild.get('name', '')}", body, user=user, active="serveurs"
    )


def render_offers(
    offers: list[dict], user: dict | None, selected_platform: str | None = None
) -> str:
    filters = (
        '<a class="badge active" href="/offres">Toutes</a>'
        if not selected_platform
        else '<a class="badge" href="/offres">Toutes</a>'
    )
    for key in config.PLATFORM_KEYS:
        platform = config.PLATFORMS[key]
        label = f"{platform.emoji} {html.escape(platform.name)}"
        css_class = f"badge platform-{key}" + (" active" if key == selected_platform else "")
        filters += f'<a class="{css_class}" href="/offres?plateforme={key}">{label}</a>'

    if not offers:
        cards = '<div class="card"><p>Aucune offre connue pour ce filtre, reviens bientôt !</p></div>'
    else:
        cards = ""
        now = datetime.now(timezone.utc)
        for offer in offers:
            key = platform_utils.detect_platform(offer)
            emoji = platform_utils.emoji(key)
            worth = str(offer.get("worth") or "").strip()
            worth_html = (
                f'<s class="muted">{html.escape(worth)}</s> → <strong>GRATUIT</strong>'
                if worth and worth.upper() != "N/A"
                else "<strong>GRATUIT</strong>"
            )
            end = parse_end_datetime(offer.get("end_date"))
            level = design.urgency_level(end, now=now)
            if level == "unknown":
                remaining = '<span class="muted">⏳ Sans date de fin connue</span>'
                remaining_badge = ""
            elif level == "ended":
                remaining = '<span class="muted">⚫ Offre expirée</span>'
                remaining_badge = '<span class="badge ended">EXPIRÉ</span>'
            else:
                hours = (end - now).total_seconds() / 3600
                if hours >= 48:
                    remaining_text = f"{int(hours // 24)} jours restants"
                elif hours >= 24:
                    remaining_text = "1 jour restant"
                else:
                    remaining_text = f"{max(1, int(hours))} h restantes"
                urgency_class = {"warning": "warn", "urgent": "urgent", "critical": "critical"}.get(
                    level, "ok"
                )
                remaining = (
                    f'{design.URGENCY_EMOJI[level]} <span class="{urgency_class}">'
                    f"{html.escape(remaining_text)}</span>"
                )
                remaining_badge = (
                    '<span class="badge ending">SE TERMINE BIENTÔT</span>'
                    if level in {"urgent", "critical"}
                    else ""
                )
            link = str(
                offer.get("open_giveaway_url")
                or offer.get("claim_url")
                or offer.get("gamerpower_url")
                or offer.get("source_url")
                or ""
            ).strip()
            ended = level == "ended"
            button = (
                f'<p><a class="button{" secondary" if ended else ""}" '
                f'href="{html.escape(link)}" rel="noopener noreferrer" target="_blank">'
                f'{"🔗 Voir l’offre" if ended else "🎁 Récupérer le jeu"}</a></p>'
                if link.startswith("http")
                else ""
            )
            thumbnail = str(offer.get("thumbnail") or "").strip()
            image_html = (
                f'<img class="offer-thumb" src="{html.escape(thumbnail)}" '
                f'alt="{html.escape(str(offer.get("title") or ""))}" loading="lazy">'
                if thumbnail.startswith("http")
                else ""
            )
            platform_badge = (
                f'<span class="badge platform-{key}">{emoji} '
                f"{html.escape(platform_utils.display_name(key))}</span>"
                if key is not None
                else f'<span class="badge">{html.escape(emoji)}</span>'
            )
            cards += f"""
<div class="card">
{image_html}
<h3>{html.escape(str(offer.get('title') or ''))}</h3>
<p class="offer-badges"><span class="badge free">GRATUIT</span>{platform_badge}{remaining_badge}</p>
<p>{worth_html}</p>
<p>{remaining}</p>
{button}
</div>
"""
        cards = f'<div class="grid-offers">{cards}</div>'

    body = f"""
<h2>🎁 Jeux gratuits</h2>
<p class="filters">{filters}</p>
{cards}
"""
    return _page("FreeGameDrop — Jeux gratuits", body, user=user, active="offres")


def render_alerts(
    user: dict,
    notifications: dict,
    preferences: dict,
    csrf_token: str,
    saved: bool = False,
) -> str:
    notice = '<div class="notice">✅ Alertes enregistrées.</div>' if saved else ""

    event_boxes = "".join(
        f'<label class="check"><input type="checkbox" name="event_{key}"'
        f'{" checked" if notifications.get(key) else ""}> {html.escape(label)}</label>'
        for key, label in config.USER_NOTIFICATION_EVENT_LABELS.items()
    )
    selected_types = set(preferences.get("offer_types") or [])
    type_boxes = "".join(
        f'<label class="check"><input type="checkbox" name="type_{key}"'
        f'{" checked" if key in selected_types else ""}> {html.escape(label)}</label>'
        for key, label in config.OFFER_TYPE_LABELS.items()
    )

    body = f"""
<h2>🔔 Mes alertes</h2>
{notice}
<form method="post" action="/alertes">
{_csrf_field(csrf_token)}
<div class="card">
<h3>Alertes en message privé</h3>
<p class="muted">Les alertes arrivent en DM : pense à accepter les messages privés du bot.
« Se termine bientôt » ne concerne que tes favoris.</p>
{event_boxes}
</div>
<div class="card">
<h3>Types d'offres qui m'intéressent</h3>
{type_boxes}
</div>
<p><button class="button" type="submit">Enregistrer</button></p>
</form>
<p class="muted">Les mêmes réglages sont accessibles sur Discord avec /alertes et /preferences.</p>
"""
    return _page("FreeGameDrop — Mes alertes", body, user=user, active="alertes")


def render_account(user: dict, summary: dict, csrf_token: str) -> str:
    user_id = str(user.get("user_id", ""))
    masked = f"{user_id[:4]}…{user_id[-2:]}" if len(user_id) > 6 else "••••"
    body = f"""
<h2>🔐 Mon compte</h2>
<div class="card">
<h3>Discord</h3>
<p><strong>@{html.escape(user.get('username', ''))}</strong><br>
<span class="muted">ID : {html.escape(masked)}</span></p>
</div>
<div class="card">
<h3>Données enregistrées</h3>
<table>
<tr><td>⭐ Favoris</td><td>{summary.get('favorites', 0)}</td></tr>
<tr><td>⚙️ Préférences</td><td>{summary.get('preferences', 0)}</td></tr>
<tr><td>🔔 Alertes configurées</td><td>{summary.get('notifications', 0)}</td></tr>
<tr><td>📜 Historique d'alertes</td><td>{summary.get('alert_history', 0)}</td></tr>
</table>
<p class="muted">FreeGameDrop ne stocke ni ton jeton Discord, ni tes messages. Seul ton
identifiant Discord relie ces données à ton compte.</p>
</div>
<div class="card">
<form method="post" action="/compte/supprimer"
      onsubmit="return confirm('Supprimer définitivement toutes tes données ?');">
{_csrf_field(csrf_token)}
<button class="button danger" type="submit">Supprimer mes données</button>
<a class="button secondary" href="/logout">Se déconnecter</a>
</form>
</div>
"""
    return _page("FreeGameDrop — Mon compte", body, user=user, active="compte")


def render_error(message: str, user: dict | None = None) -> str:
    return _page(
        "FreeGameDrop — Erreur",
        f'<div class="card"><p>{html.escape(message)}</p><p><a href="/">← Retour à l\'accueil</a></p></div>',
        user=user,
    )

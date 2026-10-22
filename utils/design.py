"""Identité visuelle de FreeGameDrop — source unique des choix graphiques.

ORVEX (marque mère, discrète)
   └── FREEGAMEDROP (produit, marque forte)

FreeGameDrop partage le même univers visuel que OverX et OverLoad : un style
**vert forêt, naturel, moderne et premium** — pas de dégradés flashy, de néons
ni d'effets gaming excessifs. Trois mots guident toutes les décisions
graphiques : **Naturel — Moderne — Premium**.

Ce module est un dictionnaire de « design tokens » partagé par :

- les embeds Discord (`utils/embeds.py`) ;
- le tableau de bord web (`web/dashboard.py`, via `css_variables()`) ;
- la documentation de marque (`DESIGN.md`).

Il ne dépend ni de Discord ni de `config` : `config` importe ces tokens, jamais l'inverse.
"""

from __future__ import annotations

from datetime import datetime, timezone

# ---------- Marque ----------

BRAND_NAME = "FreeGameDrop"
PARENT_BRAND = "Orvex"
BRAND_WORDS = ("Naturel", "Moderne", "Premium")
FOOTER = f"🎁 {BRAND_NAME} · par {PARENT_BRAND}"

# ---------- Palette ----------
# Forme « #RRGGBB » (CSS / documentation). `rgb()` convertit pour Discord (entier 0xRRGGBB).
#
# Palette « forêt » commune à FreeGameDrop, OverX et OverLoad : les trois produits
# doivent avoir l'air de faire partie du même univers. Les cinq couleurs ci-dessous
# sont la base ; tout le reste en dérive.

FOREST = "#173D2B"  # vert forêt — couleur principale
LEAF = "#285B40"  # vert feuille — boutons et actions
SAGE = "#91A889"  # vert sauge — accents secondaires
IVORY = "#F3F1E8"  # ivoire — fonds clairs, texte principal sur fond sombre
GRAPHITE = "#242923"  # graphite — texte (interfaces claires) et fonds sombres

# Couleur principale : celle qu'on associera à FreeGameDrop en une demi-seconde.
# Filet des embeds, accents de marque du dashboard, site.
PRIMARY = FOREST
PRIMARY_HOVER = "#1F4A32"  # forêt éclairci
PRIMARY_ACTIVE = "#102A1E"  # forêt assombri
PRIMARY_SOFT = "#1E352A"  # fond discret teinté forêt (badges, états actifs) sur thème sombre

# Couleur d'action : boutons principaux et appels à l'action (« Récupérer le jeu »).
ACTION = LEAF
ACTION_HOVER = "#336C4E"  # feuille éclairci
ACTION_ACTIVE = "#1F4A32"  # feuille assombri

# Couleur secondaire : statistiques, catégories, illustrations, hover, détails, liens
# sur fond sombre. Complète la principale sans lui voler la vedette.
SECONDARY = SAGE
SECONDARY_SOFT = "#2E3A2C"  # fond discret teinté sauge sur thème sombre

# Neutres — thème sombre graphite (jamais de #000000 pur, un dashboard tout noir
# paraît amateur). Le thème clair correspondant utilise IVORY en fond et GRAPHITE
# en texte.
BACKGROUND = "#1A1E1A"  # fond le plus sombre (graphite assombri)
SURFACE = GRAPHITE  # header, barres latérales
CARD = "#2C322C"  # légèrement plus clair que la surface
TEXT = IVORY  # texte principal sur fond sombre
TEXT_MUTED = "#A3AEA0"  # sauge grisé — texte secondaire
BORDER = "#3A423A"

# Sémantique — boutons « danger » (supprimer, désactiver, réinitialiser).
DANGER = "#C14B42"  # rouge brique, sans agressivité néon
DANGER_HOVER = "#A93E36"

# Niveaux d'urgence d'une offre (voir `urgency_level`) — tons naturels, jamais fluo.
SUCCESS = "#7FAE6E"  # 🟢 normal    — plus de 24 h
WARNING = "#E0C169"  # 🟡 attention — moins de 24 h
URGENT = "#DE8B4D"  # 🟠 urgent    — moins de 6 h
CRITICAL = "#D96A5B"  # 🔴 se termine — moins d'1 h
ENDED = "#7A827B"  # ⚫ terminée

# Couleurs des plateformes : reconnaissables, mais jamais confondues avec la marque.
# FreeGameDrop garde sa propre couleur ; les plateformes n'apparaissent que dans
# de petits badges, icônes, labels et filtres — jamais en embed entièrement coloré.
PLATFORM_COLOURS = {
    "steam": "#66C0F4",  # bleu Steam
    "epic": "#D9D9D9",  # blanc cassé Epic (marque noir/blanc)
    "gog": "#86328B",  # violet GOG (couleur réelle de la marque)
    "ubisoft": "#0070FF",  # bleu Ubisoft
}


def rgb(value: str) -> int:
    """'#173D2B' -> 0x173D2B (pour `discord.Colour` / les rôles)."""
    return int(value.lstrip("#"), 16)


# ---------- Urgence ----------

CRITICAL_HOURS = 1.0  # < 1 h  → 🔴 « se termine »
URGENT_HOURS = 6.0  # < 6 h  → 🟠 « urgent »
WARNING_HOURS = 24.0  # < 24 h → 🟡 « attention » ; au-delà 🟢 « normal »

URGENCY_EMOJI = {
    "normal": "🟢",
    "warning": "🟡",
    "urgent": "🟠",
    "critical": "🔴",
    "ended": "⚫",
    "unknown": "⏳",
}

URGENCY_COLOURS = {
    "normal": SUCCESS,
    "warning": WARNING,
    "urgent": URGENT,
    "critical": CRITICAL,
    "ended": ENDED,
    "unknown": TEXT_MUTED,
}


def urgency_level(end: datetime | None, now: datetime | None = None) -> str:
    """Niveau d'urgence à partir d'une échéance (datetime aware ou naive-UTC)."""
    if end is None:
        return "unknown"
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    seconds = (end - now).total_seconds()
    if seconds <= 0:
        return "ended"
    hours = seconds / 3600
    if hours < CRITICAL_HOURS:
        return "critical"
    if hours < URGENT_HOURS:
        return "urgent"
    if hours < WARNING_HOURS:
        return "warning"
    return "normal"


# ---------- Variantes d'embed ----------
# La marque (filet vert forêt) reste identique quelle que soit la plateforme :
# seule l'étiquette d'auteur change. « ended » passe en gris neutre (historique).
# Icônes simples et discrètes : l'urgence est déjà portée par 🟢🟡🟠🔴 dans le
# champ « Fin de l'offre », pas besoin d'un effet « hype ».

EMBED_VARIANTS = {
    "new": {"author": "🎁 JEU GRATUIT", "colour": PRIMARY},
    "ending_soon": {"author": "⏳ SE TERMINE BIENTÔT", "colour": PRIMARY},
    "extended": {"author": "🔄 OFFRE PROLONGÉE", "colour": PRIMARY},
    "ended": {"author": "❌ OFFRE TERMINÉE", "colour": ENDED},
}
EMBED_VARIANT_KEYS = tuple(EMBED_VARIANTS)
# Mise en évidence spéciale des offres exceptionnelles : une étoile sobre,
# jamais un effet gaming.
MEGA_DEAL_AUTHOR = "⭐ OFFRE EXCEPTIONNELLE"


def embed_colour(variant: str = "new") -> int:
    """Couleur (entier Discord) du filet de l'embed selon la variante."""
    return rgb(EMBED_VARIANTS.get(variant, EMBED_VARIANTS["new"])["colour"])


# ---------- Typographie ----------
# Une seule famille : Inter. Ce qui compte est la hiérarchie (poids, taille, espacement).

FONT_FAMILY = "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif"
GOOGLE_FONTS_URL = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"

# nom → (taille px, poids)
TYPE_SCALE = {
    "h1": (28, 800),  # énorme, très visible
    "h2": (22, 700),  # important
    "h3": (17, 600),  # sous-titre de carte
    "body": (15, 400),  # facile à lire
    "small": (13, 400),  # informations secondaires
    "button": (14, 600),
    "caption": (12, 500),  # légende, pied de page
}
LINE_HEIGHT = 1.55

# ---------- Boutons ----------
# Un seul langage visuel partout : primaire / secondaire / danger.

BUTTON_RADIUS = "10px"  # coins légèrement arrondis
BUTTON_HEIGHT = "40px"  # assez grand, très visible
BUTTON_PADDING_X = "18px"

BUTTONS = {
    # Bouton principal : vert feuille, texte ivoire.
    "primary": {"bg": ACTION, "bg_hover": ACTION_HOVER, "bg_active": ACTION_ACTIVE, "text": IVORY},
    "secondary": {"bg": CARD, "bg_hover": "#343B34", "bg_active": SURFACE, "text": TEXT},
    "danger": {"bg": DANGER, "bg_hover": DANGER_HOVER, "bg_active": "#8F332B", "text": IVORY},
}
BUTTON_DISABLED = {"bg": SURFACE, "text": TEXT_MUTED}

# ---------- Images ----------
# Les jeux ont des visuels très différents : on ne contrôle pas l'original,
# on contrôle la manière de l'afficher. Ratio et coins identiques partout.

IMAGE_RATIO = "16 / 9"
IMAGE_RADIUS = "12px"
IMAGE_FIT = "cover"  # recadrage sans déformation

# ---------- Badges ----------
# Chaque badge a une fonction précise ; maximum quelques badges par surface
# (pas de sapin de Noël).

BADGE_FREE = {"label": "GRATUIT", "colour": ACTION}
BADGE_NEW = {"label": "NOUVEAU", "colour": SECONDARY}
BADGE_ENDING = {"label": "SE TERMINE BIENTÔT", "colour": URGENT}
BADGE_ENDED = {"label": "EXPIRÉ", "colour": ENDED}


def css_variables() -> str:
    """Bloc `:root` CSS pour le tableau de bord web — généré depuis les tokens."""
    tokens = {
        "forest": FOREST,
        "leaf": LEAF,
        "sage": SAGE,
        "ivory": IVORY,
        "graphite": GRAPHITE,
        "primary": PRIMARY,
        "primary-hover": PRIMARY_HOVER,
        "primary-active": PRIMARY_ACTIVE,
        "primary-soft": PRIMARY_SOFT,
        "action": ACTION,
        "action-hover": ACTION_HOVER,
        "action-active": ACTION_ACTIVE,
        "secondary": SECONDARY,
        "secondary-soft": SECONDARY_SOFT,
        "background": BACKGROUND,
        "surface": SURFACE,
        "card": CARD,
        "text": TEXT,
        "text-muted": TEXT_MUTED,
        "border": BORDER,
        "danger": DANGER,
        "danger-hover": DANGER_HOVER,
        "success": SUCCESS,
        "warning": WARNING,
        "urgent": URGENT,
        "critical": CRITICAL,
        "ended": ENDED,
        **{f"platform-{key}": colour for key, colour in PLATFORM_COLOURS.items()},
    }
    lines = "\n".join(f"  --fgd-{name}: {value};" for name, value in tokens.items())
    return f":root {{\n{lines}\n}}"

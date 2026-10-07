"""Design tokens de l'identité visuelle FreeGameDrop (utils/design.py)."""

import re
from datetime import datetime, timedelta, timezone

import pytest

from utils import design

HEX = re.compile(r"^#[0-9A-F]{6}$")


def test_la_palette_est_en_hex_valide():
    tokens = [
        design.PRIMARY,
        design.PRIMARY_HOVER,
        design.PRIMARY_ACTIVE,
        design.PRIMARY_SOFT,
        design.SECONDARY,
        design.BACKGROUND,
        design.SURFACE,
        design.CARD,
        design.TEXT,
        design.TEXT_MUTED,
        design.BORDER,
        design.DANGER,
        design.SUCCESS,
        design.WARNING,
        design.URGENT,
        design.CRITICAL,
        design.ENDED,
        *design.PLATFORM_COLOURS.values(),
    ]
    for token in tokens:
        assert HEX.match(token), f"{token} n'est pas un hex #RRGGBB"


def test_rgb_convertit_pour_discord():
    assert design.rgb("#7C3AED") == 0x7C3AED
    assert design.rgb(design.PRIMARY) == 0x7C3AED


def test_aucun_noir_pur_dans_les_neutres():
    for token in (design.BACKGROUND, design.SURFACE, design.CARD):
        assert token.upper() != "#000000"
    # le fond est le plus sombre, la carte la plus claire
    assert design.rgb(design.BACKGROUND) < design.rgb(design.SURFACE) < design.rgb(design.CARD)


def test_les_couleurs_plateformes_sont_distinctes_de_la_marque():
    for key, colour in design.PLATFORM_COLOURS.items():
        assert colour != design.PRIMARY, f"{key} serait confondu avec la marque"
    assert len(set(design.PLATFORM_COLOURS.values())) == len(design.PLATFORM_COLOURS)


def test_trois_mots_pour_la_marque():
    assert len(design.BRAND_WORDS) == 3
    assert design.BRAND_NAME == "FreeGameDrop"
    assert design.PARENT_BRAND == "Orvex"
    assert "FreeGameDrop" in design.FOOTER and "Orvex" in design.FOOTER


@pytest.mark.parametrize(
    "heures, attendu",
    [
        (None, "unknown"),
        (-1, "ended"),
        (0.5, "critical"),
        (3, "urgent"),
        (12, "warning"),
        (48, "normal"),
    ],
)
def test_niveaux_durgence(heures, attendu):
    now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
    fin = None if heures is None else now + timedelta(hours=heures)

    assert design.urgency_level(fin, now=now) == attendu


def test_chaque_niveau_durgence_a_un_emoji_et_une_couleur():
    for niveau in ("normal", "warning", "urgent", "critical", "ended", "unknown"):
        assert design.URGENCY_EMOJI[niveau]
        assert HEX.match(design.URGENCY_COLOURS[niveau])


def test_couleurs_durgence_se_degradent_du_vert_au_rouge():
    ordre = ["normal", "warning", "urgent", "critical", "ended"]
    assert [design.URGENCY_COLOURS[n] for n in ordre] == [
        design.SUCCESS,
        design.WARNING,
        design.URGENT,
        design.CRITICAL,
        design.ENDED,
    ]


def test_variantes_dembed_couvrent_les_quatre_etats():
    assert set(design.EMBED_VARIANTS) == {"new", "ending_soon", "extended", "ended"}
    # la marque colore toutes les variantes actives ; « ended » passe en neutre
    for variante in ("new", "ending_soon", "extended"):
        assert design.embed_colour(variante) == design.rgb(design.PRIMARY)
    assert design.embed_colour("ended") == design.rgb(design.ENDED)
    # variante inconnue → repli sur « new »
    assert design.embed_colour("inconnue") == design.rgb(design.PRIMARY)


def test_echelle_typographique_couvre_les_sept_styles():
    assert set(design.TYPE_SCALE) == {"h1", "h2", "h3", "body", "small", "button", "caption"}
    tailles = [design.TYPE_SCALE[style][0] for style in design.TYPE_SCALE]
    assert tailles[0] == max(tailles)  # h1 est le plus grand
    for taille, poids in design.TYPE_SCALE.values():
        assert taille > 0 and 100 <= poids <= 900


def test_css_variables_exposent_les_tokens():
    css = design.css_variables()

    assert css.startswith(":root {")
    assert "--fgd-primary: #7C3AED;" in css
    assert "--fgd-background: #0B0E14;" in css
    for key in design.PLATFORM_COLOURS:
        assert f"--fgd-platform-{key}:" in css

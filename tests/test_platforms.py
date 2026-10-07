"""Reconnaissance des plateformes à partir de la réponse de l'API."""

import discord
import pytest

from config import PLATFORM_KEYS, PLATFORMS
from utils import design, platforms


@pytest.mark.parametrize(
    "champ_api, attendu",
    [
        ("PC (Steam)", "steam"),
        ("Epic Games Store", "epic"),
        ("GOG", "gog"),
        ("Ubisoft Connect", "ubisoft"),
        ("DRM-Free, itch.io", None),
        ("", None),
    ],
)
def test_detection_de_la_plateforme(champ_api, attendu):
    assert platforms.detect_platform({"platforms": champ_api}) == attendu


def test_detection_insensible_a_la_casse():
    assert platforms.detect_platform({"platforms": "EPIC GAMES STORE"}) == "epic"


def test_jeu_sans_champ_plateforme():
    assert platforms.detect_platform({}) is None
    assert platforms.matches({}, PLATFORM_KEYS) is False


def test_matches_sur_plusieurs_plateformes():
    jeu = {"platforms": "PC (Steam), Epic Games Store"}

    assert platforms.matches(jeu, ["steam"]) is True
    assert platforms.matches(jeu, ["gog"]) is False
    assert platforms.matches(jeu, ["gog", "epic"]) is True
    assert platforms.matches(jeu, ["inconnue"]) is False


def test_nom_et_couleur_du_role():
    assert platforms.role_name("steam") == "🔵 Steam"
    assert platforms.channel_name("steam") == "jeux-steam"
    assert platforms.role_colour("steam") == discord.Colour(0x66C0F4)


def test_valeurs_par_defaut_pour_une_plateforme_inconnue():
    assert platforms.emoji(None) == "🎁"
    # la couleur par défaut est la couleur principale de la marque, jamais une plateforme
    assert platforms.colour("inconnue") == design.rgb(design.PRIMARY)
    assert platforms.display_name("inconnue") == "inconnue"


def test_couleurs_des_plateformes_issues_des_tokens_de_marque():
    for key, platform in PLATFORMS.items():
        assert platform.colour == design.rgb(design.PLATFORM_COLOURS[key])
        assert platform.colour != design.rgb(design.PRIMARY)


def test_catalogue_coherent():
    for key, platform in PLATFORMS.items():
        assert platform.key == key
        assert platform.name and platform.emoji
        assert platform.keywords, "il faut au moins un mot-clé pour reconnaître la plateforme"
        assert all(mot == mot.lower() for mot in platform.keywords), "mots-clés en minuscules"
        assert 0 <= platform.colour <= 0xFFFFFF
        assert platform.channel_name.startswith("jeux-")

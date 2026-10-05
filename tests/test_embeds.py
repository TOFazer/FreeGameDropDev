"""Mise en forme des annonces."""

from datetime import datetime, timezone

import pytest

from utils import embeds

JEU = {
    "id": 42,
    "title": "Super Jeu Giveaway",
    "description": "  Un   très bon jeu   ",
    "platforms": "PC (Steam)",
    "worth": "19.99",
    "end_date": "2026-10-05 23:59:00",
    "thumbnail": "https://example.com/image.jpg",
    "open_giveaway_url": "https://example.com/jeu",
}


def test_prix_barre_quand_il_est_connu():
    assert embeds.format_price("19.99") == "~~19.99~~ ➜ **GRATUIT**"


@pytest.mark.parametrize("valeur", ["N/A", "n/a", "", None, 0])
def test_prix_inconnu(valeur):
    assert embeds.format_price(valeur) == "**GRATUIT**"


def test_date_de_fin_en_horodatage_discord():
    attendu = int(datetime(2026, 10, 5, 23, 59, tzinfo=timezone.utc).timestamp())

    rendu = embeds.format_end_date("2026-10-05 23:59:00")

    assert rendu == f"<t:{attendu}:R>\n<t:{attendu}:f>"


@pytest.mark.parametrize("valeur", ["bientôt", "", None])
def test_date_de_fin_illisible(valeur):
    assert embeds.format_end_date(valeur) == "Pas de date limite connue"


def test_description_raccourcie_sur_un_mot_entier():
    texte = "mot " * 100

    rendu = embeds.clean_description(texte, limit=20)

    assert rendu.endswith("…")
    assert len(rendu) <= 21
    assert "  " not in rendu


def test_description_courte_inchangee():
    assert embeds.clean_description("  Un   très bon jeu  ") == "Un très bon jeu"


def test_annonce_complete():
    embed, view = embeds.build_game_message(JEU)

    assert embed.title == "🔵 Super Jeu"  # " Giveaway" retiré, emoji Steam ajouté
    assert embed.url == JEU["open_giveaway_url"]
    assert embed.color.value == 0x66C0F4
    assert embed.description == "Un très bon jeu"
    assert [f.value for f in embed.fields] == [
        "~~19.99~~ ➜ **GRATUIT**",
        embeds.format_end_date(JEU["end_date"]),
        "PC (Steam)",
    ]
    assert embed.image.url == JEU["thumbnail"]
    assert len(view.children) == 1 and view.children[0].url == JEU["open_giveaway_url"]


def test_annonce_sans_lien_ni_image():
    embed, view = embeds.build_game_message({"title": "Jeu", "platforms": "itch.io"})

    assert embed.color.value == 0xF1C40F  # couleur par défaut
    assert embed.title == "🎁 Jeu"
    assert view.children == []


def test_lien_de_repli_sur_gamerpower():
    embed, _ = embeds.build_game_message({"title": "Jeu", "gamerpower_url": "https://gp/1"})

    assert embed.url == "https://gp/1"


def test_panneau_des_roles_precise_la_lecture_seule():
    embed = embeds.build_roles_embed()

    assert "lecture seule" in embed.footer.text

"""Filtres de catalogue : type d'offre, valeur en euros, genres, échéances."""

from datetime import datetime, timedelta, timezone

import pytest

from utils import offers


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("game", "game"),
        ("Game", "game"),
        ("DLC", "dlc"),
        ("add-on", "dlc"),
        ("loot", "content"),
        ("Beta", "content"),
        (None, "game"),
        ("mystere", "content"),
    ],
)
def test_classification_du_type(brut, attendu):
    assert offers.classify_offer_type(brut) == attendu


def test_filtre_par_type_en_ou():
    jeu = {"offer_type": "dlc"}
    assert offers.offer_matches_type(jeu, ["game", "dlc"]) is True
    assert offers.offer_matches_type(jeu, ["game"]) is False
    assert offers.offer_matches_type(jeu, []) is False


def test_filtre_temporaire_exige_une_date_de_fin():
    avec_date = {"offer_type": "game", "end_date": "2026-10-10 10:00:00"}
    sans_date = {"offer_type": "game", "end_date": ""}

    assert offers.offer_matches_type(avec_date, ["temporary"]) is True
    assert offers.offer_matches_type(sans_date, ["temporary"]) is False


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("19,99 €", 19.99),
        ("€19.99", 19.99),
        ("19.99 EUR", 19.99),
        ("1.234,56 €", 1234.56),
        ("N/A", None),
        ("", None),
        ("$19.99", None),
    ],
)
def test_parse_prix_en_euros(texte, attendu):
    assert offers.parse_worth_eur(texte) == attendu


def test_normalise_les_genres_connus_uniquement():
    assert offers.normalize_genres(["RPG", "Action", "n'importe quoi"]) == ["action", "rpg"]
    assert offers.normalize_genres("Stratégie") == ["strategy"]  # libellé FR accepté comme alias
    assert offers.normalize_genres("Inconnu") == []
    assert offers.normalize_genres(None) == []


def test_filtre_par_genre_sans_selection_accepte_tout():
    assert offers.offer_matches_genres({"genres": []}, []) is True


def test_filtre_par_genre_avec_selection():
    jeu = {"genres": ["rpg", "action"]}
    assert offers.offer_matches_genres(jeu, {"strategy"}) is False
    assert offers.offer_matches_genres(jeu, {"rpg"}) is True


def test_preferences_combinees():
    jeu = {"offer_type": "game", "worth": "29,99 €", "genres": ["rpg"]}
    preferences = {"offer_types": ["game"], "min_worth_eur": 20, "genres": ["rpg"]}

    assert offers.offer_matches_preferences(jeu, preferences) is True
    assert offers.offer_matches_preferences(jeu, {**preferences, "min_worth_eur": 50}) is False


def test_filtre_catalogue_par_plateforme_et_type():
    jeux = [
        {"id": 1, "platforms": "PC (Steam)", "offer_type": "game"},
        {"id": 2, "platforms": "Epic Games Store", "offer_type": "dlc"},
    ]

    resultat = offers.filter_offers(jeux, platform="steam")
    assert [j["id"] for j in resultat] == [1]

    resultat = offers.filter_offers(jeux, offer_type="dlc")
    assert [j["id"] for j in resultat] == [2]


def test_filtre_catalogue_se_termine_bientot():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    jeux = [
        {"id": 1, "end_date": (now + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")},
        {"id": 2, "end_date": (now + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")},
    ]

    resultat = offers.filter_offers(jeux, period="ending_soon", now=now)

    assert [j["id"] for j in resultat] == [1]


# ---------- Préférences de plateforme ----------


def test_normalisation_des_plateformes():
    assert offers.normalize_platforms(["steam", "epic"]) == ["steam", "epic"]
    assert offers.normalize_platforms("gog") == ["gog"]
    assert offers.normalize_platforms(["Steam", " EPIC ", "xbox"]) == ["steam", "epic"]
    assert offers.normalize_platforms([]) == []
    assert offers.normalize_platforms(None) == []


def test_preferences_sans_plateforme_laissent_tout_passer():
    jeu_epic = {"platforms": "Epic Games Store", "offer_type": "game"}
    preferences = {"offer_types": ["game"], "platforms": []}

    assert offers.offer_matches_preferences(jeu_epic, preferences) is True


def test_preferences_de_plateforme_filtrent_les_alertes():
    jeu_epic = {"platforms": "Epic Games Store", "offer_type": "game"}
    jeu_steam = {"platforms": "PC (Steam)", "offer_type": "game"}
    jeu_inconnu = {"platforms": "itch.io", "offer_type": "game"}
    preferences = {"offer_types": ["game"], "platforms": ["steam"]}

    assert offers.offer_matches_preferences(jeu_steam, preferences) is True
    assert offers.offer_matches_preferences(jeu_epic, preferences) is False
    assert offers.offer_matches_preferences(jeu_inconnu, preferences) is False


# ---------- Offres exceptionnelles ----------


def _jeu_mega(**overrides):
    jeu = {
        "offer_type": "game",
        "worth": "59,99 €",
        "end_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "platforms": "Epic Games Store",
    }
    jeu.update(overrides)
    return jeu


def test_mega_deal_reconnu_sur_une_grande_valeur():
    assert offers.is_mega_deal(_jeu_mega()) is True


def test_mega_deal_refuse_les_petites_valeurs():
    assert offers.is_mega_deal(_jeu_mega(worth="9,99 €")) is False


def test_mega_deal_refuse_les_valeurs_hors_euros():
    # 59,99 $ n'est pas converti ni estimé : aucune devise inventée.
    assert offers.is_mega_deal(_jeu_mega(worth="$59.99")) is False


def test_mega_deal_refuse_les_dlc_et_contenus():
    assert offers.is_mega_deal(_jeu_mega(offer_type="dlc")) is False
    assert offers.is_mega_deal(_jeu_mega(offer_type="content")) is False


def test_mega_deal_exige_une_offre_temporaire_encore_en_cours():
    assert offers.is_mega_deal(_jeu_mega(end_date="")) is False
    hier = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    assert offers.is_mega_deal(_jeu_mega(end_date=hier)) is False


def test_mega_deal_desactivable_par_configuration(monkeypatch):
    import config

    monkeypatch.setattr(config, "MEGA_DEAL_MIN_WORTH_EUR", 0)
    assert offers.is_mega_deal(_jeu_mega()) is False

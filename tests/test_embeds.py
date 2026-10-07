"""Mise en forme des annonces (identité visuelle FreeGameDrop — voir DESIGN.md)."""

from datetime import datetime, timedelta, timezone

import discord
import pytest

from utils import branding, design, embeds

AUJOURDHUI = datetime.now(timezone.utc)

JEU = {
    "id": 42,
    "title": "Super Jeu Giveaway",
    "description": "  Un   très bon jeu   ",
    "platforms": "PC (Steam)",
    "worth": "19.99",
    "end_date": (AUJOURDHUI + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
    "thumbnail": "https://example.com/image.jpg",
    "open_giveaway_url": "https://example.com/jeu",
}


def _jeu_avec_fin(**overrides):
    jeu = dict(JEU)
    jeu.update(overrides)
    return jeu


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


# ---------- Hiérarchie de l'embed ----------


def test_annonce_complete_suit_la_hierarchie():
    embed, view = embeds.build_game_message(JEU)

    # 2️⃣ titre = nom du jeu (« Giveaway » retiré, emoji plateforme)
    assert embed.title == "🔵 Super Jeu"
    assert embed.url == JEU["open_giveaway_url"]
    # la marque, pas la plateforme, colore l'embed
    assert embed.color.value == design.rgb(design.PRIMARY)
    assert embed.description == "Un très bon jeu"
    # 3️⃣ prix, 4️⃣ plateforme (badge), 5️⃣ fin avec emoji d'urgence
    assert [f.name for f in embed.fields] == ["💰 Prix", "🎮 Plateforme", "⏰ Fin de l'offre"]
    assert [f.value for f in embed.fields] == [
        "~~19.99~~ ➜ **GRATUIT**",
        "🔵 Steam",
        embeds.format_time_remaining(JEU["end_date"]),
    ]
    assert embed.fields[2].value.startswith("🟢")  # +3 jours → normal
    # image en pleine largeur, branding discret en pied
    assert embed.image.url == JEU["thumbnail"]
    assert embed.footer.text == "🎁 FreeGameDrop · par Orvex · Source : GamerPower"
    # 1️⃣ badge d'auteur + 6️⃣ CTA principal
    assert embed.author.name == "🎁 JEU GRATUIT"
    assert len(view.children) == 1
    bouton = view.children[0]
    assert bouton.url == JEU["open_giveaway_url"]
    assert bouton.label == "Récupérer le jeu"
    # Discord ne colore pas les boutons-liens : le CTA principal est le seul bouton
    assert bouton.style is discord.ButtonStyle.link


def test_annonce_sans_lien_ni_image():
    embed, view = embeds.build_game_message({"title": "Jeu", "platforms": "itch.io"})

    assert embed.color.value == design.rgb(design.PRIMARY)  # couleur de marque par défaut
    assert embed.title == "🎁 Jeu"
    assert embed.fields[1].value == "itch.io"  # texte brut si plateforme inconnue
    assert view.children == []


def test_lien_de_repli_sur_gamerpower():
    embed, _ = embeds.build_game_message({"title": "Jeu", "gamerpower_url": "https://gp/1"})

    assert embed.url == "https://gp/1"


def test_panneau_des_roles_precise_la_lecture_seule():
    embed = embeds.build_roles_embed()

    assert "lecture seule" in embed.footer.text


# ---------- Niveaux d'urgence et variantes ----------


@pytest.mark.parametrize(
    "heures, niveau",
    [(-24, "ended"), (0.5, "critical"), (3, "urgent"), (12, "warning"), (48, "normal")],
)
def test_niveaux_durgence(heures, niveau):
    fin = (AUJOURDHUI + timedelta(hours=heures)).strftime("%Y-%m-%d %H:%M:%S")

    assert embeds.urgency_for(fin) == niveau


def test_urgence_inconnue_sans_date():
    assert embeds.urgency_for(None) == "unknown"
    assert embeds.format_time_remaining(None).startswith("⏳")


def test_variante_nouvelle_offre_par_defaut():
    assert embeds.offer_variant(JEU) == "new"
    assert embeds.offer_variant({"title": "Jeu"}) == "new"  # pas de date → nouvelle


def test_offre_urgente_est_signalee_dans_le_badge_et_le_champ():
    fin = (AUJOURDHUI + timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    embed, _ = embeds.build_game_message(_jeu_avec_fin(end_date=fin))

    assert embed.author.name == "🔥 SE TERMINE BIENTÔT"
    assert embed.color.value == design.rgb(design.PRIMARY)  # la marque reste la marque
    assert embed.fields[2].value.startswith("🟠")


def test_offre_critique_en_rouge():
    fin = (AUJOURDHUI + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    embed, _ = embeds.build_game_message(_jeu_avec_fin(end_date=fin))

    assert embed.author.name == "🔥 SE TERMINE BIENTÔT"
    assert embed.fields[2].value.startswith("🔴")


def test_offre_terminee_passe_en_gris_pour_lhistorique():
    fin = (AUJOURDHUI - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    embed, view = embeds.build_game_message(_jeu_avec_fin(end_date=fin))

    assert embed.author.name == "❌ OFFRE TERMINÉE"
    assert embed.color.value == design.rgb(design.ENDED)
    assert embed.fields[2].value.startswith("⚫")
    bouton = view.children[0]
    assert bouton.label == "Voir l'offre"  # libellé atténué pour l'historique
    assert bouton.url == JEU["open_giveaway_url"]


def test_offre_prolongee_se_force_explicitement():
    embed, _ = embeds.build_game_message(JEU, variant="extended")

    assert embed.author.name == "🔄 OFFRE PROLONGÉE"
    assert embed.color.value == design.rgb(design.PRIMARY)


def test_variante_inconnue_est_rejetee():
    with pytest.raises(ValueError):
        embeds.build_game_message(JEU, variant="noel")


def test_meme_squelette_quelle_que_soit_la_plateforme():
    for champ, emoji, nom in [
        ("PC (Steam)", "🔵", "Steam"),
        ("Epic Games Store", "⚪", "Epic Games Store"),
        ("GOG", "🟣", "GOG"),
        ("Ubisoft Connect", "🔷", "Ubisoft"),
    ]:
        embed, _ = embeds.build_game_message(_jeu_avec_fin(platforms=champ))

        assert embed.color.value == design.rgb(design.PRIMARY)  # jamais la couleur plateforme
        assert embed.fields[1].value == f"{emoji} {nom}"
        assert [f.name for f in embed.fields] == ["💰 Prix", "🎮 Plateforme", "⏰ Fin de l'offre"]


# ---------- Offres exceptionnelles, branding, invitation ----------


def _jeu_exceptionnel(**overrides):
    jeu = dict(
        JEU,
        worth="59,99 €",
        end_date=(AUJOURDHUI + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
    )
    jeu.update(overrides)
    return jeu


def test_annonce_standard_reste_sobre():
    embed, _ = embeds.build_game_message(JEU)  # « 19.99 » sans euros : pas exceptionnel

    assert embed.author.name == "🎁 JEU GRATUIT"
    assert embed.footer.text == "🎁 FreeGameDrop · par Orvex · Source : GamerPower"
    assert all("exceptionnelle" not in (f.name or "").lower() for f in embed.fields)


def test_annonce_exceptionnelle_est_mise_en_avant():
    embed, _ = embeds.build_game_message(_jeu_exceptionnel())

    assert embed.author.name == "🔥 OFFRE EXCEPTIONNELLE"
    assert any("🔥 Offre exceptionnelle" in (f.name or "") for f in embed.fields)
    assert "59.99 €" in " ".join(f.value for f in embed.fields)


def test_bouton_ajout_freegamedrop_reste_en_retrait():
    invite = branding.build_invite_url(999)
    embed, view = embeds.build_game_message(JEU, invite_url=invite)

    assert len(view.children) == 2
    principal, secondaire = view.children
    # le CTA principal arrive en premier, l'invitation en retrait
    assert principal.url == JEU["open_giveaway_url"]
    assert principal.label == "Récupérer le jeu"
    assert principal.emoji.name == "🎁"
    assert secondaire.url == invite
    assert secondaire.label == "Ajouter FreeGameDrop"
    assert secondaire.emoji.name == "➕"


def test_sans_lien_dinvitation_pas_de_bouton_en_plus():
    _, view = embeds.build_game_message(JEU)

    assert len(view.children) == 1  # seulement « Récupérer le jeu »


def test_panneau_des_roles_est_brande_freegamedrop():
    embed = embeds.build_roles_embed()

    assert "FreeGameDrop" in embed.title
    assert "FreeGameDrop" in embed.footer.text
    assert "Orvex" in embed.footer.text
    assert embed.color.value == design.rgb(design.PRIMARY)

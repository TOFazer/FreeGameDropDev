# 🎨 Identité visuelle — FreeGameDrop

> **ORVEX** (marque mère, discrète)
> &nbsp;&nbsp;&nbsp;&nbsp;└── **FREEGAMEDROP** (produit, marque forte)

Le but n'est pas de choisir de jolies couleurs : quand quelqu'un voit un embed, le
dashboard ou le site, il doit penser immédiatement « Ça, c'est FreeGameDrop ».
Orvex reste en retrait ; FreeGameDrop porte l'identité.

FreeGameDrop partage le même univers visuel que **OverX** et **OverLoad** : un style
**vert forêt, naturel, moderne et premium** — pas de dégradés flashy, de néons ni
d'effets gaming excessifs. Le logo FreeGameDrop (🎁) ne change pas : c'est tout ce
qui l'entoure qui évolue.

**FreeGameDrop en trois mots : Naturel — Moderne — Premium.**

Ces trois mots guident toutes les décisions graphiques. La source unique des valeurs
chiffrées est [`utils/design.py`](utils/design.py) (design tokens) ; ce document en est
la version lisible.

---

## 1. Couleurs

La palette « forêt » compte cinq couleurs de base, communes aux trois produits :

| Couleur | Valeur | Rôle |
|---|---|---|
| Vert forêt | `#173D2B` | couleur principale |
| Vert feuille | `#285B40` | boutons et actions |
| Vert sauge | `#91A889` | accents secondaires |
| Ivoire | `#F3F1E8` | fonds clairs |
| Graphite | `#242923` | texte et fonds sombres |

### 1.1 Couleur principale

| Rôle | Valeur |
|---|---|
| **Primary** | `#173D2B` (vert forêt) |

C'est la couleur que les gens associent à FreeGameDrop en une demi-seconde. Elle sert pour :

- filet (barre latérale) des embeds ;
- éléments importants et accents de marque du dashboard ;
- rôles et salons créés par le bot quand la plateforme est inconnue.

Variantes : hover `#1F4A32`, active `#102A1E`, fond discret (badges actifs) `#1E352A`.

### 1.2 Couleur d'action

| Rôle | Valeur |
|---|---|
| **Action** | `#285B40` (vert feuille) |

Le vert feuille porte les appels à l'action : boutons principaux (« 🎁 Récupérer le
jeu ») et badge « GRATUIT ». Variantes : hover `#336C4E`, active `#1F4A32`.

### 1.3 Couleur secondaire

| Rôle | Valeur |
|---|---|
| **Secondary** | `#91A889` (vert sauge) |

Elle complète la principale sans lui voler la vedette : statistiques, catégories,
illustrations, hover, petits détails, badge « NOUVEAU », liens sur fond sombre.

### 1.4 Couleurs neutres (thème sombre graphite)

Jamais de `#000000` pur : un dashboard entièrement noir paraît amateur.

| Token | Valeur | Usage |
|---|---|---|
| Background | `#1A1E1A` | fond de page (graphite assombri, le plus sombre) |
| Surface | `#242923` | graphite — header, barres |
| Card | `#2C322C` | cartes (légèrement plus clair) |
| Text | `#F3F1E8` | ivoire |
| Secondary text | `#A3AEA0` | sauge grisé |
| Border | `#3A423A` | séparateurs |

Le thème clair correspondant (interfaces lumineuses, type site OverX) inverse la
paire : fond ivoire `#F3F1E8`, texte graphite `#242923`.

### 1.5 Couleurs des plateformes

FreeGameDrop garde **sa** couleur. Les plateformes gardent une couleur reconnaissable,
utilisée uniquement dans de petits badges, icônes, labels et filtres — **jamais** en
embed entièrement coloré.

| Plateforme | Valeur | Exemple d'usage |
|---|---|---|
| FreeGameDrop | `#173D2B` | marque (filet d'embed) ; actions et badge GRATUIT en vert feuille `#285B40` |
| Steam | `#66C0F4` | badge, rôle, filtre |
| Epic Games | `#D9D9D9` | badge, rôle, filtre (marque noir/blanc) |
| GOG | `#86328B` | badge, rôle, filtre (violet propre à GOG) |
| Ubisoft | `#0070FF` | badge, rôle, filtre |

### 1.6 Sémantique et urgence

| Niveau | Couleur | Emoji | Quand |
|---|---|---|---|
| Normal | `#7FAE6E` | 🟢 | plus de 24 h restantes |
| Attention | `#E0C169` | 🟡 | moins de 24 h |
| Urgent | `#DE8B4D` | 🟠 | moins de 6 h |
| Se termine | `#D96A5B` | 🔴 | moins d'1 h |
| Terminée | `#7A827B` | ⚫ | offre expirée |
| Bouton danger | `#C14B42` | — | supprimer, désactiver, réinitialiser |

---

## 2. Typographie

Une seule famille : **Inter** (avec repli système). Ce qui compte : lisibilité, poids,
taille, espacement, hiérarchie.

| Style | Taille | Poids | Usage |
|---|---|---|---|
| H1 | 28 px | 800 | très visible |
| H2 | 22 px | 700 | important |
| H3 | 17 px | 600 | sous-titre de carte |
| Body | 15 px | 400 | lecture courante (interligne 1,55) |
| Small | 13 px | 400 | informations secondaires |
| Button | 14 px | 600 | boutons |
| Caption | 12 px | 500 | légendes, pied de page |

---

## 3. Boutons

Un seul langage visuel partout. Rayon **10 px**, hauteur **40 px**, padding horizontal
**18 px**, texte 14 px / 600.

| Bouton | Fond | Texte | Hover | Usage |
|---|---|---|---|---|
| **Principal** | `#285B40` (vert feuille) | ivoire `#F3F1E8` | `#336C4E` | une seule action principale par surface (ex. « 🎁 Récupérer le jeu ») |
| **Secondaire** | `#2C322C` | `#F3F1E8` | `#343B34` | action complémentaire (ex. « ➕ Ajouter FreeGameDrop ») |
| **Danger** | `#C14B42` | ivoire | `#A93E36` | supprimer, désactiver, réinitialiser |
| **Désactivé** | `#242923` | `#A3AEA0` | — | `cursor: not-allowed` |

Sur Discord, les boutons-liens (URL) ne sont pas colorables : discord.py leur applique
toujours le style « link ». La hiérarchie « principal / secondaire » passe alors par
l'ordre, le libellé et l'emoji : « 🎁 Récupérer le jeu » en premier, « ➕ Ajouter
FreeGameDrop » en retrait — jamais l'inverse. L'identité de la marque est portée par le
filet vert forêt de l'embed, pas par les boutons.

---

## 4. Images

Les jeux ont des visuels très différents (réaliste, illustration, personnage) : on ne
contrôle pas l'original, on contrôle **la manière de l'afficher**.

- **Ratio** : 16/9 partout (vignettes du dashboard : `aspect-ratio: 16/9`).
- **Recadrage** : `object-fit: cover` — jamais de déformation.
- **Coins** : arrondis 12 px.
- **Fond** : `surface` (`#242923`) pendant le chargement.
- **Embeds** : image pleine largeur (`set_image`), même emplacement pour toutes les
  offres — jamais une image énorme, jamais une minuscule.

---

## 5. Badges

Chaque badge a une fonction précise. **Maximum quelques badges** par surface —
pas de sapin de Noël.

| Badge | Couleur | Fonction |
|---|---|---|
| `GRATUIT` | action `#285B40` | le plus important : l'offre est gratuite |
| `🔵 Steam` / `⚪ Epic Games Store` / `🟣 GOG` / `🔷 Ubisoft` | couleur de la plateforme | savoir immédiatement où récupérer le jeu |
| `NOUVEAU` | secondaire `#91A889` | nouvelle offre |
| `SE TERMINE BIENTÔT` | urgence `#DE8B4D` | attirer l'attention (< 6 h) |
| `EXPIRÉ` | neutre `#7A827B` | historique |

---

## 6. Embeds Discord

L'embed est une mini publicité pour le produit — utile, lisible en 2–3 secondes,
testée sur mobile.

### 6.1 Hiérarchie de l'information

1. **Quoi** — badge d'auteur : `🎁 JEU GRATUIT`
2. **Quel jeu** — titre : le nom du jeu, rien d'autre
3. **Pourquoi** — `Prix` : `~~59,99 €~~ ➜ **GRATUIT**`
4. **Où** — `Plateforme` : badge `⚪ Epic Games Store`
5. **Jusqu'à quand** — `Fin de l'offre` : `🟡 <t:…:R>` + date complète
6. **Action** — `[🎁 Récupérer le jeu]` (principal) + `[➕ Ajouter FreeGameDrop]` (secondaire)

Prix, plateforme et expiration sont regroupés sur une même ligne de champs, avec
des libellés sobres sans emoji décoratif : le signal est porté par les valeurs.
Pour une offre qui n'est pas un jeu complet (DLC, extension, contenu), deux champs
s'ajoutent dans le même langage sobre : `Type` et `Gratuité` — « ♾️ Gratuit en
permanence », « ⏳ Offert temporairement » ou « ❔ Durée non communiquée » quand la
source ne permet pas de conclure. Aucune icône supplémentaire n'est inventée.
L'image du jeu est la partie visuelle forte (pleine largeur, en bas de l'embed).
La description, si elle existe, reste courte et secondaire. Le branding
(`🎁 FreeGameDrop · par Orvex · Source : …`) tient dans le pied de page — discret,
jamais plus important que le jeu.

Le bouton envoie **directement** vers la page officielle de récupération du jeu.

### 6.2 Maquettes — un seul design, quatre plateformes

Même squelette partout ; seul le badge plateforme change.

```
┌─ filet vert forêt #173D2B ─────────────────────────┐
│ 🎁 JEU GRATUIT                          (auteur)   │
│                                                    │
│ 🔵 Super Jeu                            (titre)    │
│ Un très bon jeu.                        (description, courte)
│                                                    │
│ Prix         Plateforme      Fin de l'offre        │
│ ~~19.99~~ ➜   🔵 Steam       🟢 Dans 3 jours       │
│   **GRATUIT**                  08/10 à 23:59       │
│                                                    │
│ ┌──────────────────────────────────────────────┐   │
│ │              IMAGE DU JEU (16:9)             │   │
│ └──────────────────────────────────────────────┘   │
│                                                    │
│ 🎁 FreeGameDrop · par Orvex · Source : GamerPower  │
│                                                    │
│ [🎁 Récupérer le jeu]  [➕ Ajouter FreeGameDrop]    │
└────────────────────────────────────────────────────┘
        Steam ↑ — identique pour Epic (⚪), GOG (🟣), Ubisoft (🔷)
```

### 6.3 Variantes

| Variante | Badge d'auteur | Filet | Usage |
|---|---|---|---|
| Nouvelle offre | `🎁 JEU GRATUIT` | vert forêt | annonce standard |
| Offre bientôt terminée | `⏳ SE TERMINE BIENTÔT` | vert forêt | < 6 h restantes (détection auto) |
| Offre prolongée | `🔄 OFFRE PROLONGÉE` | vert forêt | prolongation (passée explicitement) |
| Offre terminée | `❌ OFFRE TERMINÉE` | gris `#7A827B` | historique |

Une offre « exceptionnelle » (jeu complet de grande valeur) reçoit une mise en
évidence spéciale mais sobre : le bandeau `⭐ OFFRE EXCEPTIONNELLE` avec le
détail chiffré.

---

## 7. Où c'est implémenté

| Élément | Fichier |
|---|---|
| Design tokens (couleurs, typo, boutons, images, badges, urgence) | `utils/design.py` |
| Couleurs des plateformes et couleur par défaut | `config.py` |
| Embeds (hiérarchie, variantes, boutons, badges) | `utils/embeds.py` |
| Embeds `/info`, `/stats` | `cogs/setup.py` |
| Dashboard web (thème sombre, Inter, boutons, vignettes 16:9, badges) | `web/dashboard.py` |
| Tests | `tests/test_design.py`, `tests/test_embeds.py` |

## 8. Checklist

- [x] Couleur principale définie et utilisée partout (boutons, liens, embeds, dashboard)
- [x] Couleur secondaire définie (stats, catégories, détails)
- [x] Neutres définis (thème sombre graphite, pas de noir pur)
- [x] Couleurs plateformes séparées de la marque (badges uniquement)
- [x] Police unique (Inter) + échelle H1/H2/H3/Body/Small/Button/Caption
- [x] Style des boutons (primaire/secondaire/danger/désactivé : rayon, hauteur, hover)
- [x] Style des images (16:9, coins 12 px, cover, fond surface)
- [x] Système de badges (GRATUIT, plateforme, NOUVEAU, SE TERMINE BIENTÔT, EXPIRÉ)
- [x] Trois mots de marque (Naturel — Moderne — Premium)
- [x] Palette « forêt » partagée avec OverX et OverLoad (même univers visuel)
- [x] Hiérarchie d'embed : quoi → jeu → prix → plateforme → échéance → action
- [x] Image cohérente, titre clair (nom du jeu), prix évident
- [x] Plateforme et expiration visibles avec niveaux d'urgence 🟢🟡🟠🔴
- [x] CTA principal « 🎁 Récupérer le jeu » vers la page officielle
- [x] Bouton secondaire « ➕ Ajouter FreeGameDrop »
- [x] Branding discret en pied d'embed (`FreeGameDrop · par Orvex`)
- [x] Variantes : nouvelle offre / bientôt terminée / prolongée / terminée
- [x] Même design testé pour Steam, Epic, GOG, Ubisoft (un seul squelette)
- [x] Lisible sur mobile : l'offre se comprend sans chercher le lien

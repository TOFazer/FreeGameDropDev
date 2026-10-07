# 🎨 Identité visuelle — FreeGameDrop

> **ORVEX** (marque mère, discrète)
> &nbsp;&nbsp;&nbsp;&nbsp;└── **FREEGAMEDROP** (produit, marque forte)

Le but n'est pas de choisir de jolies couleurs : quand quelqu'un voit un embed, le
dashboard ou le site, il doit penser immédiatement « Ça, c'est FreeGameDrop ».
Orvex reste en retrait ; FreeGameDrop porte l'identité.

**FreeGameDrop en trois mots : Gaming — Moderne — Premium.**

Ces trois mots guident toutes les décisions graphiques. La source unique des valeurs
chiffrées est [`utils/design.py`](utils/design.py) (design tokens) ; ce document en est
la version lisible.

---

## 1. Couleurs

### 1.1 Couleur principale

| Rôle | Valeur |
|---|---|
| **Primary** | `#7C3AED` (violet) |

C'est la couleur que les gens associent à FreeGameDrop en une demi-seconde. Elle sert pour :

- boutons principaux ;
- liens ;
- éléments importants et accents du dashboard ;
- filet (barre latérale) des embeds ;
- badges « GRATUIT » ;
- rôles et salons créés par le bot quand la plateforme est inconnue.

Variantes : hover `#8B5CF6`, active `#6D28D9`, fond discret (badges actifs) `#2A2140`.

### 1.2 Couleur secondaire

| Rôle | Valeur |
|---|---|
| **Secondary** | `#22D3EE` (cyan) |

Elle complète la principale sans lui voler la vedette : statistiques, catégories,
illustrations, hover, petits détails, badge « NOUVEAU ».

### 1.3 Couleurs neutres (thème sombre)

Jamais de `#000000` pur : un dashboard entièrement noir paraît amateur.

| Token | Valeur | Usage |
|---|---|---|
| Background | `#0B0E14` | fond de page (le plus sombre) |
| Surface | `#121622` | header, barres |
| Card | `#1A1F2E` | cartes (légèrement plus clair) |
| Text | `#F2F4F8` | blanc cassé |
| Secondary text | `#9AA3B5` | gris |
| Border | `#272E42` | séparateurs |

### 1.4 Couleurs des plateformes

FreeGameDrop garde **sa** couleur. Les plateformes gardent une couleur reconnaissable,
utilisée uniquement dans de petits badges, icônes, labels et filtres — **jamais** en
embed entièrement coloré.

| Plateforme | Valeur | Exemple d'usage |
|---|---|---|
| FreeGameDrop | `#7C3AED` | marque (filet d'embed, boutons, badges GRATUIT) |
| Steam | `#66C0F4` | badge, rôle, filtre |
| Epic Games | `#D9D9D9` | badge, rôle, filtre (marque noir/blanc) |
| GOG | `#86328B` | badge, rôle, filtre (violet propre à GOG, distinct du violet marque) |
| Ubisoft | `#0070FF` | badge, rôle, filtre |

### 1.5 Sémantique et urgence

| Niveau | Couleur | Emoji | Quand |
|---|---|---|---|
| Normal | `#4ADE80` | 🟢 | plus de 24 h restantes |
| Attention | `#FACC15` | 🟡 | moins de 24 h |
| Urgent | `#FB923C` | 🟠 | moins de 6 h |
| Se termine | `#F87171` | 🔴 | moins d'1 h |
| Terminée | `#6B7280` | ⚫ | offre expirée |
| Bouton danger | `#E5484D` | — | supprimer, désactiver, réinitialiser |

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
| **Principal** | `#7C3AED` | blanc | `#8B5CF6` | une seule action principale par surface (ex. « 🎁 Récupérer le jeu ») |
| **Secondaire** | `#232A3D` | `#F2F4F8` | `#2A3149` | action complémentaire (ex. « ➕ Ajouter FreeGameDrop ») |
| **Danger** | `#E5484D` | blanc | `#C73E43` | supprimer, désactiver, réinitialiser |
| **Désactivé** | `#121622` | `#9AA3B5` | — | `cursor: not-allowed` |

Sur Discord, les boutons-liens (URL) ne sont pas colorables : discord.py leur applique
toujours le style « link ». La hiérarchie « principal / secondaire » passe alors par
l'ordre, le libellé et l'emoji : « 🎁 Récupérer le jeu » en premier, « ➕ Ajouter
FreeGameDrop » en retrait — jamais l'inverse. L'identité de la marque est portée par le
filet violet de l'embed, pas par les boutons.

---

## 4. Images

Les jeux ont des visuels très différents (réaliste, illustration, personnage) : on ne
contrôle pas l'original, on contrôle **la manière de l'afficher**.

- **Ratio** : 16/9 partout (vignettes du dashboard : `aspect-ratio: 16/9`).
- **Recadrage** : `object-fit: cover` — jamais de déformation.
- **Coins** : arrondis 12 px.
- **Fond** : `surface` (`#121622`) pendant le chargement.
- **Embeds** : image pleine largeur (`set_image`), même emplacement pour toutes les
  offres — jamais une image énorme, jamais une minuscule.

---

## 5. Badges

Chaque badge a une fonction précise. **Maximum quelques badges** par surface —
pas de sapin de Noël.

| Badge | Couleur | Fonction |
|---|---|---|
| `GRATUIT` | primaire `#7C3AED` | le plus important : l'offre est gratuite |
| `🔵 Steam` / `⚪ Epic Games Store` / `🟣 GOG` / `🔷 Ubisoft` | couleur de la plateforme | savoir immédiatement où récupérer le jeu |
| `NOUVEAU` | secondaire `#22D3EE` | nouvelle offre |
| `SE TERMINE BIENTÔT` | urgence `#FB923C` | attirer l'attention (< 6 h) |
| `EXPIRÉ` | neutre `#6B7280` | historique |

---

## 6. Embeds Discord

L'embed est une mini publicité pour le produit — utile, lisible en 2–3 secondes,
testée sur mobile.

### 6.1 Hiérarchie de l'information

1. **Quoi** — badge d'auteur : `🎁 JEU GRATUIT`
2. **Quel jeu** — titre : le nom du jeu, rien d'autre
3. **Pourquoi** — `💰 Prix` : `~~59,99 €~~ ➜ **GRATUIT**`
4. **Où** — `🎮 Plateforme` : badge `🎮 Epic Games Store`
5. **Jusqu'à quand** — `⏰ Fin de l'offre` : `🟡 <t:…:R>` + date complète
6. **Action** — `[🎁 Récupérer le jeu]` (principal) + `[➕ Ajouter FreeGameDrop]` (secondaire)

L'image du jeu est la partie visuelle forte (pleine largeur, en bas de l'embed).
La description, si elle existe, reste courte et secondaire. Le branding
(`🎁 FreeGameDrop · par Orvex · Source : …`) tient dans le pied de page — discret,
jamais plus important que le jeu.

Le bouton envoie **directement** vers la page officielle de récupération du jeu.

### 6.2 Maquettes — un seul design, quatre plateformes

Même squelette partout ; seul le badge plateforme change.

```
┌─ filet violet #7C3AED ─────────────────────────────┐
│ 🎁 JEU GRATUIT                          (auteur)   │
│                                                    │
│ 🔵 Super Jeu                            (titre)    │
│ Un très bon jeu.                        (description, courte)
│                                                    │
│ 💰 Prix      🎮 Plateforme   ⏰ Fin de l'offre     │
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
| Nouvelle offre | `🎁 JEU GRATUIT` | violet | annonce standard |
| Offre bientôt terminée | `🔥 SE TERMINE BIENTÔT` | violet | < 6 h restantes (détection auto) |
| Offre prolongée | `🔄 OFFRE PROLONGÉE` | violet | prolongation (passée explicitement) |
| Offre terminée | `❌ OFFRE TERMINÉE` | gris `#6B7280` | historique |

Une offre « exceptionnelle » (jeu complet de grande valeur) garde le bandeau
`🔥 OFFRE EXCEPTIONNELLE` avec le détail chiffré.

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
- [x] Neutres définis (thème sombre, pas de noir pur)
- [x] Couleurs plateformes séparées de la marque (badges uniquement)
- [x] Police unique (Inter) + échelle H1/H2/H3/Body/Small/Button/Caption
- [x] Style des boutons (primaire/secondaire/danger/désactivé : rayon, hauteur, hover)
- [x] Style des images (16:9, coins 12 px, cover, fond surface)
- [x] Système de badges (GRATUIT, plateforme, NOUVEAU, SE TERMINE BIENTÔT, EXPIRÉ)
- [x] Trois mots de marque (Gaming — Moderne — Premium)
- [x] Hiérarchie d'embed : quoi → jeu → prix → plateforme → échéance → action
- [x] Image cohérente, titre clair (nom du jeu), prix évident
- [x] Plateforme et expiration visibles avec niveaux d'urgence 🟢🟡🟠🔴
- [x] CTA principal « 🎁 Récupérer le jeu » vers la page officielle
- [x] Bouton secondaire « ➕ Ajouter FreeGameDrop »
- [x] Branding discret en pied d'embed (`FreeGameDrop · par Orvex`)
- [x] Variantes : nouvelle offre / bientôt terminée / prolongée / terminée
- [x] Même design testé pour Steam, Epic, GOG, Ubisoft (un seul squelette)
- [x] Lisible sur mobile : l'offre se comprend sans chercher le lien

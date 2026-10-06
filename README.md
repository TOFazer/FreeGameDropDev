# 🎮 FreeGameDrop

Bot Discord qui annonce automatiquement les **jeux gratuits** (Steam, Epic Games Store, GOG,
Ubisoft) dans des salons dédiés, et laisse chaque membre choisir les alertes qu'il veut recevoir
en cliquant sur un bouton.

Les offres viennent de plusieurs sources agrégées (API publique
[GamerPower](https://www.gamerpower.com/api-read) et l'API officielle de l'
[Epic Games Store](https://store.epicgames.com/)) : si une source est en panne ou trop lente, les
autres continuent de fonctionner normalement.

---

## Sommaire

- [Ce que fait le bot](#ce-que-fait-le-bot)
- [Installation](#installation)
- [Inviter le bot sur un serveur](#inviter-le-bot-sur-un-serveur)
- [Lancer le bot](#lancer-le-bot)
- [Commandes](#commandes)
- [Données et confidentialité](#données-et-confidentialité)
- [Fonctionnement](#fonctionnement)
- [Tableau de bord web](#tableau-de-bord-web)
- [Feuille de route](#feuille-de-route)
- [Configuration](#configuration)
- [Structure du projet](#structure-du-projet)
- [Développement et tests](#développement-et-tests)
- [Dépannage](#dépannage)

---

## Ce que fait le bot

`/setup-auto` construit tout en une fois :

```
🎮 Jeux gratuits                  ← catégorie
 ├── #choisir-ses-roles           ← panneau à boutons, LECTURE SEULE
 ├── #jeux-steam                  ← visible seulement avec le rôle 🔵 Steam
 ├── #jeux-epic                   ← visible seulement avec le rôle ⚪ Epic Games Store
 └── …
```

- **Un rôle + un salon par plateforme.** Le salon est invisible tant qu'on n'a pas le rôle.
- **Auto-attribution des rôles** : un clic sur un bouton donne (ou retire) le rôle.
- **Salons en lecture seule** : voir, lire et cliquer, rien d'autre. Ni messages, ni réactions,
  ni fils, ni sondages — pour personne.
- **Accès réglable** : `#choisir-ses-roles` est ouvert à tous par défaut, ou réservé aux rôles
  de ton choix (`/acces-salon-roles`).
- **Vérification automatique** toutes les heures, avec mention du rôle concerné, prix barré,
  compte à rebours de fin d'offre et bouton « Récupérer le jeu ».
- **Jamais deux fois le même jeu** : les annonces déjà envoyées sont mémorisées.
- **Catalogue privé des offres** avec `/free` : navigation page par page, filtres (plateforme, type
  d'offre, échéance) et lien pour récupérer le jeu.
- **Favoris personnels** : bouton ❤️, commande `/favoris` et commande `/mes-donnees` pour effacer ses favoris.
- **Historique et recherche** : `/historique` revoit les dernières offres connues, `/recherche`
  retrouve une offre par mot-clé.
- **Préférences et alertes personnelles** : `/preferences` filtre les types d'offres, le prix
  minimum et les genres ; `/alertes` active des messages privés pour les nouvelles offres
  correspondantes ou pour un favori qui se termine bientôt.
- **Rappels serveur** : `/rappel-salon` choisit un salon qui reçoit un message le jour où une
  offre suivie se termine.
- **Tableau de bord web optionnel** avec connexion Discord (OAuth2) et statistiques publiques
  (voir [Tableau de bord web](#tableau-de-bord-web)).

> ℹ️ Les administrateurs passent outre **toutes** les permissions de salon : Discord ne permet
> pas de les empêcher d'écrire. Le bot supprime donc automatiquement tout message posté dans
> `#choisir-ses-roles`, y compris le leur (il lui faut « Gérer les messages » pour ça).

---

## Installation

Prérequis : **Python 3.10 ou plus**.

```bash
git clone https://github.com/TOFazer/release-bot-FreeGameDrop.git
cd release-bot-FreeGameDrop

python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env             # puis ouvre .env et colle ton token
```

Créer le bot et récupérer le token : <https://discord.com/developers/applications>
→ **New Application** → onglet **Bot** → **Reset Token** → copier dans `.env`.

Aucun *intent privilégié* n'est nécessaire.

---

## Inviter le bot sur un serveur

Onglet **OAuth2 → URL Generator** : scopes `bot` + `applications.commands`, puis ces permissions :

| Permission | À quoi elle sert |
| --- | --- |
| Gérer les salons | créer la catégorie et les salons |
| Gérer les rôles | créer les rôles de plateforme et les distribuer |
| Voir les salons / Lire l'historique | accéder à ses propres salons |
| Envoyer des messages / Liens intégrés | poster les annonces |
| Gérer les messages | effacer ce qui est écrit dans `#choisir-ses-roles` |

Lien tout prêt (remplace `CLIENT_ID` par l'identifiant de ton application) :

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=268528656&scope=bot%20applications.commands
```

> Le **rôle du bot doit être placé au-dessus** des rôles de plateforme dans les paramètres du
> serveur, sinon Discord l'empêche de les attribuer.

---

## Lancer le bot

```bash
python main.py
```

Puis, sur le serveur Discord : `/setup-auto`.

---

## Commandes

Les commandes de configuration sont réservées aux administrateurs. Les commandes publiques et personnelles répondent en privé lorsque c'est pertinent.

| Commande | Accès | Effet |
| --- | --- | --- |
| `/setup-auto` | Admin | Choisit les plateformes et qui voit `#choisir-ses-roles`, puis crée/met à jour catégorie, rôles, salons et panneau de boutons. Rejouable sans rien dupliquer. |
| `/config` | Admin | Rouvre le même panneau de configuration que `/setup-auto`. |
| `/acces-salon-roles` | Admin | Change les rôles autorisés à voir `#choisir-ses-roles` (menu vide = tout le monde). Le salon reste en lecture seule. |
| `/test-jeux` | Admin | Force une vérification immédiate des jeux gratuits. |
| `/reset-jeux` | Admin | Vide l'historique des envois : les jeux récents peuvent être réannoncés. |
| `/reset-all` | Admin | Supprime tout ce que le bot a créé (salons, rôles, catégorie, messages). Demande confirmation. |
| `/free` | Tout le monde | Parcourt les offres agrégées (GamerPower, Epic Games Store, …), avec filtres optionnels par plateforme, type d'offre et échéance. La réponse est éphémère ; les boutons permettent de parcourir et d'enregistrer un favori. Limite d'une requête par utilisateur toutes les 15 secondes. |
| `/favoris` | Tout le monde | Affiche ses favoris en privé ; le bouton permet de retirer une offre. |
| `/historique` | Tout le monde | Revoit les dernières offres connues du bot, avec les mêmes filtres que `/free`. |
| `/recherche` | Tout le monde | Recherche une offre déjà connue par titre ou description. |
| `/preferences` | Tout le monde | Personnalise les types d'offres, le prix minimum (en euros) et les genres pris en compte par `/free` et les alertes personnelles. |
| `/alertes` | Tout le monde | Active ou désactive une alerte par message privé (« nouvelle offre » ou « favori qui se termine bientôt »). |
| `/mes-donnees` | Tout le monde | Demande confirmation puis supprime les favoris associés au compte Discord. |
| `/rappel-salon` | Admin | Choisit le salon qui reçoit un rappel pour les offres qui se terminent le jour même. |
| `/dev-stats` | Développeur du bot | Statistiques internes (serveurs, offres suivies, favoris) ; réservé au propriétaire de l'application Discord. |
| `/ping` | Tout le monde | Vérifie que le bot répond et affiche sa latence. |
| `/info` | Tout le monde | Affiche la latence, le nombre de serveurs et les liens utiles. |

---

## Données et confidentialité

Le bot utilise SQLite (`DB_PATH`) et conserve :

- la configuration technique des serveurs (identifiants de salons et rôles) et les identifiants d'offres déjà annoncées, pour éviter les doublons ;
- les champs publics d'une offre (identifiant, titre, plateforme, source, type, valeur, liens, description, genres et dates) ;
- pour les favoris, l'identifiant Discord du membre, l'identifiant de l'offre et la date d'ajout ;
- pour les préférences et alertes personnelles (`/preferences`, `/alertes`), les réglages choisis, liés uniquement à l'identifiant Discord du membre ;
- un historique minimal des alertes déjà envoyées (membre, offre, type d'alerte) pour éviter les doublons et respecter un délai minimal entre deux alertes identiques ;
- si le tableau de bord web est activé, une session de connexion temporaire (identifiant Discord, pseudo, expiration) créée après une connexion OAuth2 réussie.

Le bot ne stocke pas les messages privés, les messages des membres ni la preuve qu'un jeu a été réclamé. Les réponses de `/free`, `/favoris`, `/historique` et `/recherche` sont éphémères. Les offres publiques non favorites sont supprimées du catalogue après 90 jours sans nouvelle observation ; celles gardées en favori restent jusqu'au retrait du favori ou à la suppression des données.

Pour supprimer les favoris liés à ton compte, utilise `/mes-donnees` et confirme. Cette action ne supprime pas les réglages du serveur, les préférences/alertes personnelles, ni les informations publiques d'une offre qui serait encore en favori par quelqu'un d'autre.

---

## Fonctionnement

```
                 toutes les heures
                        │
      services/gamerpower.py ──► API GamerPower
                        │
                 utils/platforms.py   « PC (Steam) » → steam
                        │
                   database.py        déjà annoncé ? sinon, on enregistre
                        │
                  utils/embeds.py     construction du message
                        │
                  #jeux-steam         @🔵 Steam nouveau jeu gratuit !
```

Côté permissions, la règle est simple : **les salons du bot se lisent, ils ne s'écrivent pas.**
Deux subtilités Discord sont gérées dans `utils/permissions.py` :

1. un bot ne peut pas accorder ni refuser une permission qu'il ne possède pas lui-même — chaque
   réglage est donc filtré par ce que le bot a réellement ;
2. les administrateurs ignorent les permissions de salon — leurs messages sont donc supprimés
   par le bot.

---

## Tableau de bord web

Un petit serveur web optionnel (basé sur `aiohttp.web`, déjà dans les dépendances du bot — aucun
paquet supplémentaire requis) expose des statistiques publiques et une connexion Discord :

- `GET /` : page d'accueil avec les statistiques globales (serveurs, offres suivies, favoris...) et
  un bouton de connexion Discord (OAuth2, scope `identify` uniquement).
- `GET /api/stats` : les mêmes statistiques en JSON.
- `GET /login`, `GET /auth/callback`, `GET /logout` : parcours de connexion/déconnexion.

Pour l'activer :

1. Crée une application sur <https://discord.com/developers/applications>, onglet **OAuth2**,
   et ajoute une redirection `http://localhost:8080/auth/callback` (ou ton domaine).
2. Renseigne dans `.env` : `DASHBOARD_ENABLED=true`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`,
   et au besoin `DASHBOARD_PORT` / `DASHBOARD_BASE_URL` / `DISCORD_OAUTH_REDIRECT_URI`.
3. Lance le bot normalement (`python main.py`) : le tableau de bord démarre avec lui, sur
   `DASHBOARD_HOST:DASHBOARD_PORT`.

Le tableau de bord ne stocke aucune donnée de jeu séparée : il lit la même base SQLite que le bot.

**Sécurité des sessions.** Le cookie de session (`HttpOnly`, `SameSite=Lax`) reçoit aussi
l'attribut `Secure` dès que `DASHBOARD_BASE_URL` commence par `https://` — donc automatiquement en
production normale, sans rien à faire. Si tu places un reverse proxy qui termine le TLS devant le
bot (le serveur interne reste alors en HTTP), force quand même `DASHBOARD_COOKIE_SECURE=true`.
Ne mets jamais `DASHBOARD_COOKIE_SECURE=false` sur un tableau de bord exposé publiquement.

---

## Feuille de route

Les prochaines fonctionnalités sont planifiées par étapes dans [`ROADMAP.md`](ROADMAP.md). Les notes, genres, joueurs et réclamations ne sont pas inventés : ils seront affichés uniquement si une source fiable les fournit ou si l'utilisateur les déclare explicitement.

---

## Configuration

Tout est dans `config.py`, surchargeable par le fichier `.env` (voir `.env.example`) :

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `DISCORD_TOKEN` | — | **Obligatoire.** Token du bot. |
| `DB_PATH` | `bot.db` | Fichier SQLite. |
| `CHECK_INTERVAL_HOURS` | `1` | Fréquence de vérification. |
| `MAX_GAMES` | `10` | Jeux récents examinés à chaque tour. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `PROJECT_URL` | dépôt GitHub | Lien du projet affiché par `/info`. |
| `SUPPORT_URL` | page Issues GitHub | Lien de support affiché par `/info`. |
| `VOTE_URL` | *(vide)* | Lien de vote affiché par `/info`, si le bot est référencé sur un annuaire. |
| `CATEGORY_NAME` | `🎮 Jeux gratuits` | Nom de la catégorie créée. |
| `ROLES_CHANNEL` | `choisir-ses-roles` | Nom du salon de choix des rôles. |
| `TEST_GUILD_ID` | *(serveur de test)* | Serveur dont on purge les anciennes commandes au démarrage ; `0` pour désactiver. |
| `GAMERPOWER_API_URL` | API GamerPower | Source des jeux. |
| `GAMERPOWER_TIMEOUT` | `15` | Délai d'attente réseau, en secondes. |
| `EPIC_API_URL` | API Epic Games Store | Source des jeux offerts chaque semaine. |
| `EPIC_TIMEOUT` | `15` | Délai d'attente réseau, en secondes. |
| `EPIC_LOCALE` / `EPIC_COUNTRY` | `fr-FR` / `FR` | Langue et pays utilisés pour interroger l'Epic Games Store. |
| `OFFER_SOURCES` | `gamerpower,epic` | Sources activées pour `/free`, les alertes et la veille automatique. |
| `OFFER_SOURCE_TIMEOUT` | `20` | Délai maximal accordé à chaque source avant de l'ignorer pour ce tour. |
| `DEFAULT_TIMEZONE` | `Europe/Paris` | Fuseau horaire par défaut des filtres de date de `/free`. |
| `ALERT_CADENCE_HOURS` | `1` | Délai minimal entre deux alertes DM identiques pour un même membre. |
| `LAST_DAY_HOURS` | `24` | Fenêtre considérée comme « se termine bientôt ». |
| `DASHBOARD_ENABLED` | `false` | Démarre le tableau de bord web avec le bot. |
| `DASHBOARD_HOST` / `DASHBOARD_PORT` | `0.0.0.0` / `8080` | Adresse d'écoute du tableau de bord. |
| `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` | — | Identifiants OAuth2 de l'application Discord, nécessaires pour la connexion sur le tableau de bord. |
| `DISCORD_OAUTH_REDIRECT_URI` | `DASHBOARD_BASE_URL/auth/callback` | URL de redirection OAuth2, doit correspondre à celle déclarée sur Discord. |
| `DASHBOARD_COOKIE_SECURE` | auto (`true` si `DASHBOARD_BASE_URL` est en `https://`) | Ajoute l'attribut `Secure` aux cookies de session. À laisser activé dès que le tableau de bord est exposé publiquement en HTTPS. |

**Ajouter une plateforme** (exemple : Amazon Prime Gaming) — une seule ligne dans `config.py` :

```python
Platform("prime", "Prime Gaming", ("prime gaming",), "🟠", 0xFF9900),
```

Les mots-clés sont cherchés en minuscules dans le champ `platforms` renvoyé par l'API.

---

## Structure du projet

```
main.py                 point d'entrée : démarre le bot, les cogs et le tableau de bord optionnel
config.py               toute la configuration (.env, plateformes, sources, alertes, dashboard)
database.py             stockage SQLite (configuration, annonces, catalogue, favoris, alertes, sessions)
cogs/
  jeux.py               commandes, menus, navigation des offres, boucle de vérification
  setup.py              /ping et /info
ROADMAP.md              feuille de route des prochaines versions
services/
  gamerpower.py         appel à l'API GamerPower (et rien d'autre)
  epic_games.py          appel à l'API de l'Epic Games Store (et rien d'autre)
  offer_engine.py        agrège les sources, tolère les pannes, dédoublonne
utils/
  platforms.py          reconnaître la plateforme d'un jeu
  offers.py             filtres de catalogue (type, prix, genres, échéances)
  embeds.py             construire les messages Discord
  notifications.py       alertes DM personnelles et rappels serveur
  metrics.py             statistiques internes (/dev-stats, tableau de bord)
  permissions.py        calculer les permissions des salons
web/
  dashboard.py           pages HTML et échanges OAuth2 Discord (logique pure, testable)
  dashboard_server.py    serveur aiohttp.web et routage
tests/                  tests automatiques (pytest), sans token ni réseau
.github/workflows/      intégration continue
```

---

## Développement et tests

```bash
pip install -r requirements-dev.txt

pytest                 # tests unitaires et parcours simulés, sans token ni réseau
ruff check .           # style et erreurs courantes
```

Les tests simulent un serveur Discord complet en mémoire (`tests/conftest.py`) : ils rejouent un
`/setup-auto`, vérifient les permissions appliquées, le routage des annonces et la modération du
salon des rôles — **sans token ni appel réseau**.

L'intégration continue (`.github/workflows/ci.yml`) rejoue `ruff` et `pytest` sur Python 3.10,
3.11 et 3.12 à chaque `push` et chaque pull request.

---

## Dépannage

| Symptôme | Cause et solution |
| --- | --- |
| « Il me manque une permission » | Donne au bot **Gérer les salons**, **Gérer les rôles** et **Gérer les messages**, et remonte son rôle au-dessus des rôles de plateforme. |
| Les boutons répondent « Ce rôle n'existe plus » | Un rôle a été supprimé à la main : relance `/setup-auto`. |
| Des membres écrivent quand même dans `#choisir-ses-roles` | Ce sont des administrateurs (Discord les autorise toujours) ; leurs messages sont effacés si le bot a **Gérer les messages**. |
| Les commandes n'apparaissent pas | Le bot a besoin du scope `applications.commands` ; sinon attends quelques minutes ou redémarre Discord. |
| Aucune annonce | Vérifie `/test-jeux`, puis `/reset-jeux` si les jeux ont déjà été envoyés. |
| `DISCORD_TOKEN manquant` au démarrage | Le fichier `.env` est absent ou vide : `cp .env.example .env`. |

<div align="center">

# 🎮 FreeGameDrop

**Les jeux gratuits, annoncés automatiquement sur Discord.**
*The all-in-one free game alert bot for Discord.*

[![CI](https://github.com/TOFazer/freegamedrop/actions/workflows/ci.yml/badge.svg)](https://github.com/TOFazer/freegamedrop/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Licence](https://img.shields.io/badge/licence-MIT-green)](LICENSE)
[![Release](https://img.shields.io/github/v/release/TOFazer/freegamedrop?include_prereleases)](https://github.com/TOFazer/freegamedrop/releases)

Chaque heure, FreeGameDrop surveille **Steam, l'Epic Games Store, GOG et Ubisoft**, prévient
ton serveur dès qu'un jeu devient gratuit, et laisse **chaque membre choisir exactement les
alertes qu'il veut recevoir** — plateforme par plateforme, en un clic.

[🚀 Démarrer en 5 minutes](#installation-express) · [✨ Fonctionnalités](#fonctionnalités) · [📊 Démo](#à-quoi-ça-ressemble) · [🧩 Commandes](#commandes) · [🌐 Dashboard web](#tableau-de-bord-web)

<!-- Une instance publique du bot est en ligne ? Remplace le lien ci-dessous par ton
     invitation Discord et décommente le bloc :
<a href="https://discord.com/oauth2/authorize?client_id=TON_CLIENT_ID&permissions=268454928&scope=bot%20applications.commands">
  <img src="https://img.shields.io/badge/➕_Ajouter_FreeGameDrop_à_Discord-7C3AED?style=for-the-badge&logo=discord&logoColor=white" alt="Ajouter FreeGameDrop à Discord">
</a>
-->

</div>

---

## Pourquoi FreeGameDrop ?

Un membre ne veut pas recevoir « DLC random gratuit » toutes les heures.
Il veut : **🔥 Hogwarts Legacy est GRATUIT sur Epic, dépêche-toi, il reste 22 h.**

FreeGameDrop fait exactement ça — et rien d'autre :

- **🔥 Offres exceptionnelles** : les gros jeux complets à forte valeur sont mis en avant
  (critères transparents, calculés uniquement à partir des données fournies par les sources).
- **🔔 Alertes personnalisées** : chaque membre choisit ses plateformes, ses types d'offres,
  sa valeur minimum et ses genres — et reçoit le reste en message privé, jamais en spam.
- **❤️ Favoris + rappel d'expiration** : « Ton jeu favori expire dans 6 heures. »
- **🛰️ Multi-sources résilientes** : GamerPower **et** l'API officielle Epic Games Store,
  agrégées en parallèle ; une source en panne ne bloque jamais les autres.
- **📊 Chiffres publics** : `/stats` n'affiche que des valeurs réellement mesurées par le bot.
- **🔐 Vie privée sérieuse** : réponses éphémères, données minimales, suppression en une
  commande, aucune donnée de message stockée.

## À quoi ça ressemble

L'identité visuelle — couleurs, typographie, boutons, badges, embeds — est définie
dans **[DESIGN.md](DESIGN.md)** (FreeGameDrop en trois mots : **Gaming — Moderne —
Premium**, sous la marque mère Orvex).

**Une annonce dans le salon d'une plateforme** (le filet de l'embed est toujours
violet `#7C3AED`, quelle que soit la plateforme) :

```text
🎁 JEU GRATUIT                          ← badge d'auteur
⚪ Hogwarts Legacy                      ← le nom du jeu, rien d'autre
Un RPG d'action en monde ouvert dans l'univers de Harry Potter…

   💰 Prix                 🎮 Plateforme        ⏰ Fin de l'offre
   ~~59,99 €~~ ➜ GRATUIT   ⚪ Epic Games Store  🟡 dans 22 h (mar. 7 oct. …)

[ 🎁 Récupérer le jeu ]   [ ➕ Ajouter FreeGameDrop ]   ← pied : 🎁 FreeGameDrop · par Orvex
```

**L'urgence se lit en un coup d'œil** : 🟢 plus de 24 h · 🟡 moins de 24 h ·
🟠 moins de 6 h (« 🔥 SE TERMINE BIENTÔT ») · 🔴 moins d'1 h.

**Le gros jeu du jour passe en « offre exceptionnelle » :**

```text
🔥 OFFRE EXCEPTIONNELLE
🔵 Cyberpunk 2077

   💰 Prix                 🎮 Plateforme   ⏰ Fin de l'offre
   ~~59,99 €~~ ➜ GRATUIT   🔵 Steam        🟡 dans 23 heures

   🔥 Offre exceptionnelle
   Jeu complet d'une valeur de 59,99 €, offert pour une durée limitée.
```

**Le panneau que chaque membre voit en arrivant** (`/setup-auto` crée tout) :

```text
🎮 Jeux gratuits                  ← catégorie
 ├── #choisir-ses-roles           ← panneau à boutons, LECTURE SEULE
 │      « Clique sur un bouton pour recevoir le rôle d'une plateforme
 │        et débloquer son salon. Reclique pour le retirer. »
 │      [ 🔵 Steam ] [ ⚪ Epic Games Store ] [ 🟣 GOG ] [ 🔷 Ubisoft ]
 ├── #jeux-steam                  ← visible seulement avec le rôle 🔵 Steam
 ├── #jeux-epic                   ← visible seulement avec le rôle ⚪ Epic Games Store
 └── …
```

**Le navigateur `/free`, en éphémère, avec boutons de pagination et favori :**

```text
🎁 JEU GRATUIT · 🔵 Super Jeu
~~19,99 €~~ ➜ GRATUIT • 🔵 Steam • 🟢 dans 3 jours

[ ◀️ ]  [ ❤️ Retirer des favoris ]  [ ▶️ ]  [ 🎁 Récupérer le jeu ]
```

---

## Sommaire

- [Installation express](#installation-express)
- [Héberger le bot en continu](#héberger-le-bot-en-continu)
- [Inviter le bot sur un serveur](#inviter-le-bot-sur-un-serveur)
- [Lancer le bot](#lancer-le-bot)
- [Commandes](#commandes)
- [Données et confidentialité](#données-et-confidentialité)
- [Fonctionnement](#fonctionnement)
- [Journal, limites et surveillance](#journal-limites-et-surveillance)
- [Tableau de bord web](#tableau-de-bord-web)
- [Feuille de route](#feuille-de-route)
- [Configuration](#configuration)
- [Structure du projet](#structure-du-projet)
- [Développement et tests](#développement-et-tests)
- [Dépannage](#dépannage)
- [Licence](#licence)

---

## Installation express

Prérequis : **Python 3.10 ou plus** (ou [Docker](#héberger-le-bot-en-continu)).

```bash
git clone https://github.com/TOFazer/freegamedrop.git
cd freegamedrop

python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # puis ouvre .env et colle ton token
python main.py
```

Créer le bot et récupérer le token : <https://discord.com/developers/applications>
→ **New Application** → onglet **Bot** → **Reset Token** → copier dans `.env`.

Puis, sur le serveur Discord : `/setup-auto` → coche les plateformes → **Créer / mettre à jour**.
La catégorie, les rôles, les salons privés et le panneau de boutons sont créés ou réparés d'un coup.
Une vérification des offres démarre juste après ; la surveillance continue ensuite toutes les heures.
Relancer la commande met à jour les choix sans créer de doublons. Aucun *intent privilégié* n'est nécessaire.

---

## Héberger le bot en continu

Un bot Discord doit tourner en permanence pour vérifier les offres chaque heure. Trois
options simples, de la plus rapide à la plus souple :

### Option A — PaaS (Railway, Render, Fly.io…)

1. Crée un dépôt GitHub avec ce code (ou fork).
2. Sur le PaaS, crée un service depuis ce dépôt : il détecte le [`Dockerfile`](Dockerfile).
3. Renseigne les variables d'environnement de `.env.example` (`DISCORD_TOKEN` au minimum).

Le `Dockerfile` place la base SQLite dans `/app/data` : monte un volume sur ce chemin
pour que la configuration survive aux redéploiements.

### Option B — Docker sur ton serveur

```bash
docker build -t freegamedrop .
docker run -d --env-file .env -v freegamedrop-data:/app/data --restart unless-stopped freegamedrop
```

### Option C — Machine classique

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # renseigne DISCORD_TOKEN
.venv/bin/python main.py
```

À lancer au démarrage via `systemd`, `screen` ou `tmux`.

### Obtenir le lien « Ajouter à Discord »

Ton instance connaît déjà son propre lien d'invitation : la commande `/info` du bot le
construit automatiquement, et **chaque annonce inclut un bouton ➕ « Ajouter FreeGameDrop »**
— chaque serveur alerté devient une vitrine pour le bot. Pour un lien à partager à la main,
utilise l'[URL d'invitation](#inviter-le-bot-sur-un-serveur) avec l'identifiant (`client_id`)
de ton application.

> 💡 Héberges-tu une instance publique ? Décommente le gros bouton « Ajouter FreeGameDrop
> à Discord » en haut de ce README et colle ton lien d'invitation.

---

## Inviter le bot sur un serveur

Onglet **OAuth2 → URL Generator** : scopes `bot` + `applications.commands`, puis ces permissions :

| Permission | À quoi elle sert |
| --- | --- |
| Gérer les salons | créer et réparer la catégorie et les salons |
| Gérer les rôles | créer et attribuer les rôles de plateforme |
| Voir les salons | accéder aux salons FreeGameDrop |
| Envoyer des messages / Liens intégrés | publier les annonces et le panneau de rôles |

**Permissions facultatives :** `Lire l'historique` et `Gérer les messages` permettent de nettoyer les anciens panneaux et les messages écrits par les administrateurs dans `#choisir-ses-roles`. Elles ne sont pas nécessaires pour l'installation ni pour recevoir les alertes.

Lien tout prêt (remplace `CLIENT_ID` par l'identifiant de ton application) :

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=268454928&scope=bot%20applications.commands
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

## Fonctionnalités

`/setup-auto` construit tout en une fois : catégorie, rôles, salons, panneau de boutons.

- **Un rôle + un salon par plateforme.** Le salon est invisible tant qu'on n'a pas le rôle.
- **Auto-attribution des rôles** : un clic sur un bouton donne (ou retire) le rôle.
- **Salons en lecture seule** : voir, lire et cliquer, rien d'autre. Ni messages, ni réactions,
  ni fils, ni sondages — pour personne.
- **Accès réglable** : `#choisir-ses-roles` est ouvert à tous par défaut, ou réservé aux rôles
  de ton choix (`/acces-salon-roles`).
- **Vérification automatique** toutes les heures, avec mention du rôle concerné, prix barré,
  compte à rebours de fin d'offre et bouton « Récupérer le jeu ».
- **Offres exceptionnelles 🔥** : un jeu complet, temporaire et d'une valeur (libellée en
  euros par la source) d'au moins `MEGA_DEAL_MIN_WORTH_EUR` est annoncé avec le bandeau
  « 🔥 OFFRE EXCEPTIONNELLE » et l'explication chiffrée. Aucune valeur n'est inventée ni
  convertie.
- **Jamais deux fois le même jeu** : les annonces déjà envoyées sont mémorisées.
- **Catalogue privé des offres** avec `/free` : navigation page par page, filtres (plateforme, type
  d'offre, échéance) et lien pour récupérer le jeu.
- **Favoris personnels** : bouton ❤️, commande `/favoris` et commande `/mes-donnees` pour effacer ses favoris.
- **Historique et recherche** : `/historique` revoit les dernières offres connues, `/recherche`
  retrouve une offre par mot-clé.
- **Préférences et alertes personnelles** : `/preferences` filtre les plateformes, les types
  d'offres, le prix minimum et les genres ; `/alertes` active des messages privés pour les
  nouvelles offres correspondantes ou pour un favori qui se termine bientôt.
- **Rappels serveur** : `/rappel-salon` choisit un salon qui reçoit un message le jour où une
  offre suivie se termine.
- **Statistiques publiques** : `/stats` affiche les offres détectées, actives, la valeur
  cumulée connue et la dernière vérification — uniquement des chiffres réellement mesurés.
- **Veille technique** : `/sante` montre l'état réel du bot, de Discord, de la base et de chaque
  source d'offres (🟢 / 🟠 / 🔴) ; les alertes automatiques préviennent quand une source tombe,
  quand une tâche s'arrête, quand la base ne répond plus ou quand les erreurs s'accumulent.
- **Limites raisonnables** : un quota par membre pour les commandes, un quota par serveur pour les
  actions administratives, un espacement des envois Discord — un membre normal ne les remarque
  jamais, un abus est ralenti.
- **Journal de bord sûr** : chaque étape est journalisée (`event=source.failure source=epic …`)
  pour pouvoir répondre à « pourquoi cette offre n'est pas arrivée ? », sans jamais écrire de
  token, de mot de passe ni de donnée personnelle inutile.
- **Boucle virale intégrée** : chaque annonce se termine par le pied de page « 🎁 FreeGameDrop »
  et un bouton « ➕ Ajouter FreeGameDrop ».
- **Tableau de bord web optionnel** avec connexion Discord (OAuth2) et statistiques publiques
  (voir [Tableau de bord web](#tableau-de-bord-web)).

> ℹ️ Les administrateurs passent outre **toutes** les permissions de salon : Discord ne permet
> pas de les empêcher d'écrire. Si le bot a la permission facultative **Gérer les messages**, il
> supprime leurs messages dans `#choisir-ses-roles` ; sans elle, ils restent visibles.

---

## Commandes

Les commandes de configuration sont réservées aux administrateurs. Les commandes publiques et personnelles répondent en privé lorsque c'est pertinent.

| Commande | Accès | Effet |
| --- | --- | --- |
| `/setup-auto` | Admin | Coche les plateformes et clique sur **Créer / mettre à jour**. Crée/répare catégorie, rôles, salons et panneau ; les plateformes décochées sont masquées et réactivables. Lance une première vérification des offres immédiatement. |
| `/config` | Admin | Rouvre le même panneau de configuration que `/setup-auto`. |
| `/acces-salon-roles` | Admin | Change les rôles autorisés à voir `#choisir-ses-roles` (menu vide = tout le monde). Le salon reste en lecture seule. |
| `/test-jeux` | Admin | Force une vérification immédiate des jeux gratuits. |
| `/reset-jeux` | Admin | Vide l'historique des envois : les jeux récents peuvent être réannoncés. |
| `/reset-all` | Admin | Supprime tout ce que le bot a créé (salons, rôles, catégorie, messages). Demande confirmation. |
| `/free` | Tout le monde | Parcourt les offres agrégées (GamerPower, Epic Games Store, …), avec filtres optionnels par plateforme, type d'offre et échéance. La réponse est éphémère ; les boutons permettent de parcourir et d'enregistrer un favori. Les offres sont mises en cache une minute (`OFFER_CACHE_SECONDS`) et limitées à quelques requêtes par membre et par minute. |
| `/favoris` | Tout le monde | Affiche ses favoris en privé ; le bouton permet de retirer une offre. |
| `/historique` | Tout le monde | Revoit les dernières offres connues du bot, avec les mêmes filtres que `/free`. |
| `/recherche` | Tout le monde | Recherche une offre déjà connue par titre ou description. |
| `/preferences` | Tout le monde | Personnalise les plateformes, types d'offres, prix minimum (en euros) et genres pris en compte par `/free` et les alertes personnelles. |
| `/alertes` | Tout le monde | Active ou désactive une alerte par message privé (« nouvelle offre » ou « favori qui se termine bientôt »). |
| `/stats` | Tout le monde | Les chiffres publics du bot : offres détectées, offres actives, valeur connue, plateformes suivies, dernière vérification. |
| `/mes-donnees` | Tout le monde | Demande confirmation puis supprime les favoris associés au compte Discord. |
| `/rappel-salon` | Admin | Choisit le salon qui reçoit un rappel pour les offres qui se terminent le jour même. |
| `/sante` | Tout le monde | État mesuré du bot, de Discord, de la base et des sources d'offres, en réponse privée. Aucun secret, aucune donnée personnelle. |
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
- la date de la dernière vérification des sources, pour `/stats`, et un battement de cœur de la
  surveillance (`monitor_heartbeat_at`), pour qu'un service externe voie que le bot tourne ;
- si le tableau de bord web est activé, une session de connexion temporaire (identifiant Discord, pseudo, expiration, jeton anti-CSRF et instantané des serveurs gérables — jamais le jeton OAuth Discord) créée après une connexion OAuth2 réussie.

Les journaux ne contiennent ni token, ni mot de passe, ni clé d'API, ni adresse e-mail, ni contenu
de message : ces valeurs sont masquées avant écriture (`utils/logging_setup.py`), y compris dans les
traces d'exception. Les identifiants Discord peuvent être remplacés par une empreinte
(`LOG_PSEUDONYMIZE_IDS=true`) si le journal doit sortir de ton infrastructure.

Le bot ne stocke pas les messages privés, les messages des membres ni la preuve qu'un jeu a été réclamé. Les réponses de `/free`, `/favoris`, `/historique` et `/recherche` sont éphémères. Les offres publiques non favorites sont supprimées du catalogue après 90 jours sans nouvelle observation ; celles gardées en favori restent jusqu'au retrait du favori ou à la suppression des données.

Pour supprimer les favoris liés à ton compte, utilise `/mes-donnees` et confirme. Cette action ne supprime pas les réglages du serveur, les préférences/alertes personnelles, ni les informations publiques d'une offre qui serait encore en favori par quelqu'un d'autre. Sur le tableau de bord web, la page « Compte » propose une suppression plus large : favoris, préférences, alertes, historique d'alertes et sessions web d'un coup.

---

## Fonctionnement

```
                 toutes les heures
                        │
      services/gamerpower.py ──► API GamerPower
      services/epic_games.py ──► API Epic Games Store
                        │
              services/offer_engine.py   agrégation, vérification, cache court
                        │               (une source en panne est ignorée, l'état est
                        │                enregistré pour /sante et les alertes)
                        │
                 utils/monitoring.py état des sources, seuils, alertes
                        │
                 utils/platforms.py   « PC (Steam) » → steam
                        │
                   database.py        déjà annoncé ? sinon, on enregistre
                        │
                  utils/embeds.py     construction du message (🔥 si offre exceptionnelle)
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

## Journal, limites et surveillance

Trois mécanismes complémentaires, tous hors ligne et sans dépendance supplémentaire.

**Limites de débit** (`utils/rate_limits.py`) — le but n'est pas de gêner, mais d'éviter qu'un
compte fasse exploser le nombre d'appels :

| Portée | Exemples | Valeur par défaut |
| --- | --- | --- |
| Par membre | `/free` (4/min), `/recherche` (8/min), boutons (60/min) | `RATE_LIMIT_FREE_PER_MINUTE`, `RATE_LIMIT_USER_PER_MINUTE` |
| Par serveur | `/setup-auto`, `/config`, `/acces-salon-roles`, `/rappel-salon` (6/min) | `RATE_LIMIT_ADMIN_PER_MINUTE` |
| Par serveur, actions lourdes | `/test-jeux`, `/reset-jeux`, `/reset-all` (3/10 min) | `RATE_LIMIT_ADMIN_HEAVY_PER_10_MINUTES` |
| Appels aux sources | cache d'une minute + appel unique partagé entre commandes simultanées | `OFFER_CACHE_SECONDS` |
| Envois Discord | espacement entre deux messages d'un même salon, une reprise après un `429` | `DISCORD_SEND_INTERVAL_SECONDS` |

**Journal de bord** (`utils/logging_setup.py`) — chaque étape utile produit une ligne
`event=… clé=valeur`, facile à filtrer :

```bash
grep 'event=source' bot.log        # appels, succès, délais dépassés, pannes
grep 'offer.rejected' bot.log      # offres écartées, avec le motif
grep 'event=monitor.alert' bot.log # alertes de surveillance
```

Les secrets sont masqués **avant** l'écriture (token, clé OAuth, clé du tableau de bord, URL de
webhook, `Authorization`, `code=` OAuth2, adresses e-mail), y compris dans les traces
d'exception. Le contenu des messages Discord n'est jamais journalisé. `LOG_FILE` ajoute un
fichier à rotation (5 Mo × 3) et `LOG_PSEUDONYMIZE_IDS=true` remplace les identifiants Discord
par une empreinte stable.

**Surveillance** (`utils/monitoring.py`, `cogs/sante.py`) — `/sante` affiche l'état mesuré :

```
FreeGameDrop
────────────────────
🟢 Bot              en ligne
🟢 Discord          connecté (latence 42 ms)
🟢 Base de données  saine (2 ms)

Sources
🟢 gamerpower — OK · dernier succès : il y a 2 min · 12 offre(s)
🟢 epic       — OK · dernier succès : il y a 2 min · 3 offre(s)

Dernière vérification : il y a 2 min
Erreurs (15 dernières minutes) : 0
```

Une alerte part automatiquement quand :

- une source n'a plus réussi depuis `SOURCE_DOWN_AFTER_MINUTES` (les autres continuent) ;
- la base de données ne répond plus au ping ;
- une tâche de fond n'a pas tourné depuis son intervalle + `MONITOR_TASK_GRACE_MINUTES` ;
- la connexion Discord est perdue ou très lente ;
- le nombre d'erreurs dépasse `MONITOR_ERROR_ALERT_THRESHOLD` sur
  `MONITOR_ERROR_WINDOW_MINUTES`.

Une même alerte n'est pas répétée avant `MONITOR_ALERT_COOLDOWN_MINUTES`, et le retour à la
normale envoie un message de rétablissement. Les alertes vont dans `MONITOR_ALERT_CHANNEL_ID`
ou, à défaut, en message privé au propriétaire du bot. Sans destinataire joignable (Discord
coupé), elles restent dans le journal — et `/api/health` permet à un service externe de voir
que le bot ne répond plus du tout.

---

## Tableau de bord web

Un petit serveur web optionnel (basé sur `aiohttp.web`, déjà dans les dépendances du bot — aucun
paquet supplémentaire requis) sert de **centre de configuration** de FreeGameDrop :

- `GET /` : page d'accueil publique avec les boutons « Ajouter à Discord » et « Se connecter avec
  Discord » (OAuth2, scopes `identify guilds` uniquement), plus les statistiques globales.
- `GET /offres` : la vitrine publique des jeux gratuits connus du bot, filtrable par plateforme.
- `GET /serveurs` : après connexion, la liste des serveurs que le membre peut **réellement**
  administrer (propriétaire, administrateur ou « Gérer le serveur »), avec l'état d'installation
  du bot sur chacun.
- `GET`/`POST /serveurs/{id}` : configuration d'un serveur — salons d'annonces et rôles par
  plateforme, salon des rappels, et vérification des permissions du bot (avec un bouton
  « Corriger » si une permission manque).
- `GET`/`POST /alertes` : les alertes personnelles (DM) et les types d'offres suivis, les mêmes
  réglages que `/alertes` et `/preferences` sur Discord.
- `GET /compte`, `POST /compte/supprimer` : résumé des données conservées et suppression complète.
- `GET /api/stats` : les statistiques globales en JSON.
- `GET /health` et `GET /api/health` : l'état mesuré du bot en JSON (composants, sources,
  tâches, erreurs récentes, horodatages) — à brancher sur un service de supervision externe.
  Aucun secret n'y figure.
- `GET /login`, `GET /auth/callback`, `GET /logout` : parcours de connexion/déconnexion.

Pour l'activer :

1. Crée une application sur <https://discord.com/developers/applications>, onglet **OAuth2**,
   et ajoute une redirection `http://localhost:8080/auth/callback` (ou ton domaine).
2. Renseigne dans `.env` : `DASHBOARD_ENABLED=true`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`,
   et au besoin `DASHBOARD_PORT` / `DASHBOARD_BASE_URL` / `DISCORD_OAUTH_REDIRECT_URI`.
3. Lance le bot normalement (`python main.py`) : le tableau de bord démarre avec lui, sur
   `DASHBOARD_HOST:DASHBOARD_PORT`.

Le tableau de bord ne stocke aucune donnée de jeu séparée : il lit la même base SQLite que le bot.

**Sécurité du tableau de bord.**

- Le jeton OAuth Discord du membre n'est **jamais stocké** : il sert uniquement, au moment de la
  connexion, à lire son identité et la liste de ses serveurs gérables (id, nom, icône) — cet
  instantané est ensuite conservé dans la session, côté serveur.
- Un serveur n'est configurable que si le membre peut le gérer **et** que le bot y est présent ;
  chaque identifiant de salon ou de rôle envoyé par un formulaire est vérifié comme appartenant
  bien à ce serveur.
- Tous les formulaires sont protégés par un jeton anti-CSRF propre à la session.
- Le cookie de session (`HttpOnly`, `SameSite=Lax`) reçoit aussi l'attribut `Secure` dès que
  `DASHBOARD_BASE_URL` commence par `https://` — donc automatiquement en production normale, sans
  rien à faire. Si tu places un reverse proxy qui termine le TLS devant le bot (le serveur interne
  reste alors en HTTP), force quand même `DASHBOARD_COOKIE_SECURE=true`. Ne mets jamais
  `DASHBOARD_COOKIE_SECURE=false` sur un tableau de bord exposé publiquement.

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
| `LOG_FILE` | *(vide)* | Fichier de journal supplémentaire (rotation 5 Mo × 3) ; vide = sortie standard uniquement. |
| `LOG_PSEUDONYMIZE_IDS` | `false` | Remplace les identifiants Discord par une empreinte stable dans les logs. |
| `LOG_MAX_FIELD_CHARS` | `160` | Longueur maximale d'un champ dans les lignes `event=…`. |
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
| `OFFER_CACHE_SECONDS` | `60` | Durée de réutilisation des offres pour `/free` (un seul appel partagé entre commandes simultanées). |
| `RATE_LIMIT_USER_PER_MINUTE` | `20` | Plafond, par membre, toutes commandes de lecture confondues. |
| `RATE_LIMIT_FREE_PER_MINUTE` | `4` | Appels de `/free` par membre et par minute. |
| `RATE_LIMIT_ADMIN_PER_MINUTE` | `6` | Actions de configuration par serveur et par minute. |
| `RATE_LIMIT_ADMIN_HEAVY_PER_10_MINUTES` | `3` | Tests et réinitialisations par serveur, sur 10 minutes. |
| `DISCORD_SEND_INTERVAL_SECONDS` | `0.4` | Espacement minimal entre deux messages d'un même salon ou à un même membre. |
| `MONITOR_ENABLED` | `true` | Active la boucle de surveillance et ses alertes. |
| `MONITOR_INTERVAL_MINUTES` | `5` | Fréquence des contrôles de surveillance. |
| `MONITOR_ALERT_CHANNEL_ID` | *(vide)* | Salon qui reçoit les alertes de surveillance ; vide = message privé au propriétaire. |
| `MONITOR_OWNER_ID` | *(vide)* | Destinataire de secours des alertes ; vide = propriétaire du bot. |
| `SOURCE_DOWN_AFTER_MINUTES` | `10` | Délai sans succès au-delà duquel une source est déclarée indisponible. |
| `MONITOR_ALERT_COOLDOWN_MINUTES` | `30` | Délai minimal entre deux alertes identiques. |
| `MONITOR_ERROR_WINDOW_MINUTES` | `15` | Fenêtre glissante du comptage d'erreurs. |
| `MONITOR_ERROR_ALERT_THRESHOLD` | `10` | Nombre d'erreurs dans la fenêtre qui déclenche l'alerte « pic d'erreurs ». |
| `MONITOR_TASK_GRACE_MINUTES` | `10` | Marge accordée à une tâche avant de la signaler comme arrêtée. |
| `MONITOR_LATENCY_WARN_MS` | `1000` | Latence Discord au-delà de laquelle la connexion est signalée comme dégradée. |
| `DEFAULT_TIMEZONE` | `Europe/Paris` | Fuseau horaire par défaut des filtres de date de `/free`. |
| `ALERT_CADENCE_HOURS` | `1` | Délai minimal entre deux alertes DM identiques pour un même membre. |
| `LAST_DAY_HOURS` | `24` | Fenêtre considérée comme « se termine bientôt ». |
| `MEGA_DEAL_MIN_WORTH_EUR` | `19.99` | Seuil de valeur (en euros, libellée par la source) pour le bandeau « 🔥 Offre exceptionnelle ». `0` désactive. |
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
DESIGN.md               livre de marque : identité visuelle FreeGameDrop (couleurs, typo, embeds)
ROADMAP.md              feuille de route des prochaines versions
cogs/
  jeux.py               commandes, menus, navigation des offres, boucle de vérification
  setup.py              /ping, /info et /stats
  sante.py              /sante et boucle d'alertes de surveillance
services/
  gamerpower.py         appel à l'API GamerPower (et rien d'autre)
  epic_games.py          appel à l'API de l'Epic Games Store (et rien d'autre)
  offer_engine.py        agrège les sources, tolère les pannes, dédoublonne
utils/
  design.py             design tokens de l'identité visuelle (couleurs, urgence, typo, boutons)
  platforms.py          reconnaître la plateforme d'un jeu
  offers.py             filtres de catalogue, préférences, offres exceptionnelles
  embeds.py             construire les messages Discord
  branding.py           lien d'invitation partagé (/info, /stats, annonces)
  notifications.py       alertes DM personnelles et rappels serveur
  metrics.py             statistiques internes (/dev-stats) et publiques (/stats)
  rate_limits.py         quotas par membre/serveur et espacement des envois Discord
  logging_setup.py       journal d'événements sûr (secrets masqués avant écriture)
  monitoring.py          état des composants, seuils d'alerte et rapport /sante
  permissions.py        calculer les permissions des salons
web/
  dashboard.py           pages HTML et échanges OAuth2 Discord (logique pure, testable)
  dashboard_server.py    serveur aiohttp.web et routage
tests/                  tests automatiques (pytest), sans token ni réseau
.github/workflows/      intégration continue
Dockerfile              image de production pour l'auto-hébergement
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

Ils couvrent aussi les situations anormales, car c'est là que le bot se casse en vrai :

| Famille | Exemples couverts |
| --- | --- |
| Pannes de source | API en erreur, réponse illisible, format inattendu, délai d'attente dépassé — les autres sources continuent (`tests/test_source_reliability.py`, `tests/test_offer_engine.py`). |
| Faux positifs | offre terminée, statut « non active » annoncé par la source, remise non nulle, lien invalide : jamais annoncés. |
| Base de données | ping en échec : alerte envoyée, rapport passé au rouge, bot qui continue de tourner. |
| Discord | salon supprimé, permissions refusées, `429 Too Many Requests` (une seule reprise). |
| Limites | quotas par membre et par serveur, fenêtre glissante, plafond global, messages d'attente. |
| Journal | token, mot de passe, URL de webhook et e-mail jamais écrits, même dans une trace d'exception. |
| Surveillance | source déclarée indisponible, retour à la normale, pic d'erreurs, tâche arrêtée, anti-spam des alertes. |

L'intégration continue (`.github/workflows/ci.yml`) rejoue `ruff` et `pytest` sur Python 3.10,
3.11 et 3.12 à chaque `push` et chaque pull request.

---

## Dépannage

| Symptôme | Cause et solution |
| --- | --- |
| « Il me manque une permission » | Accorde au bot **Gérer les salons**, **Gérer les rôles**, **Voir les salons**, **Envoyer des messages** et **Intégrer des liens**. Pour attribuer un rôle, place aussi le rôle du bot au-dessus des rôles de plateforme. |
| Les boutons répondent « Ce rôle n'existe plus » | Un rôle a été supprimé à la main : relance `/setup-auto`. |
| Des membres écrivent quand même dans `#choisir-ses-roles` | Ce sont des administrateurs (Discord les autorise toujours) ; leurs messages sont effacés si le bot a **Gérer les messages**. |
| Les commandes n'apparaissent pas | Le bot a besoin du scope `applications.commands` ; sinon attends quelques minutes ou redémarre Discord. |
| Aucune annonce | Vérifie `/test-jeux`, puis `/reset-jeux` si les jeux ont déjà été envoyés. |
| « FreeGameDrop n'a pas envoyé l'offre Epic » | Lance `/sante` : la ligne de la source indique si elle a répondu, quand, avec combien d'offres, ou pourquoi elle est en panne. Puis `grep 'event=offer' bot.log` pour voir si l'offre a été détectée, écartée (`offer.rejected`) ou déjà annoncée (`offer.duplicate`). |
| Une source est en 🔴 dans `/sante` | Elle n'a plus répondu depuis `SOURCE_DOWN_AFTER_MINUTES` : vérifie l'accès réseau du serveur, l'URL dans `.env` (`GAMERPOWER_API_URL`, `EPIC_API_URL`). Les autres sources continuent d'alimenter le bot. |
| Aucune alerte de surveillance reçue | Vérifie `MONITOR_ENABLED`, `MONITOR_ALERT_CHANNEL_ID` (ou les messages privés du propriétaire), et `grep 'event=monitor.alert' bot.log`. |
| Des lignes `***` dans les logs | C'est voulu : c'est une valeur sensible (token, clé, webhook, e-mail) masquée avant écriture. |
| `DISCORD_TOKEN manquant` au démarrage | Le fichier `.env` est absent ou vide : `cp .env.example .env`. |

---

## Licence

Publié sous [licence MIT](LICENSE) — utilisation, modification et redistribution libres,
y compris pour ton propre serveur ou ton hébergement public.

## Validation avant lancement

La checklist de recette Discord, les corrections de la phase 1 et les limites encore connues
sont suivies dans [PHASE1_VALIDATION.md](PHASE1_VALIDATION.md).
Un panneau expiré ou ouvert avant un redémarrage se reprend en relançant `/setup-auto`.
Un salon homonyme non enregistré n'est pas adopté automatiquement : renomme-le pour poursuivre.

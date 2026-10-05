# 🎮 FreeGameDrop

Bot Discord qui annonce automatiquement les **jeux gratuits** (Steam, Epic Games Store, GOG,
Ubisoft) dans des salons dédiés, et laisse chaque membre choisir les alertes qu'il veut recevoir
en cliquant sur un bouton.

Les données viennent de l'API publique [GamerPower](https://www.gamerpower.com/api-read).

---

## Sommaire

- [Ce que fait le bot](#ce-que-fait-le-bot)
- [Installation](#installation)
- [Inviter le bot sur un serveur](#inviter-le-bot-sur-un-serveur)
- [Lancer le bot](#lancer-le-bot)
- [Commandes](#commandes)
- [Fonctionnement](#fonctionnement)
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
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=268561424&scope=bot%20applications.commands
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

Toutes les commandes sont réservées aux administrateurs et répondent en message éphémère
(visible de toi seul).

| Commande | Effet |
| --- | --- |
| `/setup-auto` | Choisit les plateformes et qui voit `#choisir-ses-roles`, puis crée/met à jour catégorie, rôles, salons et panneau de boutons. Rejouable sans rien dupliquer. |
| `/acces-salon-roles` | Change les rôles autorisés à voir `#choisir-ses-roles` (menu vide = tout le monde). Le salon reste en lecture seule. |
| `/test-jeux` | Force une vérification immédiate des jeux gratuits. |
| `/reset-jeux` | Vide l'historique des envois : les jeux récents peuvent être réannoncés. |
| `/reset-all` | Supprime tout ce que le bot a créé (salons, rôles, catégorie, messages). Demande confirmation. |
| `/ping` | Vérifie que le bot répond et affiche sa latence. |

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

## Configuration

Tout est dans `config.py`, surchargeable par le fichier `.env` (voir `.env.example`) :

| Variable | Défaut | Rôle |
| --- | --- | --- |
| `DISCORD_TOKEN` | — | **Obligatoire.** Token du bot. |
| `DB_PATH` | `bot.db` | Fichier SQLite. |
| `CHECK_INTERVAL_HOURS` | `1` | Fréquence de vérification. |
| `MAX_GAMES` | `10` | Jeux récents examinés à chaque tour. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `CATEGORY_NAME` | `🎮 Jeux gratuits` | Nom de la catégorie créée. |
| `ROLES_CHANNEL` | `choisir-ses-roles` | Nom du salon de choix des rôles. |
| `TEST_GUILD_ID` | *(serveur de test)* | Serveur dont on purge les anciennes commandes au démarrage ; `0` pour désactiver. |
| `GAMERPOWER_API_URL` | API GamerPower | Source des jeux. |
| `GAMERPOWER_TIMEOUT` | `15` | Délai d'attente réseau, en secondes. |

**Ajouter une plateforme** (exemple : Amazon Prime Gaming) — une seule ligne dans `config.py` :

```python
Platform("prime", "Prime Gaming", ("prime gaming",), "🟠", 0xFF9900),
```

Les mots-clés sont cherchés en minuscules dans le champ `platforms` renvoyé par l'API.

---

## Structure du projet

```
main.py                 point d'entrée : démarre le bot et charge les cogs
config.py               toute la configuration (.env, plateformes, noms des salons)
database.py             stockage SQLite (salons, rôles, accès, historique)
cogs/
  jeux.py               commandes, menus, boucle de vérification
  setup.py              /ping
services/
  gamerpower.py         appel à l'API (et rien d'autre)
utils/
  platforms.py          reconnaître la plateforme d'un jeu
  embeds.py             construire les messages Discord
  permissions.py        calculer les permissions des salons
tests/                  tests automatiques (pytest), sans token ni réseau
.github/workflows/      intégration continue
```

---

## Développement et tests

```bash
pip install -r requirements-dev.txt

pytest                 # 95 tests, moins d'une seconde
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

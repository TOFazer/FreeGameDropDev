# 🧪 Environnements DEV et PROD

Ce dépôt est l'environnement de **développement**. Il doit pouvoir tourner à côté de la
production sans jamais la toucher : deux applications Discord, deux jetons, deux bases
SQLite, deux volumes Docker, deux redirections OAuth.

```
FreeGameDropDev                      FreeGameDrop (production)
│                                    │
├── Bot Discord DEV                  ├── Bot Discord PROD
├── Base SQLite DEV (data/…-dev.db)  ├── Base SQLite PROD (/app/data/bot.db)
├── Application Discord DEV          ├── Application Discord PROD
└── Token DEV (.env local)           └── Token PROD (.env du serveur)

                 ❌ AUCUN ACCÈS D'UN CÔTÉ À L'AUTRE
```

Le même code sert les deux ; ce sont les valeurs de `.env` qui décident de tout. Le
garde-fou décrit plus bas refuse de démarrer plutôt que de laisser un mélange se produire.

---

## 1. Le garde-fou, en quatre verrous

Rien n'est tenté côté Discord avant que ces quatre contrôles soient passés
(`utils/environment.py`, appelé par `main.py` avant toute connexion) :

| Verrou | Ce qui est comparé | Si ça ne correspond pas |
| --- | --- | --- |
| Environnement déclaré | `ENVIRONMENT` doit valoir `development` ou `production` | ❌ démarrage refusé |
| Environnement attendu | `ENVIRONMENT` **=** `EXPECTED_ENVIRONMENT` | ❌ `Environment mismatch` |
| Application Discord | identifiant encodé dans `DISCORD_TOKEN` **=** `DISCORD_APPLICATION_ID` **=** `DISCORD_CLIENT_ID` | ❌ `Discord application mismatch` |
| Fichier SQLite | `DB_PATH` ne doit pas désigner la base de l'autre environnement | ❌ démarrage refusé |

**Le jeton ne vient jamais d'ailleurs que de `DISCORD_TOKEN`** : `ENVIRONMENT` ne choisit
rien, il contrôle. Un `.env` de production posé par erreur dans ce dépôt s'arrête donc
immédiatement, avec un message explicite :

```
CRITICAL utils.environment | [DEVELOPMENT] ❌ Discord application mismatch : le jeton appartient
à l'application 111… alors que DISCORD_APPLICATION_ID=222… est attendu pour l'environnement development.
CRITICAL utils.environment | [DEVELOPMENT] 🧪 Development bot refused to start (1 erreur(s) de configuration).
```

L'identifiant d'application est lu **localement** dans le jeton (`base64(application_id).secret.
checksum`) : aucun appel réseau n'est nécessaire pour savoir à quelle application appartient un
jeton.

Deux garde-fous complémentaires, eux non bloquants, avertissent quand la vérification est
incomplète : `EXPECTED_ENVIRONMENT` ou `DISCORD_APPLICATION_ID` non renseignés.

> 🧨 Le scénario évité : `FreeGameDropDev` + mauvais jeton + connexion au serveur de prod.
> Avec ce garde-fou, la seule chose qui se passe est un arrêt immédiat et une ligne rouge
> dans les journaux.

### Vérifier le garde-fou à la main

```bash
# Doit refuser (code de sortie 1, message « Discord application mismatch »)
ENVIRONMENT=development EXPECTED_ENVIRONMENT=development \
DISCORD_APPLICATION_ID=111111111111111111 \
DISCORD_TOKEN="OTg3NjU0MzIxMDk4NzY1NDMy.jeton.factice" python main.py
```

---

## 2. Le `.env` de développement

`cp .env.example .env`, puis :

```dotenv
ENVIRONMENT=development
EXPECTED_ENVIRONMENT=development
DISCORD_APPLICATION_ID=ID_APPLICATION_DEV      # onglet General Information
DISCORD_TOKEN=TON_TOKEN_DU_BOT_DEV             # onglet Bot
DB_PATH=data/freegamedrop-dev.db
LOG_LEVEL=DEBUG
MAINTENANCE_MODE=false

CHECK_INTERVAL_HOURS=1
MAX_GAMES=10

DASHBOARD_ENABLED=true
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8080
DASHBOARD_BASE_URL=http://localhost:8080
DISCORD_CLIENT_ID=ID_APPLICATION_DEV
DISCORD_CLIENT_SECRET=TON_CLIENT_SECRET_DEV
DISCORD_OAUTH_REDIRECT_URI=http://localhost:8080/auth/callback
```

- `.env` reste dans `.gitignore` : **le dépôt ne contient jamais `DISCORD_TOKEN=…`** (l'étape
  CI « Vérifier que le dépôt ne contient aucun secret » fait échouer le build si ça arrive).
- `EXPECTED_ENVIRONMENT` et `DISCORD_APPLICATION_ID` sont la partie « ceinture et bretelles » :
  ils rendent l'erreur humaine impossible à ignorer.

---

## 3. Créer l'application Discord DEV

1. <https://discord.com/developers/applications> → **New Application** → `FreeGameDrop Dev`.
2. Onglet **General Information** : copie **Application ID** → `DISCORD_APPLICATION_ID`.
3. Onglet **Bot** → **Reset Token** → copie dans `DISCORD_TOKEN` (uniquement dans `.env`).
   Le bot n'a besoin d'**aucun intent privilégié**.
4. Onglet **OAuth2 → Redirects** : ajoute `http://localhost:8080/auth/callback`
   (puis `https://dev.ton-domaine/auth/callback` quand le DEV sera hébergé).
5. Onglet **OAuth2** : copie **Client ID** (identique à l'Application ID) et **Client Secret**
   → `DISCORD_CLIENT_ID` / `DISCORD_CLIENT_SECRET` du DEV. **Ce secret n'est pas celui de la prod.**

L'installation du bot demande les scopes `bot` + `applications.commands`
(`/info` et chaque annonce génèrent le lien d'invitation). Lien tout prêt :

```
https://discord.com/oauth2/authorize?client_id=ID_APPLICATION_DEV&permissions=268454928&scope=bot%20applications.commands
```

---

## 4. Serveur Discord de test

Crée un serveur dédié — par exemple **🧪 ORVEX DEVELOPMENT** — et n'y installe que
l'application **FreeGameDrop Dev** :

```
🧪 ORVEX DEVELOPMENT
├── #test        essais de commandes
├── #test-jeux   annonces automatiques
├── #logs        journaux / surveillance
└── #bugs        ce qui casse
```

Ensuite, dans ce serveur : `/setup-auto` → coche les plateformes → **Créer / mettre à jour**.
Un `TEST_GUILD_ID` peut y pointer pour nettoyer les copies de commandes au démarrage.

---

## 5. Base SQLite DEV

```
FreeGameDropDev/
├── data/
│   ├── .gitkeep                 (dossier conservé dans git)
│   └── freegamedrop-dev.db      (ignoré par git, créé au premier démarrage)
```

- Le dossier `data/` est créé automatiquement si besoin (`database.init_db`).
- `.gitignore` exclut `data/*`, `*.db`, `*.db-wal` et `*.db-shm`.
- En DEV, un `DB_PATH` contenant `prod` **empêche** le démarrage ; en PROD, un **nom de fichier**
  contenant `dev` ou `test` le refuse aussi (un dossier parent nommé `dev` ne bloque rien : seuls
  les déploiements manifestement mal ciblés sont arrêtés).

**Instance existante (mise à jour).** Sans `ENVIRONMENT` dans `.env`, l'instance se déclare
`production`, comme avant la séparation des environnements, et garde `bot.db` : rien ne change.
Ajoute `EXPECTED_ENVIRONMENT=production` (ou `development`) et `DISCORD_APPLICATION_ID` pour
activer le contrôle complet. Si le nom du fichier SQLite évoque l'autre environnement alors que
l'instance est correctement déclarée, le démarrage est refusé : renomme le fichier (`bot.db` en
production, `data/freegamedrop-dev.db` en développement) ou corrige `ENVIRONMENT`.

**Pourquoi rester sur SQLite ?** Le bot fonctionne déjà dessus et stocke : configuration des
serveurs, offres annoncées, catalogue, favoris, préférences, alertes, statistiques, sessions
web. Migrer maintenant vers PostgreSQL ajouterait beaucoup de risque pour peu de gain. La
migration se fera quand la croissance du bot la justifiera — le passage est prévu en
V4+ (voir `ROADMAP.md`), pas dans cette étape.

---

## 6. Tableau de bord DEV

Le tableau de bord est celui qui existe déjà (`web/dashboard.py`, aiohttp.web). En DEV il
s'affiche sous une identité impossible à confondre :

| | DEV | PROD |
| --- | --- | --- |
| Titre de l'onglet | `🧪 FreeGameDrop DEV — …` | `FreeGameDrop — …` |
| En-tête | `🎮 FreeGameDrop DEV` + badge `🧪 DEV` | `🎮 FreeGameDrop` |
| Bandeau | « environnement de développement, base et application Discord dédiées » | — |
| OAuth | application **DEV** (secret DEV, redirection localhost) | application **PROD** (secret PROD, domaine public) |

Les cookies `Secure` restent automatiques dès que `DASHBOARD_BASE_URL` est en `https://`.

`GET /health` et `GET /api/health` exposent désormais `environment` (`development` /
`production`) : un superviseur externe qui interroge les deux instances voit immédiatement
laquelle répond. `/sante` affiche la même information sur sa première ligne.

---

## 7. Docker DEV

```bash
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml logs -f
```

| | DEV | PROD |
| --- | --- | --- |
| Conteneur | `freegamedrop-dev` | `freegamedrop` |
| Volume | `freegamedrop-dev-data` → `/app/data` | `freegamedrop-prod-data` → `/app/data` |
| Base dans le conteneur | `/app/data/freegamedrop-dev.db` | `/app/data/bot.db` |
| Jeton | `.env` local (application DEV) | `.env` du serveur (application PROD) |

Le compose DEV force `ENVIRONMENT=development`, `EXPECTED_ENVIRONMENT=development` et un
`DB_PATH` dédié : même si `.env` était copié depuis la production, la base DEV reste la sienne.
**Jamais le même volume que la production.**

---

## 8. Intégration continue et déploiement DEV

`.github/workflows/ci.yml` — quatre contrôles, puis une porte unique :

```
push / pull_request
        │
        ├── Style (ruff)
        ├── Tests (Python 3.10, 3.11, 3.12) — aucun token, aucun réseau
        ├── Garde-fou DEV / PROD  (le vrai binaire refuse les mauvaises configs)
        └── Image Docker + validation de docker-compose.dev.yml
                        │
                        ▼
                    CI OK  ◀── seule porte à exiger sur `main`
```

`.github/workflows/deploy-dev.yml` ne se déclenche **qu'après** une CI verte sur `main`
(`workflow_run` + `conclusion == success`) ou à la main. Il est inerte tant que rien n'est
configuré : pour l'activer, définis la variable de dépôt `DEV_DEPLOY_ENABLED=true` et le
secret `DEV_DEPLOY_WEBHOOK` (webhook propre au serveur DEV). Sans eux, le job affiche la
commande `docker compose -f docker-compose.dev.yml up -d --build` et s'arrête proprement.

---

## 9. Tests

| Fichier | Ce qui est vérifié |
| --- | --- |
| `tests/test_environment.py` | environnements, préfixes de journal, jeton/application/base, refus de démarrage (y compris **processus réel** `main.py`) |
| `tests/test_maintenance.py` | mode maintenance : veille suspendue, commandes de test conservées |
| `tests/test_config.py` | lecture `.env`, valeurs par défaut, absence de jeton dans le code |
| `tests/test_database.py` | SQLite, création du dossier `data/`, salons, rôles, favoris |
| `tests/test_offers.py`, `tests/test_offer_engine.py` | sélection et agrégation des offres |
| `tests/test_dashboard.py` | **web** : pages, OAuth2, API JSON, identité DEV / PROD, maintenance |
| `tests/test_public_info.py` | `/info` : environnement, latence, serveurs, base |
| `tests/test_history_and_alerts.py`, `tests/test_new_commands.py` | **préférences** (type, prix, genres, plateformes, fuseau) et alertes |
| `tests/test_permissions.py` | **permissions** : ce que le bot crée, modifie et refuse |
| `tests/test_notifications.py`, `tests/test_offers.py` | filtres et alertes appliqués aux préférences |
| `tests/conftest.py` + 25 autres fichiers | parcours complets simulés, sans token ni réseau |

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest          # tous les tests
.venv/bin/ruff check .    # style
```

Le test le plus important du lot :

```python
def test_le_bot_de_dev_refuse_un_jeton_de_production():
    """Le scénario catastrophe : `.env` de production lancé depuis le dépôt de dev."""
```

---

## 10. Mode maintenance

```dotenv
MAINTENANCE_MODE=true
```

- La **veille automatique** ne publie plus rien (`event=check.skipped reason=maintenance`).
- Les **commandes d'administration** (`/test-jeux`, `/config`, `/setup-auto`) restent
  utilisables : on peut tester sans que les membres croient que le vrai bot est cassé.
- Les notifications privées et les rappels de salon sont suspendus avec la veille.
- `/info` et le tableau de bord affichent « 🔧 Maintenance : les annonces automatiques sont
  suspendues. »

---

## 11. Journaux

En DEV, `LOG_LEVEL=DEBUG` par défaut ; en PROD, `LOG_LEVEL=INFO`. Les trois premières lignes
identifient l'instance :

```
[DEVELOPMENT] FreeGameDrop starting...
[DEVELOPMENT] Environment: 🧪 Development
[DEVELOPMENT] Database: data/freegamedrop-dev.db
[DEVELOPMENT] Discord application: 111…
[DEVELOPMENT] Maintenance mode: off
[DEVELOPMENT] Discord bot connected as FreeGameDrop Dev#1234
[DEVELOPMENT] Servers: 1
```

En production, le même bandeau s'écrit `[PRODUCTION] …`. Les secrets restent masqués avant
écriture (`utils/logging_setup.py`), sur la sortie standard comme dans `LOG_FILE`.

---

## 12. Ce que cette étape ne fait pas

❌ pas de `OrvexWebsite` — ❌ pas de PostgreSQL — ❌ pas de deuxième bot — ❌ pas de
microservices — ❌ pas de Kubernetes — ❌ pas de dashboard Next.js — ❌ pas de migration massive.

Seulement : **FREEGAMEDROP DEV** → application Discord DEV → bot + SQLite DEV + tableau de bord
DEV + Docker DEV + tests et CI. La production sera traitée quand le DEV sera propre.

---

## 13. Mise en route — à cocher

- [ ] Application **FreeGameDrop Dev** créée ; Application ID et Client Secret relevés.
- [ ] `cp .env.example .env` puis renseigné : `DISCORD_TOKEN`, `DISCORD_APPLICATION_ID`,
      `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`.
- [ ] `python main.py` : les lignes `[DEVELOPMENT] …` apparaissent, aucune erreur.
- [ ] Essai raté volontaire : mauvais `DISCORD_APPLICATION_ID` → démarrage refusé.
- [ ] Serveur **🧪 ORVEX DEVELOPMENT** prêt, bot DEV installé avec
      `bot` + `applications.commands`.
- [ ] `/setup-auto` passé sur ce serveur ; `/info` affiche `🧪 Development` et la base DEV.
- [ ] Redirection OAuth DEV déclarée dans le portail ; tableau de bord affiché en
      `🧪 FreeGameDrop DEV`.
- [ ] `docker compose -f docker-compose.dev.yml up -d` : volume `freegamedrop-dev-data` créé.
- [ ] CI verte sur `main` (style, tests, garde-fou, image Docker).
- [ ] `git status` ne montre ni `.env` ni fichier `*.db`.

---

## 14. Dépannage express

| Message | Cause | Solution |
| --- | --- | --- |
| `DISCORD_TOKEN manquant` | `.env` absent ou vide | `cp .env.example .env` puis renseigne le token |
| `❌ Discord application mismatch` | jeton d'une autre application que `DISCORD_APPLICATION_ID` / `DISCORD_CLIENT_ID` | utilise le jeton de **l'application DEV** (ou corrige l'identifiant annoncé) |
| `❌ Environment mismatch` | `ENVIRONMENT` ≠ `EXPECTED_ENVIRONMENT` | aligne les deux lignes du `.env` |
| `❌ Refus de démarrer en développement sur une base de production` | `DB_PATH` contient `prod` | mets `data/freegamedrop-dev.db` |
| `❌ ENVIRONMENT=… inconnu` | faute de frappe | `development` ou `production`, en minuscules |
| `⚠️ DISCORD_APPLICATION_ID absent` | garde-fou incomplet | renseigne l'identifiant de l'application DEV |
| Le tableau de bord affiche « FreeGameDrop » sans `DEV` | `ENVIRONMENT` n'est pas `development` | vérifie le `.env` réellement lu |
| Aucune annonce pendant les essais | `MAINTENANCE_MODE=true` | repasse à `false` |

# FreeGameDrop — feuille de route

Le projet avance par lots testables. Les fonctions ci-dessous ne sont pas toutes annoncées comme
disponibles : seuls les lots marqués **Livré** sont implémentés dans le code actuel.

## Livré — V1.5, lot 1 : catalogue léger et favoris

- `/free` : parcourt en privé les offres retournées par GamerPower, avec pagination et lien de récupération.
- Bouton ❤️ dans le navigateur pour ajouter ou retirer une offre des favoris.
- `/favoris` : consulte et retire ses favoris, en réponse éphémère.
- `/mes-donnees` : demande confirmation puis efface les favoris associés à l'identifiant Discord de l'utilisateur.
- Enregistrement d'un sous-ensemble des informations publiques des offres, sans nom d'utilisateur, message privé ni preuve de réclamation.
- Les offres publiques non favorites expirées du catalogue sont nettoyées après 90 jours ; une offre reste disponible tant qu'un utilisateur l'a en favori.

## Livré — V1.5, lot 2 : historique, recherche et filtres fiables

- `/historique` pour parcourir les offres enregistrées récemment, avec filtres plateforme et type d'offre.
- `/recherche` par titre et description.
- `/dev-stats` (réservé au propriétaire du bot) pour compter les offres, les sources, les favoris
  et les serveurs configurés — portée et période indiquées pour chaque chiffre.
- Classification prudente du type d'offre (jeu complet / DLC / contenu) à partir du champ fourni
  par la source : aucun type n'est deviné quand il n'est pas fourni, et il est alors classé « contenu ».
- Une offre n'est jamais présentée comme effectivement réclamée par qui que ce soit.

## Livré — V1.5, lot 3 : préférences et alertes personnelles

- `/preferences` : type d'offre, prix minimum (en euros, lu uniquement s'il est explicitement
  libellé en euros) et genres (uniquement ceux fournis explicitement par une source, jamais devinés).
- `/alertes` : active ou désactive, par membre, une alerte en message privé pour une nouvelle
  offre correspondant à ses préférences, ou pour un favori qui se termine bientôt.
- Cadence minimale entre deux alertes identiques (`ALERT_CADENCE_HOURS`) pour éviter le spam.
- Fuseau horaire personnel optionnel pour les filtres d'échéance de `/free` (sinon `DEFAULT_TIMEZONE`).
- Tout est désactivé par défaut, réversible, et lié uniquement à l'identifiant Discord du membre.

## Livré — V2, partiel : annonces serveur et résilience multi-sources

- `/rappel-salon` : un salon par serveur reçoit un message pour les offres qui se terminent le jour même.
- `services/offer_engine.py` agrège plusieurs sources en parallèle ; une source en panne ou trop
  lente (`OFFER_SOURCE_TIMEOUT`) est simplement ignorée pour ce tour, sans bloquer les autres.
- Dédoublonnage entre sources par identifiant.

## Livré — V3, partiel : deuxième source et typage des offres

- `services/epic_games.py` : jeux actuellement offerts sur l'Epic Games Store, dans le même format
  commun que les autres sources (`source`, `offer_type`, `genres`).
- Les DLC et contenus sont distingués des jeux complets dès qu'une source le permet ; `/free` et
  `/historique` peuvent filtrer dessus.
- Tableau de bord web optionnel (`web/dashboard.py`, `web/dashboard_server.py`), devenu centre de
  configuration : connexion Discord OAuth2 (scopes `identify guilds`, jeton jamais stocké),
  liste des serveurs gérables avec état d'installation du bot, configuration des salons/rôles par
  plateforme, vérification des permissions du bot, vitrine publique des offres (`/offres`),
  alertes personnelles et page « Compte » avec suppression des données.

## Livré — V2.1 : plateformes dans les préférences, offres exceptionnelles, stats publiques

- `/preferences` accepte désormais un filtre par **plateformes** (`steam,epic,gog,ubisoft` ;
  vide = toutes) : `/free`, les favoris et les alertes DM n'affichent plus que les plateformes choisies.
- **Offres exceptionnelles** : un jeu complet, temporaire et dont la valeur explicitement
  libellée en euros atteint `MEGA_DEAL_MIN_WORTH_EUR` est annoncé avec le bandeau
  « 🔥 OFFRE EXCEPTIONNELLE » et le détail chiffré. Aucune conversion ni estimation : une valeur
  en dollars, par exemple, ne déclenche jamais le bandeau.
- `/stats` : statistiques publiques (offres détectées, offres actives, valeur cumulée connue en
  euros, plateformes suivies, sources, serveurs, dernière vérification) — uniquement des valeurs
  réellement mesurées par le bot.
- Branding et boucle virale : pied de page « 🎁 FreeGameDrop » sur les annonces et le panneau des
  rôles, bouton « ➕ Ajouter FreeGameDrop » construit dynamiquement sur chaque annonce (fonctionne
  pour toute instance auto-hébergée, sans configuration).
- `Dockerfile` et `.dockerignore` pour l'hébergement continu (PaaS, serveur perso).
- Licence MIT.

## Livré — V2.2 : débit maîtrisé, journal sûr, surveillance et fiabilité des sources

- **Limites de débit** (`utils/rate_limits.py`) : quota par membre pour les commandes de lecture,
  quota partagé par serveur pour les actions administratives, plafond global par membre, fenêtre
  glissante et messages d'attente courtois. Les valeurs par défaut sont larges : un usage normal
  ne les remarque jamais, un abus est ralenti.
- **Respect des limites Discord** : espacement des envois dans un même salon ou vers un même
  membre, et une seule reprise quand Discord répond `429` — en tenant compte du `Retry-After`
  qu'il fournit. Le cache court des offres (`OFFER_CACHE_SECONDS`) et l'appel unique partagé
  épargnent aussi les API de sources.
- **Journal de bord** (`utils/logging_setup.py`) : événements stables `event=… clé=valeur`
  (appel de source, succès, délai dépassé, offre détectée, doublon, offre écartée, annonce
  envoyée, alerte envoyée). Les secrets sont masqués avant écriture, y compris dans les traces
  d'exception ; `LOG_FILE` ajoute un fichier à rotation et `LOG_PSEUDONYMIZE_IDS` peut remplacer
  les identifiants Discord par une empreinte stable.
- **Surveillance** (`utils/monitoring.py`, `cogs/sante.py`) : état mesuré du bot, de Discord, de
  la base et de chaque source ; `/sante` affiche le rapport et `/api/health` l'expose en JSON pour
  une supervision externe.
- **Alertes automatiques** : source tombée (`SOURCE_DOWN_AFTER_MINUTES`), base injoignable, tâche
  arrêtée, connexion Discord dégradée ou perdue, pic d'erreurs — avec anti-spam
  (`MONITOR_ALERT_COOLDOWN_MINUTES`) et message de rétablissement. Le battement de cœur est
  enregistré en base pour qu'une alerte puisse partir même si Discord est coupé.
- **Sources fiables, sans faux positif** : une offre n'est annoncée que si elle est réellement
  présentable — identifiant et titre présents, lien `http(s)` valide, date de fin encore future,
  et statut non contredit par la source (`free_verified`, déduit du statut GamerPower et du prix
  réellement nul côté Epic Games Store). Une offre écartée est journalisée avec son motif.
- **Tests de panne et de régression** (331 tests) : API indisponible, réponse illisible, délai
  dépassé, base injoignable, `429` Discord, offre expirée ou non active, quotas atteints, journaux
  contenant un token.

## Livré — V2.3 : identité visuelle FreeGameDrop et embeds repensés

- **Identité de marque** (`utils/design.py`, documentée dans `DESIGN.md`) : FreeGameDrop en trois
  mots (**Gaming — Moderne — Premium**), sous la marque mère Orvex restée discrète
  (« 🎁 FreeGameDrop · par Orvex » en pied de page).
- **Palette** : couleur principale `#7C3AED` (boutons, liens, accents, filet des embeds), couleur
  secondaire `#22D3EE` (stats, catégories, détails), neutres pour un thème sombre sans noir pur
  (`#0B0E14` / `#121622` / `#1A1F2E` / `#F2F4F8` / `#9AA3B5` / `#272E42`).
- **Couleurs plateformes séparées de la marque** : Steam `#66C0F4`, Epic `#D9D9D9`, GOG `#86328B`,
  Ubisoft `#0070FF` — utilisées uniquement en badges, rôles et filtres ; l'embed d'une offre
  porte toujours la couleur de la marque, jamais celle d'une plateforme.
- **Typographie** : Inter partout, échelle H1/H2/H3/Body/Small/Button/Caption.
- **Boutons** : un seul langage (primaire / secondaire / danger / désactivé ; rayon 10 px,
  hauteur 40 px, états hover/active).
- **Images** : présentation cohérente (ratio 16:9, `object-fit: cover`, coins 12 px) sur le
  dashboard ; image pleine largeur dans les embeds.
- **Badges** : `GRATUIT`, plateforme, `NOUVEAU`, `SE TERMINE BIENTÔT`, `EXPIRÉ`.
- **Embeds repensés** (`utils/embeds.py`) : hiérarchie « quoi → jeu → prix → plateforme →
  échéance → action », titre = nom du jeu, prix barré → GRATUIT, badge plateforme, urgence
  🟢 > 24 h / 🟡 < 24 h / 🟠 < 6 h / 🔴 < 1 h, CTA principal « 🎁 Récupérer le jeu » vers la page
  officielle, bouton secondaire « ➕ Ajouter FreeGameDrop », branding discret en pied.
- **Variantes d'embed** : nouvelle offre, « 🔥 SE TERMINE BIENTÔT » (détection auto < 6 h),
  « 🔄 OFFRE PROLONGÉE », « ❌ OFFRE TERMINÉE » (gris, pour l'historique) — un seul squelette,
  testé pour Steam, Epic, GOG et Ubisoft.
- **Dashboard** : thème sombre et police issus des tokens (`css_variables()`), boutons et
  badges de marque, vignettes d'offres 16:9, échéance colorée selon l'urgence.

## Prochains lots

### V2 — compléments

1. Digest quotidien activable par serveur, puis récapitulatif hebdomadaire.
2. ~~Offres « Mega Deal » à partir d'un seuil de valeur configuré côté serveur (en plus du seuil personnel déjà disponible via `/preferences`).~~ Livré en V2.1 côté annonce (`MEGA_DEAL_MIN_WORTH_EUR`) ; reste à rendre le seuil configurable par serveur.
3. Modèles d'annonces configurables, commande de test sans fausse annonce dans les statistiques, et salon de logs facultatif.
4. File d'envoi et limitation de débit pour respecter les limites Discord à grande échelle.

### V3 — données enrichies et autres sources

1. Sources supplémentaires (ex. Prime Gaming, GOG) normalisées dans le même format d'offre commun.
2. Historique des prix seulement à partir de relevés effectivement observés par le bot ; ne pas inventer un prix historique avant le premier relevé.
3. Recommandations basées sur les préférences choisies par le membre, avant d'envisager de l'apprentissage automatique.
4. ~~Tableau de bord web : gestion des préférences et alertes personnelles depuis l'interface, pas uniquement en lecture seule.~~ Livré : pages « Serveurs », « Offres », « Alertes » et « Compte ».

## V4 — Collection et expérience étendue

- Profils, XP, badges et classements uniquement à partir d'actions réellement observées dans le bot.
- Une pression sur « récupérer » ne prouve pas que le jeu a été réclamé : toute statistique de collection ou d'argent économisé devra être présentée comme déclarative, ou confirmée explicitement par l'utilisateur.
- Traductions des messages et préférences de langue.
- API publique et offre premium après définition des besoins d'hébergement, de sécurité et de confidentialité.

## Limites actuelles des données

L'API GamerPower et l'API de l'Epic Games Store fournissent des champs tels que le titre, les
plateformes, la valeur annoncée, une description, des liens et parfois une date de fin. Les genres
ne sont retenus que lorsqu'une source les fournit explicitement ; aucune note utilisateur, aucun
nombre de joueurs ni aucune confirmation de réclamation ne sont disponibles. Ces éléments ne
seront affichés qu'après intégration d'une source adaptée ou d'une saisie clairement identifiée
comme déclarative.

## Principes de réalisation

- Pas d'intent Discord privilégié requis par les fonctionnalités actuelles.
- Ne stocker que les champs utiles, expliquer chaque donnée et offrir une suppression côté utilisateur.
- Réponses éphémères pour les favoris et les préférences personnelles.
- Pas de permissions `Administrator` pour le bot.
- Une source d'offres en panne ne doit jamais empêcher les autres de fonctionner.
- Chaque lot ajoute des tests hors ligne et met à jour le README avant de passer au suivant.

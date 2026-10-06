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
- Tableau de bord web optionnel (`web/dashboard.py`, `web/dashboard_server.py`), avec connexion
  Discord OAuth2 (scope `identify` uniquement) et statistiques publiques en lecture seule.

## Prochains lots

### V2 — compléments

1. Digest quotidien activable par serveur, puis récapitulatif hebdomadaire.
2. Offres « Mega Deal » à partir d'un seuil de valeur configuré côté serveur (en plus du seuil personnel déjà disponible via `/preferences`).
3. Modèles d'annonces configurables, commande de test sans fausse annonce dans les statistiques, et salon de logs facultatif.
4. File d'envoi et limitation de débit pour respecter les limites Discord à grande échelle.

### V3 — données enrichies et autres sources

1. Sources supplémentaires (ex. Prime Gaming, GOG) normalisées dans le même format d'offre commun.
2. Historique des prix seulement à partir de relevés effectivement observés par le bot ; ne pas inventer un prix historique avant le premier relevé.
3. Recommandations basées sur les préférences choisies par le membre, avant d'envisager de l'apprentissage automatique.
4. Tableau de bord web : gestion des préférences et alertes personnelles depuis l'interface, pas uniquement en lecture seule.

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

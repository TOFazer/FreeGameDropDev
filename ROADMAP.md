# FreeGameDrop — feuille de route

Le projet avancera par lots testables. Les fonctions ci-dessous ne sont pas toutes annoncées comme disponibles : seul le lot marqué **Livré** est implémenté dans le code actuel.

## Livré — V1.5, lot 1 : catalogue léger et favoris

- `/free` : parcourt en privé les offres retournées par GamerPower, avec pagination et lien de récupération.
- Bouton ❤️ dans le navigateur pour ajouter ou retirer une offre des favoris.
- `/favoris` : consulte et retire ses favoris, en réponse éphémère.
- `/mes-donnees` : demande confirmation puis efface les favoris associés à l'identifiant Discord de l'utilisateur.
- Enregistrement d'un sous-ensemble des informations publiques des offres, sans nom d'utilisateur, message privé ni preuve de réclamation.
- Les offres publiques non favorites expirées du catalogue sont nettoyées après 90 jours ; une offre reste disponible tant qu'un utilisateur l'a en favori.

## V1.5 — Prochains lots

### Lot 2 : historique, recherche et statistiques fiables

- `/historique` pour les offres enregistrées récemment.
- `/recherche` par titre et filtres de plateforme.
- `/stats` pour compter les offres et afficher la valeur annoncée quand le prix est fourni.
- Préciser la portée et la période de chaque statistique ; ne pas présenter une offre détectée comme un jeu effectivement réclamé.

### Lot 3 : préférences de notifications

- Préférences de plateforme par membre, en complément des rôles du serveur.
- Plages silencieuses et choix du fuseau horaire.
- Suppression facile des préférences et commandes privées/éphémères pour éviter d'exposer les données personnelles.

## V2 — Fonctions communautaires et annonces

1. Digest quotidien activable par serveur, puis récapitulatif hebdomadaire.
2. Offres « Mega Deal » à partir d'un seuil de valeur configuré ; alertes de fin d'offre uniquement si activées par le serveur.
3. Modèles d'annonces configurables, commande de test sans fausse annonce dans les statistiques, et salon de logs facultatif.
4. Résilience renforcée : validation de la réponse source, reprise avec délai, cache et file d'envoi pour respecter les limites Discord.

## V3 — Données enrichies et autres sources

1. Normaliser plusieurs fournisseurs dans un format d'offre commun, en gardant la provenance.
2. Ajouter DLC, extensions et autres types uniquement quand une source permet de les distinguer correctement.
3. Historique des prix seulement à partir de relevés effectivement observés par le bot ; ne pas inventer un prix historique avant le premier relevé.
4. Recommandations basées sur les préférences choisies par le membre, avant d'envisager de l'apprentissage automatique.

## V4 — Collection et expérience étendue

- Profils, XP, badges et classements uniquement à partir d'actions réellement observées dans le bot.
- Une pression sur « récupérer » ne prouve pas que le jeu a été réclamé : toute statistique de collection ou d'argent économisé devra être présentée comme déclarative, ou confirmée explicitement par l'utilisateur.
- Traductions des messages et préférences de langue.
- Éventuellement un dashboard web, une API publique et une offre premium après définition des besoins d'hébergement, de sécurité et de confidentialité.

## Limites actuelles des données

L'API GamerPower fournit des champs tels que le titre, les plateformes, la valeur annoncée, une description, des liens et parfois une date de fin. Elle ne constitue pas une source fiable pour les notes utilisateurs, les genres, le nombre de joueurs, ni la confirmation qu'une personne a réclamé le jeu. Ces éléments ne seront affichés qu'après intégration d'une source adaptée ou d'une saisie clairement identifiée comme déclarative.

## Principes de réalisation

- Pas d'intent Discord privilégié requis par les fonctionnalités actuelles.
- Ne stocker que les champs utiles, expliquer chaque donnée et offrir une suppression côté utilisateur.
- Réponses éphémères pour les favoris et les préférences personnelles.
- Pas de permissions `Administrator` pour le bot.
- Chaque lot ajoute des tests hors ligne et met à jour le README avant de passer au suivant.

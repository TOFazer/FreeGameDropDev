# Phase 1 — installation et stabilité

## État au 7 octobre 2026

Validation automatisée locale : tests sans token Discord, sans serveur réel.
Le seuil « installation en moins de 60 secondes » reste un **objectif à mesurer**,
pas une garantie validée par les tests unitaires.

### Corrections livrées

- Accueil à l'arrivée du bot dans un salon accessible ; repli sur les autres salons.
- `/setup-auto` propose Steam et Epic par défaut, explique la relance et les accès optionnels.
- Vérification effective des permissions administrateur sur les commandes et sur le panneau de configuration.
- Prévalidation des permissions du bot, erreurs Discord lisibles, instruction de reprise.
- Verrou par serveur pour sérialiser deux configurations ; verrou des vérifications pour éviter
  deux envois simultanés dans une même instance du bot.
- Réparation des salons, rôles et panneaux supprimés ; panneau édité par identifiant persistant.
- Plateformes décochées désactivées dans le routage, salons masqués et réactivables.
- Première vérification limitée au serveur configuré, sans lancer les DM/rappels des autres serveurs.
- Refus d'un salon homonyme non enregistré : il faut le renommer, sans modifier son contenu ni ses accès.
- Refus d'attribuer automatiquement un rôle doté de permissions.
- Invitation et dashboard partagent les permissions minimales. Lecture d'historique et modération facultatives.
- Données Epic malformées isolées ; identifiants absents ignorés ; liste de sources vide respectée.
- Les trois types d'alertes continuent indépendamment si l'un échoue.
- Journal d'événements `event=… clé=valeur` : appels de source, succès, délais dépassés, offres
  détectées/écartées/dupliquées, annonces et alertes ; secrets masqués avant écriture.
- Limites de débit par membre et par serveur, espacement des envois Discord et reprise après `429`.
- Surveillance : `/sante` et `/api/health` distinguent une source indisponible d'une source sans
  offre (dernier succès, nombre d'offres, latence, erreurs), avec alertes et rétablissement.
- Anti faux positifs : une offre terminée, non active selon sa source ou sans titre n'est plus
  annoncée ; chaque rejet est journalisé avec son motif.

## Registre des points ouverts — lancement non certifié

| Gravité | Point | Validation / action restante |
| --- | --- | --- |
| Important | Crash entre une création Discord et l'écriture SQLite | Pas de transaction distribuée. Un salon orphelin homonyme est refusé proprement ; le renommer avant reprise. |
| Important | Envoi Discord réussi puis crash avant mémorisation | Doublon possible après redémarrage ; les verrous ne couvrent qu'un processus. N'exécuter qu'une instance sur la base. |
| Important | `/reset-all` partiellement refusé | La configuration est encore effacée même si des ressources n'ont pas été supprimées. Vérifier/nettoyer les ressources avant de relancer. |
| Important | Notifications personnelles « fin proche » | Le filtre temporel existant doit être revu avant de certifier cette fonctionnalité. |
| Mineur | Redémarrage alors qu'un panneau éphémère est ouvert | Le panneau ne reprend pas : relancer `/setup-auto`. Les identifiants enregistrés sont conservés. |
| Mineur | Ancien panneau sans identifiant enregistré, sans lecture d'historique | Un nouveau panneau est publié ; supprimer manuellement l'ancien si nécessaire. |
| Mineur | Alertes de surveillance reçues uniquement si Discord répond | Si Discord est coupé, l'alerte reste dans le journal et `/api/health` prend le relais (supervision externe). Aucun envoi hors Discord n'est prévu. |

Les tests ne justifient donc pas une annonce « zéro bug connu » ou « prêt pour lancement ».

## Recette Discord réelle (à cocher)

- [ ] Une personne extérieure ajoute le bot sans documentation : chronométrer jusqu'à la confirmation.
- [ ] Vérifier l'accueil et le lien OAuth sans permission Administrateur ni intent privilégié.
- [ ] Choisir Steam/Epic ; vérifier les rôles, accès et une annonce réelle s'il existe une offre.
- [ ] En l'absence d'offre, vérifier le message explicatif et attendre la prochaine vérification.
- [ ] Cliquer sur les rôles avec un compte membre ; vérifier ajout, retrait et visibilité.
- [ ] Relancer ; décocher Epic puis le réactiver : aucun nouveau salon ni panneau.
- [ ] Supprimer un salon, un rôle, puis le panneau et relancer après chaque suppression.
- [ ] Deux administrateurs confirment en même temps ; la dernière configuration appliquée gagne.
- [ ] Retirer les permissions admin pendant l'ouverture du menu : le clic est refusé.
- [ ] Retirer Gérer les rôles au bot et déplacer son rôle sous un rôle de plateforme.
- [ ] Provoquer une panne Epic puis GamerPower : vérifier que l'autre source continue.
- [ ] Tester les homonymes ; aucun salon existant non enregistré ne doit être modifié.
- [ ] Redémarrer pendant le setup : relancer la commande et inspecter les éventuels éléments orphelins.
- [ ] `/sante` : vérifier les lignes Bot/Discord/Base/Sources et la cohérence des horodatages.
- [ ] Configurer un salon d'alertes, provoquer une panne de source et vérifier l'alerte puis le
  message de rétablissement (et l'absence de répétition avant le délai anti-spam).
- [ ] Demander `/free` plusieurs fois très vite et vérifier le message d'attente de la limite.
- [ ] Lire le journal : aucun token, aucune adresse e-mail, aucune URL de webhook en clair.

### Recette de séparation DEV / PROD (voir ENVIRONMENTS.md)

- [ ] Démarrer avec un `DISCORD_APPLICATION_ID` étranger au jeton : le bot refuse de démarrer
  (« ❌ Discord application mismatch ») sans tenter la moindre connexion.
- [ ] Démarrer avec `ENVIRONMENT=development` et `DB_PATH=data/freegamedrop-prod.db` : refus.
- [ ] Démarrer avec `ENVIRONMENT` ≠ `EXPECTED_ENVIRONMENT` : refus (`Environment mismatch`).
- [ ] Démarrer normalement : les lignes `[DEVELOPMENT] …` annoncent environnement, base et
  application ; `/info` affiche « 🧪 Development » ; le tableau de bord affiche 🧪 FreeGameDrop DEV.
- [ ] Activer `MAINTENANCE_MODE=true` : la veille automatique ne publie plus rien
  (`event=check.skipped`), `/test-jeux` fonctionne toujours.
- [ ] Vérifier que `data/freegamedrop-dev.db` existe en local, que `git status` ne montre ni
  `.env` ni `*.db`, et que le conteneur DEV utilise le volume `freegamedrop-dev-data`.

Commandes de contrôle : `pytest`, `ruff check .`, `git diff --check`,
`docker compose -f docker-compose.dev.yml config`.

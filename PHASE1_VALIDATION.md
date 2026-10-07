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

## Registre des points ouverts — lancement non certifié

| Gravité | Point | Validation / action restante |
| --- | --- | --- |
| Important | Crash entre une création Discord et l'écriture SQLite | Pas de transaction distribuée. Un salon orphelin homonyme est refusé proprement ; le renommer avant reprise. |
| Important | Envoi Discord réussi puis crash avant mémorisation | Doublon possible après redémarrage ; les verrous ne couvrent qu'un processus. N'exécuter qu'une instance sur la base. |
| Important | Source indisponible et source sans offre renvoient toutes deux une liste vide | Les logs distinguent les pannes, mais pas encore d'indicateur utilisateur fiable par source. Ne pas afficher de faux voyant vert par plateforme. |
| Important | `/reset-all` partiellement refusé | La configuration est encore effacée même si des ressources n'ont pas été supprimées. Vérifier/nettoyer les ressources avant de relancer. |
| Important | Notifications personnelles « fin proche » | Le filtre temporel existant doit être revu avant de certifier cette fonctionnalité. |
| Mineur | Redémarrage alors qu'un panneau éphémère est ouvert | Le panneau ne reprend pas : relancer `/setup-auto`. Les identifiants enregistrés sont conservés. |
| Mineur | Ancien panneau sans identifiant enregistré, sans lecture d'historique | Un nouveau panneau est publié ; supprimer manuellement l'ancien si nécessaire. |

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

Commandes de contrôle : `pytest`, `ruff check .`, `git diff --check`.

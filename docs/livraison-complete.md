# Livraison complète RECETTE et PREPROD

Procédure standard inchangée : `./wavy install recette` ou `./wavy install preprod`.

Le moteur commun conserve le verrou de l’environnement pendant les précontrôles existants, une seule sauvegarde coordonnée, sa vérification d’intégrité et l’application des 13 références du manifeste. Il réutilise `backup-db.sh` en RECETTE et `backup-preprod.sh` en PREPROD ; le chiffrement et la signature PREPROD restent obligatoires. Les migrations, contrôles de santé, smoke tests et protections propres à chaque environnement restent actifs.

Une livraison PREPROD complète ne déclenche plus une sauvegarde par composant. Un déploiement unitaire effectué hors de cette livraison conserve sa propre sauvegarde. Aucune option publique ne permet de sauter la sauvegarde.

Un bilan privé dans `deployments/` conserve les images initiales, les références cibles, le lot vérifié, la phase et les composants terminés. En cas d’erreur, la commande retourne un code non nul et précise la phase. Le lot et les lots incomplets sont conservés ; aucune restauration, purge ou reprise automatique n’est exécutée. La suppression de sauvegardes nécessite un accord distinct.

Après interruption, lire le bilan et vérifier les images effectivement actives avant toute reprise autorisée. Une nouvelle livraison crée un nouveau point coordonné de l’état courant ; elle ne réutilise pas automatiquement un lot incomplet. Un rollback des données exige une décision explicite et la restauration coordonnée des cinq bases et des documents avec des images compatibles.

La validation automatisée exerce les mêmes scripts dans un environnement isolé avec services simulés : ordre des 13 composants, sauvegarde unique, intégrité, échec de sauvegarde, échec intermédiaire et interruption. Elle ne remplace pas une validation fonctionnelle après installation autorisée.

## Différences conservées et convergence

| Étape | RECETTE | PREPROD | Parcours commun préparé |
|---|---|---|---|
| Exclusion mutuelle | Verrou RECETTE et exclusion session MSI | Verrou d’opération et réservations PREPROD | Verrou conservé du précontrôle à la fin |
| Validation de release | Configuration, images/digests et stockage | Promotion RECETTE acceptée, OCI, digests, isolation et contexte smoke | Précontrôles existants avant le lot unique |
| Sauvegarde | Cinq dumps + justificatifs, suspension des writers, manifeste d’intégrité | Cinq dumps + Contrats/Notes, suspension des writers, chiffrement et manifeste signé | Un appel au provider existant et vérification du lot |
| Application | Compose complet avec attente de santé | Remplacements unitaires épinglés au digest | Même coordination ; application propre à chaque environnement conservée |
| Validation après application | Fronts, migrations, Nginx, état runtime | Flyway, fronts, Nginx, santé des API, smoke, image active et historique pour chaque composant | Aucun contrôle existant retiré |
| Échec / retour | Journal d’installation | Journal par composant et caches d’images précédentes | Code non nul, phase/composant signalés, lot conservé, aucune restauration automatique |

Ordre PREPROD : Socle API, Tiers API, Contrats API, Factures API, Trésorerie API, Gateway, Socle Front, Tiers Front, Contrats Front, Factures Front, Trésorerie Front, PWA, ERP Shell. Les treize images sont celles des manifestes validés ; aucune image n’est construite et aucun digest n’est réécrit.

## Reprise après promotion partielle

La même commande `./wavy install preprod` effectue les précontrôles, lit les références/IDs des treize conteneurs actifs et vérifie les logs Flyway depuis le démarrage courant des cinq API avant toute sauvegarde ou remplacement. Une erreur de migration ou une lecture impossible arrête la reprise. Après remplacement, le même contrôle Flyway est conservé.

La reprise crée un seul **nouveau** lot coordonné de l’état partiel courant, puis réapplique les treize cibles dans l’ordre, y compris les composants déjà à la cible. Elle ne suppose pas qu’un ancien journal décrit encore le runtime. Chaque invocation autorisée possède son lot et son bilan ; les lots et bilans des tentatives précédentes sont conservés. Aucun saut de composant, marqueur de succès forcé ou restauration implicite n’est introduit.

Les historiques et leur sauvegarde indépendante ne sont ni purgés ni déplacés. Les scripts de restauration restent distincts et soumis à confirmation ; aucun changement de secrets, de volumes ou de paramètres applicatifs n’est inclus.

## Portée et limites

Le contrôle Flyway réutilise la détection existante des erreurs dans les logs ; il ne remplace pas une expertise SQL des schémas ni un exercice de restauration. Une coupure électrique ou un SIGKILL ne permet pas aux traps de reprendre les writers : vérifier alors les services avant de relancer. L’arrêt gracieux attend le nettoyage des scripts ; il ne force pas leur destruction. Une migration incompatible impose une décision de restauration coordonnée explicite.

Le parcours peut servir de base commune à une future PRODUCTION, mais seules RECETTE et PREPROD sont acceptées ; aucun déploiement production n’est activé. Les essais isolés ne constituent pas une nouvelle installation distante ni une validation fonctionnelle PREPROD.

## Périmètre des fichiers préparés

- Coordination : `scripts/install.sh`, nouveaux `scripts/delivery_batch.py`, `scripts/delivery-preflight.sh`, `scripts/delivery-apply.sh`.
- Adaptation PREPROD : `scripts/_preprod.sh`, `scripts/preprod_operation.py`, `scripts/release-preprod.sh`, `scripts/backup-preprod.sh`.
- Non-régression : nouveau `scripts/test-delivery-batch.py`, adaptations de `scripts/test-delivery.py`, `scripts/test-preprod-nginx.py`, `scripts/test-preprod-backup-transition.py`.
- Exécution systématique en CI : `.github/workflows/preprod-validation.yml`.
- Documentation : ce document, `README_PREPROD.md`, `README_RECETTE_DOCKER.md` ; l’inventaire opérationnel daté reste local et est exclu de la publication.

Les autres travaux locaux Anthropic et Windows sont hors de ce correctif. `backup-db.sh`, les scripts de restauration, les manifestes, les digests et les historiques existants ne sont pas modifiés par cette préparation.

## Résultats MSI — 4 novembre 2026

Copie Git temporaire contenant uniquement les fichiers candidats, services Docker/SQL simulés, scripts réels et chiffrement réel : **164 tests Python réussis**, tests d’historique version/digest réussis, syntaxe Bash et `git diff --check` conformes.

Les douze tests du parcours PREPROD couvrent notamment : treize composants avec un seul nouveau lot (cinq dumps et une archive), état initial déjà partiellement promu, conservation des lots/historiques, sauvegarde défaillante avec reprise des writers, échec d’application avec composant/code explicites, interruption SIGTERM pendant le déploiement puis reprise par la même commande, refus avant sauvegarde lorsque les logs Flyway courants signalent une erreur ou sont inaccessibles. La reprise conserve le premier lot et crée exactement un lot supplémentaire pour la nouvelle invocation. Les six tests du coordinateur couvrent aussi RECETTE, l’intégrité et l’interruption pendant la sauvegarde.

Aucun accès VM ni installation réelle pendant cette finalisation. Aucune suppression de sauvegarde ou changement d’image/digest. La publication de ce correctif est autorisée ; toute installation distante reste distincte et n’est pas exécutée ici.

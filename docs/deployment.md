# Déploiement contrôlé Wavy

## Architecture transitoire

Les scripts supportent deux modes explicitement déclarés par environnement et
composant dans `deployment_mode()` (`scripts/_common.sh`). Ils ne déduisent
jamais le mode d'un tag présent dans le cache Docker.

- **IMAGE** est la cible. Une image GHCR déjà construite est identifiée par un
  tag dans `versions/<environnement>.env` et par un digest actif dans
  `versions/<environnement>.digests`.
- **SOURCE** est transitoire. Le script conserve le build depuis le
  `build.context` Compose et le contrôle du dépôt Git local.

À ce stade, seul `recette/tresorerie-api` est en mode IMAGE. Les douze autres
composants et tous les composants locaux restent en mode SOURCE. PREPROD reste
désactivée dans les scripts : la logique commune sait charger ses deux manifests
mais aucune bascule ni aucun déploiement PREPROD n'est réalisé.

## Configuration et secrets

Compose reçoit séparément la configuration et les versions :

```bash
docker compose \
  --env-file .env.recette \
  --env-file versions/recette.env \
  -p wavy-recette \
  -f docker-compose.recette.yml ...
```

`.env.recette` reste réservé à la configuration d'environnement, y compris les
secrets locaux. `versions/recette.env` contient le registre et les tags, sans
secret. `versions/recette.digests` contient le digest attendu pour la version
active et n'est pas passé à Compose.

## Version active et historique validé

`versions/recette.env` exprime l'état désiré actuellement. Le digest actif qui
lui correspond reste dans `versions/recette.digests`. Ces deux fichiers peuvent
évoluer lors de la préparation d'une nouvelle livraison.

Chaque version déployée avec succès est aussi conservée dans un historique par
composant, par exemple :

```text
versions/history/recette/tresorerie-api.tsv
version  digest  commit  date_validation
```

Cet historique est append-only : une version absente est ajoutée après toutes
les validations du déploiement. Une version déjà présente avec le même digest
n'est pas dupliquée. Si son digest diffère, l'opération est refusée ; une
validation existante n'est jamais réécrite silencieusement.

Une entrée historique signifie que le couple tag/digest a réellement passé le
pull, le contrôle de digest, le démarrage, Flyway le cas échéant, les
healthchecks et les smoke tests. La simple présence d'un tag dans GHCR n'est
jamais une validation. Une entrée ne peut être créée que :

- automatiquement par `deploy.sh` après un déploiement IMAGE réussi ;
- exceptionnellement par un opérateur DevOps habilité, après revue à deux
  personnes et conservation des preuves équivalentes dans le journal de
  changement.

Une saisie manuelle ne doit jamais contourner un échec de déploiement ou de
digest. Les modifications directes d'une ligne existante sont interdites.

La fonction commune suivante retourne le digest exact ou termine en erreur :

```bash
get_validated_digest recette tresorerie-api 0.1.0-79ffe8a
```

Une image GHCR privée nécessiterait préalablement un `docker login ghcr.io` avec
un token limité à `read:packages`, transmis par entrée standard. Le token ne doit
jamais être écrit dans Git, un manifest, une commande historisée ou les logs.

## Déploiement SOURCE

```bash
./scripts/deploy.sh recette factures-api
```

Le dépôt source doit être propre, sauf utilisation explicite de
`--allow-dirty`. Le script sauvegarde les bases pour une API avec base, exécute
`docker compose build`, recrée uniquement le service avec `--no-deps`, contrôle
sa santé, Flyway, les healthchecks et les smoke tests.

## Déploiement IMAGE

```bash
./scripts/deploy.sh recette tresorerie-api
```

Le script refuse une version ou un digest vide, vérifie que le tag distant
existe, effectue le pull et compare le `RepoDigest` au digest validé. Toute
différence interrompt le déploiement avant la recréation du conteneur.

Après validation du digest, l'image active reçoit un tag local horodaté sous
`wavy-rollback-cache/`. Le script sauvegarde les bases, n'exécute aucun build et
recrée uniquement le service ciblé avec `--no-deps --force-recreate --pull
never`. L'ID de l'image réellement exécutée est comparé à celui de l'image
validée.

## Rollback

Pour un composant SOURCE, la cible reste un commit Git et le mécanisme worktree
temporaire reste disponible :

```bash
./scripts/rollback.sh recette factures-api <commit>
```

Pour un composant IMAGE, la cible est un tag explicite :

```bash
./scripts/rollback.sh recette tresorerie-api 0.1.0-79ffe8a
```

Le script recherche d'abord obligatoirement le digest de la version dans
l'historique validé. Une version inconnue est refusée avant le pull et avant
toute recréation. Il vérifie ensuite l'existence du tag, le tire et contrôle son
digest. Un
override Compose temporaire sélectionne l'image cible sans modifier le manifest.
Il affiche les images actuelle et cible, demande confirmation, crée un nouveau
tag de sécurité puis recrée uniquement le service. Aucun build n'est exécuté en
mode IMAGE.

Le rollback vers une ancienne version utilise donc directement son entrée
historique, sans demander de digest à l'opérateur et sans modifier la version
active déclarée.

## Sauvegardes PostgreSQL

Les sauvegardes utilisent des répertoires `AAAA-MM-JJ_HHMMSS`. Si deux demandes
arrivent dans la même seconde, un suffixe numérique (`-01`, `-02`, etc.) garantit
une destination distincte. Chaque destination contient les dumps, le manifest
historique et un `metadata.txt` sans secret avec la date, l'environnement, le
composant, sa version, l'utilisateur et la liste des bases.

Une sauvegarde préalable facilite une décision DBA, mais un rollback applicatif
n'est jamais un rollback de base. Les scripts ne restaurent jamais PostgreSQL
automatiquement.

### Rétention locale des sauvegardes

`scripts/cleanup-backups.sh` conserve par défaut les 20 dernières sauvegardes
reconnues **ou** toute sauvegarde âgée de 14 jours au maximum. Une sauvegarde
n'est supprimable que si elle dépasse simultanément ces deux protections. Les
valeurs sont configurables :

```bash
WAVY_BACKUP_RETENTION_DAYS=14
WAVY_BACKUP_RETENTION_COUNT=20
```

Le script ne considère que les répertoires directs de `backups/` nommés
`AAAA-MM-JJ_HHMMSS` avec un éventuel suffixe `-NN`. Il ne suit pas les liens et
ignore les noms anciens ou inconnus. Son mode par défaut est le dry-run :

```bash
./scripts/cleanup-backups.sh --dry-run
./scripts/cleanup-backups.sh --execute
```

### Rétention des tags de rollback

`scripts/cleanup-rollback-cache.sh` conserve par défaut les 5 tags horodatés les
plus récents pour chaque dépôt local
`wavy-rollback-cache/<environnement>-<composant>`. La valeur est configurable
avec `WAVY_ROLLBACK_CACHE_RETENTION_COUNT`.

Seuls les tags dont le nom se termine par `AAAAMMJJTHHMMSS` sont candidats. Les
tags non reconnus sont ignorés. Un tag pointant vers l'image d'un conteneur,
même arrêté, est toujours protégé. Supprimer un tag de cache ne supprime pas une
image GHCR validée par simple absence d'utilisation : un tag qui constitue la
seule référence locale de son image est également protégé. Le mode par défaut
est là aussi `--dry-run`; `--execute` est nécessaire pour supprimer.

Les scripts de rétention ne touchent jamais aux volumes, aux données
PostgreSQL, aux manifests de versions ou à l'historique validé.

## Tests locaux de l'historique

```bash
./scripts/test-version-history.sh
```

Le test travaille sous un répertoire temporaire et vérifie l'ajout, la lecture,
l'idempotence, les refus de conflit et de version inconnue, l'absence de fichier,
l'en-tête TSV et le verrouillage `flock`. Il ne lit ni ne modifie l'historique
réel.

## Flyway et validations

Pour une API avec base, déploiement et rollback créent une sauvegarde préalable,
mais ne restaurent jamais PostgreSQL automatiquement. Ils ne modifient aucune
migration et n'exécutent jamais `flyway repair`.

Les logs produits depuis le début de l'opération sont refusés s'ils contiennent :

```text
checksum mismatch
Validate failed
migration failed
FlywayValidateException
FlywayMigrateException
```

Le script attend ensuite le healthcheck Docker, exécute
`scripts/healthcheck.sh`, puis `scripts/smoke-test.sh`.

## Journalisation

Déploiements et rollbacks sont ajoutés à `deployments/history.tsv` :

```text
date action environnement composant mode commit version digest résultat utilisateur
```

Les anciennes lignes de déploiement sont migrées vers ce schéma à la première
écriture. Aucun secret n'est journalisé.

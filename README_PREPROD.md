# Préproduction Wavy

La préproduction est une installation neuve et isolée. Elle n'importe jamais de dump de recette et utilise exclusivement les migrations Flyway présentes dans les images versionnées.

## Préparer et démarrer

1. Publier toutes les images avec **le même tag immuable** (version ou SHA Git) dans le registry.
2. Copier `.env.preprod.example` vers `.env.preprod`, remplacer chaque `CHANGE_ME`, puis limiter ses droits (`chmod 600 .env.preprod`).
3. Terminer TLS sur un reverse proxy ou load balancer devant `127.0.0.1:24443`. Le shell est le seul port publié ; les API et PostgreSQL restent privés.
4. Lancer `./wavy start preprod`, puis `./wavy health preprod`.

`start preprod` exécute d'abord `scripts/validate-preprod-config.sh` : aucun `CHANGE_ME`, tag `latest`, URL non HTTPS, SIREN invalide ou mot de passe bootstrap trop court n'est accepté.

Les fronts utilisent des URLs relatives (`/api`) : le même artefact est donc promu de préproduction en production sans recompilation liée au domaine.

Pour construire localement ou dans une CI disposant des dépôts frères, utiliser l'override `docker-compose.preprod.build.yml`. Il applique le même tag à toutes les images :

```bash
docker compose --env-file .env.preprod \
  -f docker-compose.preprod.yml -f docker-compose.preprod.build.yml build --parallel
```

Le stockage `documents-preprod` et les cinq volumes PostgreSQL sont propres à `wavy-preprod`. Aucun script de `dev/recette` ou `dev/demo-local` n'est monté ni exécuté.

## Sauvegarde et restauration

- `./scripts/backup-preprod.sh` crée cinq dumps AES-256 chiffrés sous `backups/preprod/` et applique la rétention.
- `./scripts/restore-preprod.sh backups/preprod/<horodatage>` restaure les cinq bases après confirmation puis contrôle la santé.

Une restauration doit être testée régulièrement sur une stack isolée. Pour tester une reconstruction neuve, utiliser un **runner Docker dédié sans préproduction active**, une copie temporaire de `.env.preprod` avec `COMPOSE_PROJECT_NAME=wavy-preprod-from-zero`, puis lancer :

```bash
WAVY_CONFIRM_FROM_ZERO_TEST=ERASE_EPHEMERAL_DATABASES ./scripts/test-database-from-zero.sh
```

## Garanties et responsabilités applicatives

Compose force le profil Spring `preprod`, les cookies sécurisés, les secrets externes, les images versionnées, les volumes persistants et les healthchecks. Chaque API doit conserver Flyway activé et exposer `/actuator/health`. Le Socle doit implémenter un bootstrap idempotent consommant les variables `WAVY_BOOTSTRAP_*` : tenant, société, administrateur `ADMIN_TENANT`, mot de passe à changer. Les référentiels techniques doivent être portés par de **nouvelles** migrations ; aucune migration existante ne doit être modifiée.

Les données métier sont créées uniquement par les interfaces. Le passage en production réutilise exactement les digests d'images validés ici, avec ses propres secrets, volumes, domaine et sauvegardes.

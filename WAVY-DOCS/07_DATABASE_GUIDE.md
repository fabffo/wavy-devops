# 07_DATABASE_GUIDE

## Objectif

Documenter l'organisation des bases de données, les conventions de connexion et les modes d'exécution observés dans Wavy.

## Informations trouvées dans le code

- Bases PostgreSQL locales et Docker : `wavy_socle_db`, `wavy_tiers_db`, `wavy_contrats_db`, `wavy_factures_db`.
- Scripts de création des bases locales : `scripts/create-local-dbs.sh`.
- Le module `wavy-factures-api` en local utilise H2 pour les tests/Swagger.
- Les containers PostgreSQL exposent les ports hôtes `15432`, `15433`, `15434`, `15435` en local Docker et `25432`, `25433`, `25434`, `25435` en recette.
- Les utilisateurs PostgreSQL sont `socle_user`, `tiers_user`, `contrats_user`, `factures_user`.

## Conventions observées

- Source locale : une seule instance PostgreSQL sur `localhost:5432`, plusieurs bases.
- Docker local : chaque base PostgreSQL est dans son propre conteneur avec port hôte dédié.
- Docker recette : chaque base PostgreSQL est dans son propre conteneur avec port hôte dédié différent.
- Les backends backend utilisent `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD`.
- Les sources SQL de démonstration se trouvent dans `dev/demo-local/` pour les données demo et `dev/recette/` pour les données recette.

## Observations spécifiques

- `wavy-socle-api` utilise `localhost:5432` et semble avoir un nom de base par défaut `socle_multitenant`.
- `wavy-tiers-api` et `wavy-contrats-api` ont Flyway configuré.
- `wavy-factures-api` a un mode H2 en local et PostgreSQL en recette.
- Les données de démonstration sont chargées via `load-demo-local.sh` dans `scripts/start-docker-local.sh`.

## Points à compléter

- Schéma de base complet pour chaque module.
- Etat de l'utilisation de Flyway dans `wavy-socle-api` et `wavy-factures-api`.
- Scripts de migration spécifiques aux modules.
- Configuration PostgreSQL exacte des `application-*.properties` et `application-*.yml` des backends.
- Index et contraintes métiers.

## Liens utiles

- `scripts/create-local-dbs.sh`
- `dev/demo-local/`
- `dev/recette/`
- `docker-compose.local.yml`
- `docker-compose.recette.yml`
- `.env.local.example`
- `.env.recette.example`

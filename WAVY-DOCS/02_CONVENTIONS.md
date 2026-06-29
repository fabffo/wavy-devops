# 02_CONVENTIONS

## Objectif

Rassembler les conventions matérielles observées dans le projet : ports, nommage, environnements, headers, Docker, Git et documentation.

## Informations trouvées dans le code

- Ports locaux : `8080` socle, `8081` tiers, `8082` contrats, `8083` factures, `8088` gateway.
- Ports Docker locaux exposés sur l'hôte : `18080`, `18081`, `18082`, `18083`, `18088`.
- Ports Docker fronts locaux exposés : `14200`, `14201`, `14202`, `14203`, `14204`.
- Ports Docker recette exposés : `28080`, `28081`, `28082`, `28083`, `28088`.
- Ports PostgreSQL hôtes : `15432`, `15433`, `15434`, `15435` (local Docker), `25432`, `25433`, `25434`, `25435` (recette Docker).
- Fronts conteneurs Nginx écoutent sur `80`.
- Env var conventions : `WAVY_*`, `API_UPSTREAM`, `API_BASE_URL`, `API_GATEWAY_BASE_URL`.
- Headers métiers obligatoires : `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Le gateway transmet `Authorization` et les headers métiers.
- Le front ne doit pas appeler directement les backends ; il doit passer par la gateway.

## Conventions observées

- Nom des services Docker : `wavy-socle-api-local`, `wavy-tiers-api-recette`, etc.
- Les variables des fichiers `.env.local` et `.env.recette` pilotent l'exposition des ports hôtes et la configuration des services.
- Les fichiers de configuration locales sont souvent `application-local.properties` ou `application-local.yml`.
- En recette, les profils sont `recette` ou `local` en fonction du module.
- Tous les modules backend sont des applications Spring Boot avec `pom.xml`.
- Les modules front sont des applications Angular avec `package.json`.
- Les scripts bash utilisent `set -euo pipefail`.

## Points à compléter

- Convention Git précise utilisée (branching, nomenclature, revue, commit message).
- Convention de formatage de code pour Java, TypeScript, YAML, Markdown.
- Règles de nommage des entités, tables, colonnes, DTO, API.
- Standard de tests et couverture minimum.

## Liens utiles

- `.env.local.example`
- `.env.recette.example`
- `docker-compose.local.yml`
- `docker-compose.recette.yml`
- `README_DEV_LOCAL.md`

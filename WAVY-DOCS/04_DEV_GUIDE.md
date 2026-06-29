# 04_DEV_GUIDE

## Objectif

Fournir les bonnes pratiques de développement pour Wavy, y compris les environnements de travail, les scripts disponibles et les principaux workflows sans modifier le code applicatif.

## Informations trouvées dans le code

- `scripts/start-local-tmux.sh` démarre localement les APIs et les fronts en tmux.
- `scripts/start-docker-local.sh` construit la gateway et démarre la pile Docker locale en chargeant les données de démonstration.
- `scripts/start-docker-recette.sh` construit la gateway et démarre la pile Docker recette.
- `scripts/create-local-dbs.sh` crée les bases de données locales PostgreSQL.
- `README_DEV_LOCAL.md` documente les usages manuels et Docker.
- `README_RECETTE_DOCKER.md` documente la pile recette.

## Environnements de développement

### Local manuel

- PostgreSQL unique sur `localhost:5432`
- APIs Spring Boot démarrées avec `./mvnw spring-boot:run -Dspring-boot.run.profiles=local`
- Gateway démarrée avec `./mvnw spring-boot:run -Dspring-boot.run.profiles=local`
- Fronts Angular démarrés avec `npm start`

### Docker local

- `docker compose --env-file .env.local -f docker-compose.local.yml up --build`
- Les hôtes sont exposés sur `18080`, `18081`, `18082`, `18083`, `18088`
- Les fronts sont exposés sur `14200`, `14201`, `14202`, `14203`, `14204`

### Docker recette

- `docker compose --env-file .env.recette -f docker-compose.recette.yml up -d --build`
- Les hôtes sont exposés sur `28080`, `28081`, `28082`, `28083`, `28088`
- Les fronts sont exposés sur `24200`, `24201`, `24202`, `24203`

## Scripts utiles

- `./scripts/create-local-dbs.sh` : crée les roles et bases locales PostgreSQL.
- `./scripts/start-docker-local.sh` : démarre la pile Docker locale et charge les données de démonstration.
- `./scripts/start-docker-recette.sh` : démarre la pile Docker recette.
- `./scripts/load-recette-data.sh` : charge les données de recette dans les bases.
- `./scripts/stop-docker-local.sh` / `./scripts/stop-docker-recette.sh` : arrêt de la pile.
- `./scripts/reset-local-dbs.sh` : réinitialise les bases locales.
- `./scripts/backup-recette-data.sh` : sauvegarde des données recette.

## Bonnes pratiques observées

- Utiliser le gateway pour toutes les requêtes front.
- Vérifier les ports et variables `.env` avant de démarrer Docker.
- Charger les données de démonstration avec `load-demo-local.sh` pour Docker local.
- Tester l'API health des modules via `/actuator/health` et `/api/*/health`.

## Points à compléter

- Guide de contribution code (pull requests, revues, tests). 
- Standards de développement Java/TypeScript/Angular.
- Checklists d'avant merge / intégration.
- Normes de documentation des modules.

## Références

- `README_DEV_LOCAL.md`
- `README_RECETTE_DOCKER.md`
- `scripts/`
- `docker-compose.local.yml`
- `docker-compose.recette.yml`

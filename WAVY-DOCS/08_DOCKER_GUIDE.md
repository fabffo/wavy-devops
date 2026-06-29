# 08_DOCKER_GUIDE

## Objectif

Documenter la configuration Docker et les environnements de déploiement local/recette pour Wavy.

## Informations trouvées dans le code

- Deux fichiers Docker Compose principaux : `docker-compose.local.yml` et `docker-compose.recette.yml`.
- Le `docker-compose.local.yml` contient les services PostgreSQL, backends, gateway et fronts Angular/Docker.
- Le `docker-compose.recette.yml` contient une pile recette similaire, avec des ports hôtes différents et un réseau `wavy-recette`.
- Le script `scripts/start-docker-local.sh` utilise `docker compose --env-file .env.local -f docker-compose.local.yml`.
- Le script `scripts/start-docker-recette.sh` utilise `docker compose --env-file .env.recette -f docker-compose.recette.yml`.
- Les fronts Nginx sont construits à partir des dépôts voisins et exposent le port `80` à l'intérieur du conteneur.
- `wavy-pwa` utilise un Dockerfile dédié `docker/wavy-pwa.Dockerfile`.

## Conventions observées

- `docker compose` avec `--env-file` pour injecter la configuration des ports.
- Utilisation de variables `WAVY_*` dans les compositions Docker.
- Conteneurs de bases PostgreSQL avec `healthcheck`.
- Les backends dépendent des bases de données via `depends_on` et `condition: service_healthy`.
- La gateway dépend des backends.
- Les fronts dépendent de la gateway.
- Les services sont connectés à un réseau Docker dédié : `wavy-local` ou `wavy-recette`.

## Bonnes pratiques observées

- Construire le jar `wavy-gateway` avant de démarrer la pile Docker locale/recette.
- Charger les données de démonstration après que les services soient disponibles.
- Utiliser des volumes pour les bases de données et les pièces jointes du module contrats.
- Ne pas versionner `.env.recette`.

## Points à compléter

- Guide de débogage Docker compose en cas d'échec.
- Normes de création d'images Docker et de sécurité des containers.
- Détails des volumes et du réseau Docker.
- Comment gérer les caches de build et les reconstructions partielles.

## Liens utiles

- `docker-compose.local.yml`
- `docker-compose.recette.yml`
- `scripts/start-docker-local.sh`
- `scripts/start-docker-recette.sh`
- `.env.local.example`
- `.env.recette.example`

# GATEWAY

## Objectif

Documenter le module `wavy-gateway` et son rôle de point d'entrée pour l'ensemble des API Wavy.

## Informations trouvées dans le code

- `wavy-gateway` est une application Spring Boot utilisant Spring Cloud Gateway.
- Elle route les requêtes vers `wavy-socle-api`, `wavy-tiers-api`, `wavy-contrats-api`, `wavy-factures-api`.
- Les variables d'upstream sont : `WAVY_ROUTES_SOCLE_URI`, `WAVY_TIERS_API_URI`, `WAVY_CONTRATS_API_URI`, `WAVY_FACTURES_API_URL`.
- Le gateway local écoute sur `8088`.
- Le gateway recette expose `18088` sur l'hôte et écoute sur `8088` dans le conteneur.
- Le gateway gère les CORS pour les fronts locaux et recette.

## Conventions observées

- Le gateway transmet les headers `Authorization`, `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Les fronts Angular consomment `/api/**` et ne connaissent pas l'URL des backends.
- Les routes `/api/tiers/**`, `/api/contrats/**`, `/api/factures/**` sont déclarées avant la route générique `/api/**`.

## Points à compléter

- Configuration exacte des routes dans `application.yml` ou `application-*.properties`.
- Détails du CORS réel et des filtres appliqués.
- Sécurité de la gateway.
- Catalogue complet des endpoints routés.

## Liens utiles

- `../wavy-gateway/README.md`
- `../docker-compose.local.yml`
- `../docker-compose.recette.yml`

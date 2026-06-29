# 01_ARCHITECTURE

## Objectif

Documenter l'architecture globale du projet Wavy : modules, flux, communication entre services, front/back, gateway et bases de données.

## Informations trouvées dans le code

- Le projet est composé de plusieurs modules backend et frontend, avec un orchestrateur `wavy-devops`.
- Les modules backend sont des applications Spring Boot : `wavy-socle-api`, `wavy-tiers-api`, `wavy-contrats-api`, `wavy-factures-api`, `wavy-gateway`.
- Les modules frontend sont des applications Angular : `wavy-socle-front`, `wavy-tiers-front`, `wavy-contrats-front`, `wavy-factures-front`, plus `wavy-pwa`.
- `wavy-gateway` joue le rôle de point d'entrée HTTP pour les APIs et effectue du routage vers les backends.
- Les communications entre front et backend passent via `wavy-gateway` en local et recette.
- Les données sont stockées dans PostgreSQL pour les modules socle, tiers, contrats et factures en Docker. Le module factures a un mode H2 local pour tests manuels.

## Flux principaux

- Front Angular local -> Gateway `http://localhost:8088` -> backend local `http://localhost:8080/8081/8082/8083`
- Front Angular recette -> Gateway `http://localhost:18088` -> backend recette `wavy-socle-api-recette:8080`, `wavy-tiers-api-recette:8081`, `wavy-contrats-api-recette:8082`, `wavy-factures-api-recette:8083`
- `wavy-pwa` en local utilise `http://localhost:8088/api` pour envoyer des scans au backend factures.

## Composants

- `wavy-socle-api` : identité multi-tenant, gestion des tenants, utilisateurs, société, profil, auth.
- `wavy-tiers-api` : référentiel tiers, CRUD des tiers, adresses, contacts, référentiels.
- `wavy-contrats-api` : gestion des contrats, pièces jointes, statuts, workflow contrat.
- `wavy-factures-api` : facturation, factures de vente, lignes, calculs TVA, workflow brouillon/validation/annulation, IA de scan PWA.
- `wavy-gateway` : Spring Cloud Gateway, route `/api/contexte`, `/api/tiers`, `/api/contrats`, `/api/factures`, routes compatibles vers le socle.
- `wavy-socle-front` : interface d'administration socle, login, profils.
- `wavy-tiers-front` : interface gestion des tiers, contexte, contacts.
- `wavy-contrats-front` : interface gestion des contrats et pièces jointes.
- `wavy-factures-front` : interface gestion des factures de vente.
- `wavy-pwa` : application mobile/PWA pour scanner des factures et envoyer les fichiers au backend factures via la gateway.

## Observations sur l'architecture

- Multi-tenant stateless apparent basé sur des headers HTTP.
- Gateway comme point d'entrée commun et proxy CORS.
- Fronts Angular conçus pour utiliser `API_UPSTREAM` ou `apiGatewayBaseUrl`.
- Docker local et recette alignés sur une convention de ports stable.
- Les fronts Nginx exposent toujours le port conteneur `80`.

## Points à compléter

- Diagramme d'architecture détaillé des composants et des services.
- Décisions des technologies exactes pour chaque module.
- Détails de l'architecture interne des APIs (packages, couches, entités).
- Topologie de réseau Docker et volumes partagés si besoin.

## Références

- `docker-compose.local.yml`
- `docker-compose.recette.yml`
- `README_DEV_LOCAL.md`
- `README_RECETTE_DOCKER.md`
- `README_WAVY_PWA.md`
- `README.md` de chaque module

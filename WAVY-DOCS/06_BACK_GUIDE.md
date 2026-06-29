# 06_BACK_GUIDE

## Objectif

Documenter les conventions et pratiques backend observées dans les modules Spring Boot de Wavy.

## Informations trouvées dans le code

- Backends présents : `wavy-socle-api`, `wavy-tiers-api`, `wavy-contrats-api`, `wavy-factures-api`, `wavy-gateway`.
- Chaque module utilise Maven (`pom.xml`).
- Les modules backend utilisent Spring Boot, Spring Data JPA, Spring Security, Spring Cloud Gateway pour `wavy-gateway`.
- `wavy-tiers-api` et `wavy-contrats-api` ont Flyway activé.
- `wavy-factures-api` utilise PostgreSQL en recette et H2 en profil `local`.
- `wavy-socle-api` gère l'authentification, les profils, les tenants et le contexte multi-tenant.
- `wavy-gateway` utilise des variables `WAVY_ROUTES_SOCLE_URI`, `WAVY_TIERS_API_URI`, `WAVY_CONTRATS_API_URI`, `WAVY_FACTURES_API_URL`.

## Conventions observées

- Variable d'environnement `SPRING_PROFILES_ACTIVE` ou profil Spring `local`, `docker`, `recette`, `secure`.
- Ports internes backends : 8080, 8081, 8082, 8083.
- Communication interne Docker via noms de service et ports internes.
- Les APIs backend doivent être utilisables via la gateway, pas directement depuis le front.
- Les headers métiers `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id` sont transmis par la gateway.

## Bonnes pratiques observées

- Vérifier la configuration de base de données avant le démarrage.
- Utiliser `docker compose --env-file` pour injecter les variables d'environnement.
- Tester les health checks des endpoints : `/actuator/health`, `/api/*/health`.
- En recette, utiliser un réseau Docker externe `wavy-recette` pour que les services se découvrent.

## Points à compléter

- Détails des couches backend : services, repositories, controllers, entities.
- Convention de nommage des endpoints REST.
- Gestion des erreurs et format des réponses API.
- Stratégie de logging et de monitoring.
- Détails d'authentification sur chaque module.

## Liens utiles

- `README.md` des modules backend
- `docker-compose.local.yml`
- `docker-compose.recette.yml`
- `README_DEV_LOCAL.md`

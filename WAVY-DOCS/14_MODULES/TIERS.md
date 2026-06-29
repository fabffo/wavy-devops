# TIERS

## Objectif

Documenter le module `wavy-tiers-api` et son front `wavy-tiers-front` pour la gestion du référentiel tiers.

## Informations trouvées dans le code

- `wavy-tiers-api` expose un CRUD de tiers avec adresses et contacts.
- `wavy-tiers-api` est versionné par Flyway.
- `wavy-tiers-front` est un front Angular qui utilise la gateway pour communiquer avec les APIs.
- Le front gère les rôles de tiers, les pages de liste, détail, création, modification et contexte de société.
- `wavy-tiers-front` utilise des endpoints tels que `/api/tiers`, `/api/tiers/referentiels/*`, `/api/auth/session`, `/api/profil`.

## Conventions observées

- Le front utilise `withCredentials: true` pour partager la session via cookie.
- Les headers de contexte sont ajoutés automatiquement par le front pour les appels métier.
- Le front ne doit pas appeler `wavy-tiers-api` directement.
- Les routes Angular du module incluent `/tiers`, `/tiers/nouveau`, `/tiers/:id`, `/tiers/:id/modifier`.

## Points à compléter

- Schéma de la base `wavy_tiers_db`.
- Détails métiers des rôles de tiers.
- Décisions sur les référentiels et validations.
- Structure interne des services et des composants Angular.

## Liens utiles

- `../wavy-tiers-api/README.md`
- `../wavy-tiers-front/README.md`
- `../README_DEV_LOCAL.md`

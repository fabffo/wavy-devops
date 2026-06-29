# Tiers

## Objectif

Documenter les endpoints et le comportement du module `wavy-tiers-api`.

## Informations trouvées dans le code

- `wavy-tiers-api` expose :
  - `GET /api/tiers`
  - `GET /api/tiers/{id}`
  - `POST /api/tiers`
  - `PUT /api/tiers/{id}`
  - `DELETE /api/tiers/{id}`
  - `GET /api/tiers/referentiels/roles`
  - `GET /api/tiers/referentiels/types`
  - `GET /api/tiers/referentiels/natures-organisation`
  - `GET /api/tiers/referentiels/natures-personne`
  - endpoints d'adresses et de contacts
- Le front tiers charge le profil via `/api/profil` puis ajoute les headers métiers aux requêtes.

## Conventions observées

- Le module demande les headers métiers : `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Les endpoints sensibles sont accessibles via la gateway.

## Points à compléter

- Liste complète des endpoints d'adresses et de contacts.
- Détails des structures de requête et des DTO.
- Paramètres de filtre sur `GET /api/tiers`.
- Autorisations par rôle.

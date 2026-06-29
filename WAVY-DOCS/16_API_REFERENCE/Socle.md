# Socle

## Objectif

Documenter les endpoints et le comportement du module `wavy-socle-api`.

## Informations trouvées dans le code

- `wavy-socle-api` expose :
  - `GET /api/profil`
  - `POST /api/auth/session`
  - `GET /api/auth/session`
  - `DELETE /api/auth/session`
  - endpoints d'administration `/api/tenants/**`
- Les requests de profil peuvent être faites avec Basic Auth ou cookie de session.
- Le frontend socle utilise une authentification Basic Auth et des sessions HTTP.

## Conventions observées

- Le socle gère le contexte utilisateur, tenant et société.
- Le endpoint `/api/profil` ne nécessite pas les headers métiers de contexte.
- Les endpoints d'administration utilisent probablement `ADMIN_PLATEFORME` et `ADMIN_TENANT`.

## Points à compléter

- Liste exhaustive des endpoints socle.
- Schéma des données de profil et tenants.
- Règles de sécurité spécifiques à chaque endpoint.
- Paramètres de requête et structures de réponse.

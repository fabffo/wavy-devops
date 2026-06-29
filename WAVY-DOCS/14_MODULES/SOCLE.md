# SOCLE

## Objectif

Documenter le module `wavy-socle-api` et son front `wavy-socle-front` comme socle d'identité, de contexte et d'administration.

## Informations trouvées dans le code

- `wavy-socle-api` gère l'authentification, le profil utilisateur, les tenants, les sociétés internes et les utilisateurs.
- `wavy-socle-front` est un front Angular administrant le socle.
- Le front appelle les APIs via la gateway sur `/api/**`.
- `wavy-socle-front` utilise un proxy pour rediriger `/api` vers `http://localhost:8088` en local.
- Les comptes de recette incluent `adminrecette@wavy.fr`.

## Conventions observées

- Le socle fournit un endpoint de profil `GET /api/profil`.
- Authentification via Basic Auth et sessions cookies.
- Headers métiers de contexte utilisés : `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Le front ne communique pas directement avec `wavy-socle-api`.

## Points à compléter

- Détails du modèle de données du socle.
- Schéma de base de `wavy-socle-api`.
- Décisions métier sur les rôles et l'administration des tenants.
- Détails de la sécurité et de la gestion de sessions.

## Liens utiles

- `../wavy-socle-api/README.md`
- `../wavy-socle-front/README.md`
- `../README_DEV_LOCAL.md`
- `../README_RECETTE_DOCKER.md`

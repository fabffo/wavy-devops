# 09_SECURITY_GUIDE

## Objectif

Documenter les aspects de sécurité observés dans le projet, notamment l'authentification, les headers de contexte, le CORS et les pratiques de durcissement.

## Informations trouvées dans le code

- `wavy-socle-api` gère l'authentification et le profil utilisateur.
- `wavy-tiers-api` et `wavy-contrats-api` peuvent être démarrés en mode `gateway` ou `secure`.
- Les endpoints Swagger et Actuator restent souvent ouverts.
- Le gateway transmet les headers `Authorization`, `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Le front Angular utilise `withCredentials` pour les sessions via cookies.
- En local, CSRF est désactivé temporairement pour certains endpoints de session.

## Conventions observées

- Headers métiers de contexte obligatoires : `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Le gateway n'implémente pas de sécurité propre au moment observé ; il agit comme proxy.
- Environnements `secure` et `production` existent pour les API, mais les détails ne sont pas entièrement documentés.
- Les comptes de test sont référencés dans les README.

## Bonnes pratiques observées

- Ne pas exposer directement les API backends aux fronts : utiliser la gateway.
- Valider la présence des headers de contexte métier dans les backends.
- Utiliser des profils Spring distincts selon l'environnement.
- Protéger la session via cookie `HttpOnly`, `SameSite=Lax`.

## Points à compléter

- Architecture complète de la sécurité de `wavy-socle-api`.
- Politique d'authentification et d'autorisation pour chaque module.
- CORS exacts et stratégies de `wavy-gateway`.
- Durcissement des environnements recette et production.
- Pratiques de chiffrement des secrets et des API keys.

## Références

- `wavy-socle-api/README.md`
- `wavy-tiers-api/README.md`
- `wavy-contrats-api/README.md`
- `wavy-factures-api/README.md`
- `wavy-gateway/README.md`
- `README_DEV_LOCAL.md`
- `README_RECETTE_DOCKER.md`

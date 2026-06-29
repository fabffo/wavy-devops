# ADR-001 MultiTenant

## Objectif

Documenter la décision d'utiliser un contexte multi-tenant basé sur des headers HTTP dans Wavy.

## Contexte

Le projet Wavy comporte plusieurs applications backend qui doivent fonctionner dans un environnement multi-tenant. Le socle gère les tenants, utilisateurs, et sociétés internes.

## Décision observée

- Le multi-tenant est porté par des headers HTTP : `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Ces headers sont obligatoires pour les endpoints métier des modules `wavy-tiers-api`, `wavy-contrats-api`, `wavy-factures-api`.
- La gateway transmet ces headers aux backends.

## Raisons

- Permettre un routage simple sans état serveur lourd.
- Rendre le contexte utilisateur explicite et découplé de l'authentification.
- Faciliter les appels inter-services et le test via curl.

## Conséquences

- Les APIs doivent valider la présence et la cohérence des headers.
- Le socle doit être capable de fournir ou valider le profil utilisateur en incluant le contexte tenant/société.
- Les fronts doivent conserver et transmettre ce contexte.

## Points à compléter

- Détails de la stratégie multi-tenant pour les données persistantes.
- Comment sont gérées les permissions tenant/société.
- Gestion des tenants multiples dans `wavy-socle-api`.
- Impact sur les migrations et les schémas de base.

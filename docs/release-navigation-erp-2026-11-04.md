# Correctif de navigation ERP — 4 novembre 2026

Publication ciblée de Factures Front et ERP Shell. Les liens Factures restent dans leur espace de module ; le Shell refuse une réintégration récursive dans une iframe. Les paramètres de retour, fragments et filtres utilisateur sont conservés.

## Images publiées

- `ghcr.io/fabffo/wavy-factures-front:0.2.1-7b0ef24@sha256:51c0972c6a3555ea86a24f9345bfe6280ea88e6c7ae8c8cbc4a0a50735524407`
- `ghcr.io/fabffo/wavy-erp-shell:0.2.1-f4dd5e3@sha256:a6039fee2862308df5aa035bf7fd710e2ae6c13232ecb6a2b860ac456aa516f4`

## Validation

- 233 tests unitaires réussis : 182 Factures Front et 51 ERP Shell, rejoués lors des constructions.
- 42 scénarios Chrome réussis sur MSI : navigation, retours, filtres, actualisation, session expirée et prévention du double Shell. Les API métier sont simulées pour éviter toute écriture.
- Digests de publication comparés aux manifestes relus sur GHCR.
- RECETTE et PREPROD utilisent les mêmes nouvelles références ; les 11 autres images sont inchangées.
- Aucun changement des scripts de livraison, secrets, données, volumes ou historiques. Aucun accès VM ni déploiement.

## Installation

Utiliser le parcours existant : `git pull --ff-only`, puis `./wavy install recette`. Après validation fonctionnelle RECETTE, utiliser `./wavy install preprod`.

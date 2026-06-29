# FACTURES

## Objectif

Documenter le module `wavy-factures-api` et son front `wavy-factures-front` pour la gestion des factures et des workflows de facturation.

## Informations trouvées dans le code

- `wavy-factures-api` couvre les factures de vente, les lignes, les calculs HT/TVA/TTC, et des statuts de facturation.
- Le module est conçu pour fonctionner avec des headers métiers obligatoires : `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Le module expose des endpoints de type `GET /api/factures`, `POST /api/factures`, `POST /api/factures/{id}/valider`, `POST /api/factures/{id}/annuler`.
- `wavy-factures-api` a un profil local basé sur H2 et un mode recette basé sur PostgreSQL.
- `wavy-factures-front` appelle la gateway sur `/api/factures` et s’interface avec `wavy-socle-api`, `wavy-tiers-api`, `wavy-contrats-api`.

## Conventions observées

- Le front local écoute sur `4203`.
- Le front utilise `http://localhost:8088/api` comme gateway locale.
- En recette, le front cible `http://localhost:18088/api`.
- Le module `wavy-pwa` upload des fichiers de facture à `wavy-factures-api` via la gateway.

## Points à compléter

- Schéma de la base `wavy_factures_db`.
- Détails des règles de calculs TVA, statuts et validations.
- Architecture du module IA et du scan de facture PWA.
- Détails du modèle de données et des entités.

## Liens utiles

- `../wavy-factures-api/README.md`
- `../wavy-factures-front/README.md`
- `../README_DEV_LOCAL.md`
- `../README_FACTURES_IA.md`

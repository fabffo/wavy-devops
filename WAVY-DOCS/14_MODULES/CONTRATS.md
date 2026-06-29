# CONTRATS

## Objectif

Documenter le module `wavy-contrats-api` et son front `wavy-contrats-front` pour la gestion des contrats Wavy.

## Informations trouvées dans le code

- `wavy-contrats-api` gère les contrats, les pièces jointes et les statuts de contrat.
- `wavy-contrats-api` est versionné par Flyway.
- `wavy-contrats-front` appelle la gateway sur `/api/contrats/**` et `/api/tiers`.
- Les endpoints incluent les actions `activer`, `suspendre`, `terminer`, `annuler`, et la gestion de pièces jointes.
- Les fronts Angular s'appuient sur le contexte fourni par le socle.

## Conventions observées

- La route du front est `http://localhost:4202` en local.
- Le front utilise `http://localhost:8088` comme gateway locale.
- Les headers métiers sont transmis pour tous les appels métier.

## Points à compléter

- Schéma de la base `wavy_contrats_db`.
- Détails des workflows de contrat.
- Décisions métier sur les statuts et transitions.
- Structure interne des services Angular.

## Liens utiles

- `../wavy-contrats-api/README.md`
- `../wavy-contrats-front/README.md`
- `../README_DEV_LOCAL.md`

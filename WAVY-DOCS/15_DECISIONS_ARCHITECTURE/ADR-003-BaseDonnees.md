# ADR-003 BaseDonnees

## Objectif

Documenter la décision d'utiliser PostgreSQL pour les bases de données Wavy, avec un mode H2 local pour le module factures.

## Contexte

Plusieurs modules de Wavy stockent leurs données dans une base relationnelle. Le projet est exécuté en local, en Docker local et en recette.

## Décision observée

- `wavy-socle-api`, `wavy-tiers-api`, `wavy-contrats-api`, `wavy-factures-api` utilisent PostgreSQL en Docker.
- `wavy-factures-api` utilise H2 pour des exécutions locales simples et des tests.
- Les bases PostgreSQL sont exposées sur des ports hôtes dédiés.

## Raisons

- PostgreSQL offre une base relationnelle stable et adaptée aux besoins métier.
- Docker permet d'isoler chaque base dans un conteneur.
- H2 local facilite le test rapide sans configuration PostgreSQL.

## Conséquences

- La configuration Docker doit être synchronisée avec les vars `.env`.
- Les backends doivent gérer des profiles de datasource différents entre local et recette.
- Les données de recette sont chargées manuellement par des scripts.

## Points à compléter

- État exact des migrations Flyway par module.
- Schéma de chaque base.
- Politique de backup/restore.
- Contraintes de performance et indexation.

# 00\_MASTER\_CONTEXT

## Objectif

Fournir une vue d'ensemble stable du projet Wavy, de son organisation, de ses modules et de ses environnements. Ce document sert de point d'entrée permanent pour les développeurs, les assistants Chat/Codex et les audits.

## Informations trouvées dans le code

* Le workspace principal est `wavy-devops`.
* Les modules sont organisés en dépôts voisins : `wavy-socle-api`, `wavy-socle-front`, `wavy-tiers-api`, `wavy-tiers-front`, `wavy-contrats-api`, `wavy-contrats-front`, `wavy-factures-api`, `wavy-factures-front`, `wavy-pwa`, `wavy-gateway`.
* `wavy-devops` contient les orchestrations Docker (`docker-compose.local.yml`, `docker-compose.recette.yml`, scripts de démarrage, fichiers `.env` d'exemple, documentation existante).
* Les environnements ciblés sont : local manuel, Docker local, Docker recette.
* Le point d'entrée applicatif principal est la gateway sur `http://localhost:8088` en local et `http://localhost:18088` en recette.

## Conventions observées

* `808x` pour APIs locales, `1808x` pour APIs Docker/recette exposées sur l'hôte.
* `420x` pour fronts Angular locaux, `1420x` pour fronts Docker/recette exposés.
* Les fronts Angular sont servis dans les conteneurs sur le port `80`.
* Le gateway est configuré pour router les `/api/\\\*\\\*` vers les modules backend.
* Les headers métiers de contexte obligatoires sont : `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.

## Points à compléter

* Architecture détaillée de `wavy-socle-api`, `wavy-tiers-api`, `wavy-contrats-api`, `wavy-factures-api` à partir des sources Java.
* Schémas de base de données exacts des modules.
* API reference complète de chaque projet.
* Décisions métier explicites de chaque domaine.
* Sécurité détaillée de chaque module (authentification, autorisation, CORS, protections CSRF).

## Liens utiles

* `README\\\_DEV\\\_LOCAL.md`
* `README\\\_RECETTE\\\_DOCKER.md`
* `README\\\_WAVY\\\_PWA.md`
* `README\\\_FACTURES\\\_IA.md`
* `docker-compose.local.yml`
* `docker-compose.recette.yml`
* `scripts/start-docker-local.sh`
* `scripts/start-docker-recette.sh`

## Modules concernés

* `wavy-socle-api`
* `wavy-socle-front`
* `wavy-tiers-api`
* `wavy-tiers-front`
* `wavy-contrats-api`
* `wavy-contrats-front`
* `wavy-factures-api`
* `wavy-factures-front`
* `wavy-pwa`
* `wavy-gateway`
* `wavy-devops`


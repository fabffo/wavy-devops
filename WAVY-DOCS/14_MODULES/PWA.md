# PWA

## Objectif

Documenter le module `wavy-pwa` pour le scan mobile des factures et l’envoi de fichiers vers `wavy-factures-api`.

## Informations trouvées dans le code

- `wavy-pwa` est une application Angular séparée, mobile-first et installable en PWA.
- Elle permet de scanner ou importer un PDF/JPG/PNG et d'envoyer le fichier à `wavy-factures-api` via la gateway.
- Le front local tourne sur `http://localhost:4204`.
- La gateway locale attendue est `http://localhost:8088/api`.
- En PWA mobile, le champ fichier utilise `capture="environment"` pour la caméra arrière.
- L'historique des scans est local au navigateur.

## Conventions observées

- Le module fonctionne via la gateway et ne crée pas de login complet.
- Le workflow reste manuel : validation de la facture après correction.
- Les headers de contexte par défaut sont `X-Tenant-Id: 100`, `X-Utilisateur-Id: 100`, `X-Societe-Courante-Id: 100`.

## Points à compléter

- Architecture interne de `wavy-pwa`.
- Détails exacts des endpoints IA et de l’envoi de fichiers.
- Gestion des erreurs et de l’état offline.
- Manifest et configuration de service worker.

## Liens utiles

- `../README_WAVY_PWA.md`
- `../README_FACTURES_IA.md`

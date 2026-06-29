# ADR-004 CORS-Security

## Objectif

Documenter la décision de gérer le CORS et les aspects de sécurité côté gateway dans Wavy.

## Contexte

Les fronts Angular sont servis depuis des ports différents du backend et doivent accéder aux APIs via la gateway.

## Décision observée

- `wavy-gateway` gère les règles CORS pour les origins locales et recette.
- Les headers autorisés incluent `Authorization`, `Content-Type`, `X-Tenant-Id`, `X-Utilisateur-Id`, `X-Societe-Courante-Id`.
- Les méthodes autorisées incluent `GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`.
- Le gateway conserve `Set-Cookie` exposé.

## Raisons

- Prévenir les erreurs CORS lors du développement local et en recette.
- Permettre la transmission de cookies et de headers métiers.
- Maintenir un point central de configuration CORS.

## Conséquences

- Le front doit communiquer avec la gateway pour éviter les blocages CORS.
- La configuration CORS du gateway doit rester synchronisée avec les origins des fronts locaux et recette.
- Les backends peuvent rester plus simples sur le CORS en s'appuyant sur le gateway.

## Points à compléter

- Configuration exacte du CORS dans `wavy-gateway`.
- Sécurisation des origins en production.
- Mise en œuvre de CSRF et de protections additionnelles.

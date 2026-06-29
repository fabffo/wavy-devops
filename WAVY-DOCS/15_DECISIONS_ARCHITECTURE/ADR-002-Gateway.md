# ADR-002 Gateway

## Objectif

Documenter la décision d'utiliser `wavy-gateway` comme point d'entrée unifié pour les APIs Wavy.

## Contexte

Les fronts Angular et la PWA doivent appeler plusieurs modules backend sans connaître les URLs directes de chaque API.

## Décision observée

- `wavy-gateway` est une application Spring Cloud Gateway.
- Elle route les requêtes `/api/**` vers les différents backends.
- Les routes configurées incluent les services socle, tiers, contrats et factures.
- Les fronts Angular utilisent la gateway comme unique point d'entrée.

## Raisons

- Masquer la complexité du routage backend aux fronts.
- Centraliser le CORS et la transmission des headers de contexte.
- Simplifier la configuration des environnements Docker.

## Conséquences

- Toute requête front vers `/api/**` passe par la gateway.
- Les backends ne doivent pas être exposés directement aux clients finaux.
- La gateway doit être disponible avant que les fronts puissent fonctionner.

## Points à compléter

- Détails complémentaires de configuration des routes.
- Stratégie de fallback et de résilience du gateway.
- Authentification éventuelle future du gateway.

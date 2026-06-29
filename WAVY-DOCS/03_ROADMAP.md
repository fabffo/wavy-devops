# 03_ROADMAP

## Objectif

Exprimer l'état actuel du projet et les axes de progression observés dans le code et la documentation existante.

## Informations trouvées dans le code

- `README_DEV_LOCAL.md` indique des écarts entre l'état local et l'état cible sur les ports et les migrations.
- `wavy-socle-api` et `wavy-factures-api` n'ont pas de Flyway dans l'état observé, même si des migrations existent ailleurs.
- `wavy-tiers-api` et `wavy-contrats-api` utilisent Flyway.
- `wavy-pwa` est un projet Angular séparé utilisé pour scanner des factures IA.
- `wavy-gateway` est un élément central pour la stabilization des routes entre les fronts et les APIs.

## Axes prioritaires

1. Stabiliser la plateforme Docker locale et recette.
2. Harmoniser les environnements `local`, `docker` et `recette`.
3. Documenter précisément les ports, les variables d'environnement et les profils Spring utilisés.
4. Compléter les schémas de base de données et les références API.
5. Documenter les décisions d'architecture et métier.

## Priorités de développement

- `wavy-gateway` : centraliser le routage et la configuration CORS.
- `wavy-factures-api` : ajouter ou stabiliser Flyway et la configuration PostgreSQL en local.
- `wavy-socle-api` : harmoniser les noms de base de données et le multi-tenant.
- Fronts Angular : s'assurer qu'ils passent tous correctement par la gateway.
- `wavy-pwa` : clarifier le flux d'upload IA vers `wavy-factures-api`.

## Points à compléter

- Roadmap métier détaillée pour les domaines factures, contrats, tiers.
- Jalons, MVP et versions planifiées.
- Dépendances inter-modules et ordre de livraison.
- Priorités des correctifs de sécurité et des tests.

## Liens utiles

- `README_DEV_LOCAL.md`
- `README_FACTURES_IA.md`
- `README_RECETTE_DOCKER.md`
- `IMPLEMENTATION_RAPPROCHEMENT_FOURNISSEUR_COMPLETE.md`

# 10_TEST_GUIDE

## Objectif

Documenter l'approche de test observée dans le projet Wavy et les commandes utiles pour valider les modules.

## Informations trouvées dans le code

- Les projets backend utilisent Maven et `./mvnw test`.
- Les projets front utilisent `npm test` et `ng test`.
- Les projets Angular contiennent les structures `src/app` et `package.json`.
- La PWA utilise `npm start`, `ng test` et potentiellement `ng e2e`.

## Conventions observées

- Tests backend via `./mvnw test`.
- Tests front via `npm test -- --watch=false` ou `ng test`.
- Les tests e2e ne sont pas explicitement documentés pour tous les fronts.
- Les health checks sont utilisés comme tests de disponibilité.

## Bonnes pratiques observées

- Exécuter `./mvnw test` avant les builds backend.
- Exécuter `npm test` après les modifications front.
- Vérifier les endpoints `/actuator/health` et `/api/*/health`.
- Utiliser les scripts Docker pour démarrer un environnement intégré avant les tests de bout en bout.

## Points à compléter

- Détails sur les suites de tests existantes (unitaires, intégration, e2e).
- Élément de couverture minimale des tests.
- Stratégie de tests automatisés dans CI/CD.
- Frameworks et patterns de tests réellement utilisés dans chaque projet (JUnit, Mockito, Cypress, etc.).

## Liens utiles

- `wavy-socle-api/README.md`
- `wavy-tiers-api/README.md`
- `wavy-contrats-api/README.md`
- `wavy-factures-api/README.md`
- `wavy-socle-front/README.md`
- `wavy-tiers-front/README.md`
- `wavy-contrats-front/README.md`
- `wavy-factures-front/README.md`
- `wavy-pwa/README.md`

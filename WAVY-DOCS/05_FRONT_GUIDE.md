# 05_FRONT_GUIDE

## Objectif

Documenter l'organisation des applications front-end Angular et PWA dans Wavy, les environnements de démarrage, les conventions de build et les bonnes pratiques d'utilisation de la gateway.

## Informations trouvées dans le code

- `wavy-socle-front`, `wavy-tiers-front`, `wavy-contrats-front`, `wavy-factures-front` et `wavy-pwa` sont des applications Angular.
- Les fronts locaux se lancent sur `4200`, `4201`, `4202`, `4203`, `4204`.
- Les fronts Docker/recette exposés sont `14200`, `14201`, `14202`, `14203`.
- Les projets utilisent `npm start`, `npm test`, `npm run build`.
- `wavy-pwa` est mobile-first et upload des fichiers vers l'API factures via la gateway.

## Conventions observées

- Les applications Angular utilisent `API_UPSTREAM`, `API_BASE_URL` ou `API_GATEWAY_BASE_URL` pour le point d'entrée de la gateway.
- Les fronts doivent appeler la gateway plutôt que les API backend directes.
- Les valeurs par défaut du proxy Angular pointent vers `http://localhost:8088`.
- Les builds de recette utilisent `http://localhost:18088` comme point d'entrée gateway.

## Démarrage local

### `wavy-socle-front`

```bash
cd ../wavy-socle-front
npm start
```

Port local : `http://localhost:4200`

### `wavy-tiers-front`

```bash
cd ../wavy-tiers-front
npm start
```

Port local : `http://localhost:4201`

### `wavy-contrats-front`

```bash
cd ../wavy-contrats-front
npm start -- --port 4202
```

Port local : `http://localhost:4202`

### `wavy-factures-front`

```bash
cd ../wavy-factures-front
npm start
```

Port local : `http://localhost:4203`

### `wavy-pwa`

```bash
cd ../wavy-pwa
npm start
```

Port local : `http://localhost:4204`

## En Docker local / recette

- Les fronts sont servis depuis Nginx dans le conteneur sur le port `80`.
- Les ports hôtes locaux sont `14200`, `14201`, `14202`, `14203`, `14204`.
- Les ports hôtes recette sont `24200`, `24201`, `24202`, `24203`.
- Le front doit appeler la gateway sur `8088` en local ou `18088` en recette.

## Points à compléter

- Détails des frameworks front (versions Angular, librairies, architecture des modules).
- Convention de codage front-end et règle de linting.
- Tests unitaires et end-to-end front.
- Module `wavy-pwa` spécifique : installation, service worker, manifest.

## Liens utiles

- `README_WAVY_PWA.md`
- `README.md` des fronts Angular
- `docker-compose.local.yml`
- `docker-compose.recette.yml`

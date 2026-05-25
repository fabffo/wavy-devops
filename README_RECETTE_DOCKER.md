# Docker Recette Wavy

Cette documentation décrit la pile Docker globale de recette pour le dépôt `wavy-devops`.

## Principe

La pile Docker recette est séparée de la pile locale valide existante. Elle utilise :
- `docker-compose.recette.yml`
- `.env.recette` (non versionné)
- les scripts sous `scripts/`
- les données de recette sous `dev/recette/`

Les données de recette sont chargées manuellement via `./scripts/load-recette-data.sh`. Le démarrage Docker ne recharge pas automatiquement les données.

## Installation sur la VM

```bash
git clone <repo> wavy-devops
cd wavy-devops
cp .env.recette.example .env.recette
nano .env.recette
./scripts/start-docker-recette.sh
./scripts/load-recette-data.sh
```

## Démarrage quotidien

```bash
./scripts/start-docker-recette.sh
```

## Arrêt

```bash
./scripts/stop-docker-recette.sh
```

Pour supprimer les conteneurs et les réseaux tout en conservant les volumes :

```bash
./scripts/stop-docker-recette.sh
```

Pour supprimer aussi les volumes :

```bash
./scripts/stop-docker-recette.sh --volumes
```

## Rechargement exceptionnel

Avant un rechargement de données, sauvegardez les bases :

```bash
./scripts/backup-recette-data.sh
```

Puis rechargez les données :

```bash
./scripts/load-recette-data.sh
```

## URLs

- Gateway : http://localhost:28088
- Socle : http://localhost:24200
- Tiers : http://localhost:24201
- Contrats : http://localhost:24202
- Factures : http://localhost:24203

## Comptes de recette

- `adminrecette@wavy.fr` / `motdepasse123` (tenant 1, rôle ADMIN_PLATEFORME)
- `admin.groupe-demo@recette.fr` / `motdepasse123` (tenant 3, rôles ADMIN_TENANT et GESTIONNAIRE)
- `gestionnaire.services@recette.fr` / `motdepasse123` (tenant 3, rôle GESTIONNAIRE, société 4)
- `gestionnaire.immobilier@recette.fr` / `motdepasse123` (tenant 3, rôle GESTIONNAIRE, société 5)

## Tests rapides

```bash
curl -i http://localhost:28088/actuator/health

curl -i -u adminrecette@wavy.fr:motdepasse123 http://localhost:28088/api/profil

curl -i -u admin.groupe-demo@recette.fr:motdepasse123 \
  http://localhost:28088/api/profil

curl -i http://localhost:28088/api/tiers \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4"

curl -i http://localhost:28088/api/tiers \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 5"

curl -i http://localhost:28088/api/contrats \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4"

curl -i http://localhost:28088/api/factures \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4"
```

## Remarques

- `.env.recette` ne doit pas être versionné.
- les backups générés doivent rester en dehors du dépôt.

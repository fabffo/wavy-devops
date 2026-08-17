# Scripts d'administration Wavy

Ces scripts pilotent les environnements Docker Wavy sans avoir à retenir les commandes `docker compose`.

Par défaut, les scripts ciblent l'environnement `recette`.
Pour cibler l'environnement local quand le script le permet :

```bash
WAVY_ENV=local ./scripts/status.sh
WAVY_ENV=local ./scripts/logs.sh factures-api
```

## Pré-requis

- Linux, Ubuntu ou WSL
- Docker démarré
- Docker Compose v2 (`docker compose`)
- Fichiers `.env.local` et `.env.recette` présents à la racine du dépôt

## Scripts

### `status.sh`

Affiche tous les conteneurs Wavy, leur statut, leurs ports et leur état `healthy` si un healthcheck existe.

```bash
./scripts/status.sh
```

### `logs.sh`

Affiche les logs d'un service. Sans argument, un menu interactif est proposé.

```bash
./scripts/logs.sh
./scripts/logs.sh factures-api
./scripts/logs.sh pwa
```

Services disponibles : `socle-api`, `tiers-api`, `contrats-api`, `factures-api`, `tresorerie-api`, `gateway`, les fronts, `pwa` et `erp-shell`.

### `build-all.sh`

Reconstruit toutes les images des environnements `local` et `recette`.

```bash
./scripts/build-all.sh
```

### `build-local.sh`

Reconstruit toutes les images locales.

```bash
./scripts/build-local.sh
```

### `build-recette.sh`

Reconstruit toutes les images recette.

```bash
./scripts/build-recette.sh
```

### `restart-all.sh`

Reconstruit explicitement les images applicatives recette puis recrée les conteneurs applicatifs recette.
Les bases PostgreSQL ne sont pas recréées.

```bash
./scripts/restart-all.sh
```

### Scripts de redémarrage par service

Chaque script reconstruit explicitement l'image du service, recrée uniquement son conteneur avec cette nouvelle image, puis affiche les logs récents sans suivi bloquant.
Pour les fronts, cela recompile donc le bundle Angular/Vite avant de recréer l'image Nginx.

```bash
./scripts/restart-socle-api.sh
./scripts/restart-tiers-api.sh
./scripts/restart-contrats-api.sh
./scripts/restart-factures-api.sh
./scripts/restart-tresorerie-api.sh
./scripts/restart-gateway.sh
./scripts/restart-socle-front.sh
./scripts/restart-tiers-front.sh
./scripts/restart-contrats-front.sh
./scripts/restart-factures-front.sh
./scripts/restart-tresorerie-front.sh
./scripts/restart-pwa.sh
./scripts/restart-erp-shell.sh
```

Par défaut les scripts ciblent `recette`. Exemple local :

```bash
WAVY_ENV=local ./scripts/restart-factures-api.sh
WAVY_ENV=local ./scripts/restart-erp-shell.sh
```

### `stop-all.sh`

Arrête les services applicatifs. Les bases PostgreSQL ne sont arrêtées qu'après confirmation explicite.

```bash
./scripts/stop-all.sh
```

### `clean.sh`

Nettoie Docker sans supprimer les volumes de données Wavy :

- images inutilisées ;
- cache de build Docker ;
- volumes inutilisés non identifiés comme volumes de bases, après confirmation.

```bash
./scripts/clean.sh
```

### `backup-db.sh`

Sauvegarde les bases `socle`, `tiers`, `contrats` et `factures` dans :

```text
backups/AAAA-MM-JJ_HHMM/
```

Chaque dump est au format PostgreSQL custom (`pg_dump -Fc`).

```bash
./scripts/backup-db.sh
```

### `restore-db.sh`

Liste les sauvegardes disponibles, permet de choisir une base, puis demande confirmation avant restauration.

```bash
./scripts/restore-db.sh
```

La restauration utilise `pg_restore --clean --if-exists`.

## Sécurité

- Les scripts vérifient Docker et Docker Compose avant exécution.
- Les bases PostgreSQL ne sont jamais arrêtées sans confirmation.
- Les volumes contenant les données Wavy ne sont pas supprimés par `clean.sh`.
- Les commandes destructrices de restauration demandent une confirmation explicite.

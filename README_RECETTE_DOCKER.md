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

Avant de lancer sur une VM accessible depuis une autre machine, adaptez dans `.env.recette` :

```env
WAVY_PUBLIC_GATEWAY_URL=http://<ip-ou-domaine-vm>:28088
WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=https://recette.wavyservices.fr
```

En local sur la VM elle-même, les valeurs `localhost` de l'exemple restent suffisantes. Depuis un navigateur distant, ne laissez pas `WAVY_PUBLIC_GATEWAY_URL` sur `localhost`, sinon le front appellera le poste client au lieu de la VM.

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
- PWA notes de frais : http://localhost:24204

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

curl -i http://localhost:28088/api/factures/ventes \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4"

curl -i http://localhost:28088/api/factures \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4"

curl -i http://localhost:28088/api/notes-frais \
  -H "Origin: http://localhost:24204" \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4" \
  -H "X-Wavy-Roles: NOTE_DE_FRAIS"

curl -i http://localhost:28088/api/notes-frais/synthese-mensuelle?annee=2026 \
  -H "Origin: http://localhost:24204" \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4" \
  -H "X-Wavy-Roles: SUPER_NOTE_DE_FRAIS"
```

Extraction IA des factures de vente : voir `README_FACTURES_IA.md` pour la configuration `WAVY_AI_*`, les limites et les commandes curl.

Factures d'achat :

```bash
curl -i http://localhost:28088/api/factures/achats \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4"

curl -i -X POST http://localhost:28088/api/factures/achats \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 6" \
  -H "X-Societe-Courante-Id: 4" \
  -d '{
    "categorieAchat": "FRAIS_GENERAUX",
    "numeroFactureFournisseur": "OVH-2026-001",
    "dateFacture": "2026-01-15",
    "dateReception": "2026-01-16",
    "dateEcheance": "2026-02-15",
    "fournisseurNom": "OVH",
    "libelle": "Hébergement cloud",
    "devise": "EUR",
    "regimeTva": "TVA_STANDARD",
    "modePaiement": "VIREMENT",
    "lignes": [
      {
        "libelle": "Hébergement cloud",
        "quantite": 1,
        "unite": "MOIS",
        "prixUnitaireHt": 100,
        "tauxTva": 20
      }
    ]
  }'
```

## Remarques

- `.env.recette` ne doit pas être versionné.
- les backups générés doivent rester en dehors du dépôt.

### Images de release reproductibles

`./wavy start recette` charge automatiquement `versions/recette.env` et
`versions/recette.digests`. Les 13 services applicatifs utilisent la référence
`ghcr.io/fabffo/wavy-<composant>:<version>@sha256:<digest>` : le tag conserve la
traçabilité, le digest détermine exactement le contenu exécuté.

Avant toute recréation, les 13 tags sont téléchargés et leurs RepoDigests sont
comparés au manifeste ; les références épinglées sont ensuite téléchargées.
Un digest absent, invalide ou incompatible avec la version bloque l'opération
avant le remplacement des conteneurs. Le shell ne peut pas remplacer les
versions ou digests déclarés. Aucun build n'est exécuté en RECETTE.

Les commandes historiques `./wavy build recette [all|service]`,
`./scripts/build-recette.sh` et les redémarrages restent disponibles : leur étape
build télécharge et vérifie désormais les images de release. Le redémarrage
complet des applications conserve les dépendances PostgreSQL ; aucune commande
n'efface les volumes, bases ou documents.

PREPROD charge également les 13 digests dans son Compose de base. Les mises à
jour et rollbacks restent exclusivement dans l'orchestrateur sécurisé existant
(verrou, contrôles hôte, configuration, sauvegarde et vérifications après
remplacement). Il vérifie les 13 références de release avant le remplacement
ciblé ; un rollback garde son digest historique autorisé.

Validation locale sans daemon ni déploiement :
`python3 scripts/test-release-images.py` (rendu Compose réel et Docker simulé
pour les contrôles de téléchargement et de refus).

### CORS HTTPS commun

Gateway et les cinq APIs lisent `WAVY_CORS_ALLOWED_ORIGIN_PATTERNS` depuis la
configuration machine, avec les origines exactes de référence du Compose si la
variable est absente. La référence RECETTE inclut
`https://recette.wavyservices.fr` et les ports historiques des fronts localhost.
Le manifeste `versions/recette.env` ne définit plus de paramètre CORS distinct
pour Gateway. Le profil Gateway `recette` doit provenir de l'image corrigée :
il lit cette variable au lieu d'imposer uniquement localhost.

PREPROD conserve son origine unique validée contre `WAVY_PUBLIC_URL` :
`https://preprod.wavyservices.fr` en mode HTTPS, ou l'origine locale du tunnel.
Le parcours HTTPS local conserve son origine exacte
`https://recettelocal.wavyservices.fr` et ses paramètres de proxy.

Une surcharge explicite `SPRING_APPLICATION_JSON` ou une propriété Spring
passée en ligne de commande reste prioritaire sur les propriétés du profil ;
elle doit désigner la même origine. Aucun ajustement direct de la map CORS
Spring sur les VMs n'est nécessaire avec l'image Gateway corrigée.

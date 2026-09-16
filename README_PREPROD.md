# Préproduction Wavy

Préparation DevOps réalisée sur **ffo@MSI**, sans déploiement. La cible future est
la VM dédiée **wavyadmin@wavy-preprod**, projet Docker **wavy-preprod**.
Aucun vrai `.env.preprod` n’est créé dans cette revue.

| Environnement | Déploiement | Isolation |
|---|---|---|
| LOCAL | Sources et builds existants | Configuration de développement inchangée |
| RECETTE | 13 images GHCR déjà versionnées | Manifestes, données et fonctionnement inchangés |
| PREPROD | Images GHCR, version et digest individuels, contrôle OCI | VM, réseau, volumes et secrets dédiés ; aucun port DB/API/Gateway publié |

## Images autorisées et preuves

`versions/preprod.env` contient uniquement le registre et les 13 versions.
`versions/preprod.digests` contient les 13 digests correspondants. Aucun tag global.
Le Socle est **0.1.0-6570deb**, digest
`sha256:77c66ff49cbc14e6b4b1e91d0ce687b6e9dc0063b1f8c3055f9bc37c208c9662`.
Les 12 autres couples viennent des manifestes et historiques RECETTE, recoupés
avec les RepoDigests et les trois labels OCI du cache MSI. Voir
[la revue détaillée](docs/preprod-review.md), avec provenance et limites.
PostgreSQL 16 Alpine est également épinglé au digest observé dans le cache MSI,
directement dans Compose ; aucune mise à jour automatique de cette image socle.

L’historique `versions/history/preprod/<composant>.tsv` suit exactement le schéma
RECETTE : `version`, `digest`, `commit`, `date_validation`. Il ne contient
initialement que les en-têtes. Les manifestes autorisent une livraison ; leur
présence **ne signifie pas un déploiement**. Une ligne historique n’est ajoutée
qu’après les contrôles runtime réussis. Le rollback exige cette ligne : aucune
ancienne version RECETTE n’est implicitement autorisée comme rollback PREPROD.

## Configuration machine future

Sur la VM seulement, après synchronisation du dépôt Git revu : copier le
modèle `.env.preprod.example` vers `.env.preprod`, remplacer les placeholders,
appliquer `chmod 600`. Ce fichier est ignoré par Git. Ne pas y dupliquer les
versions, digests ou le registre. Les scripts refusent les substitutions shell
et les valeurs interpolées ; pour un secret contenant `$`, `#`, espaces ou
backslash, utiliser `CLE='valeur littérale'` sur une seule ligne, sans quote
simple interne. Le dotenv n’est jamais exécuté par `source`.

Préparer des secrets **propres à PREPROD**, différents de RECETTE : cinq mots
de passe DB distincts (12 caractères minimum), administrateur bootstrap (12),
secret session (32), passphrase backup (32), credentials Socle/Tiers si utilisés,
clé AI et SMTP si ces fonctions sont activées. L’indépendance vis-à-vis de
RECETTE relève de la génération dans le gestionnaire de secrets : le validateur
ne lit pas les secrets RECETTE. AI est désactivée par défaut (provider vide).
Les variables SMTP du modèle ne sont pas câblées aux images dans cette étape.

`WAVY_BOOTSTRAP_ENABLED=false` par défaut ; configurable uniquement dans le
dotenv machine. Le premier démarrage peut utiliser `true` pour initialiser
le tenant, la société et l’administrateur. Le passage ultérieur à `false`
reste une décision opérateur, appliquée au prochain déploiement Socle.

## Accès A : bootstrap et tests par tunnel SSH

Le port `127.0.0.1:24443` du serveur aboutit au port **80 HTTP** du Nginx ERP
Shell. Le nouveau nom est `WAVY_PUBLIC_HTTP_PORT` ; aucun certificat ni TLS
n’est fourni par ce Compose. Exemple de paramètres pour le tunnel initial :

```dotenv
WAVY_ACCESS_MODE=tunnel
WAVY_COOKIE_SECURE=false
WAVY_PUBLIC_HTTP_PORT=24443
WAVY_PUBLIC_URL=http://localhost:24443
WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=http://localhost:24443
```

Commande future depuis le MSI (non exécutée pendant la préparation) :

```bash
ssh -N -L 24443:127.0.0.1:24443 wavyadmin@wavy-preprod
```

Le navigateur utilise `http://localhost:24443`. SSH chiffre le transport entre
les deux machines, mais ne transforme pas HTTP en HTTPS. **Décision de revue :
scénario B, HTTP temporaire**, car aucun domaine, certificat ni reverse proxy
TLS n’est disponible dans le lot. `WAVY_COOKIE_SECURE=false` est explicitement
limité à `WAVY_ACCESS_MODE=tunnel` avec cette seule origine localhost. HttpOnly
et SameSite=Strict restent actifs. Le validateur refuse un cookie non-Secure en
mode HTTPS, tout autre hôte en tunnel et toute publication hors loopback.

Le cookie est émis par Socle, pas par le Gateway WebFlux. Le comportement
Secure sur HTTP localhost bénéficie d’exceptions dans certains navigateurs,
mais n’est pas portable (notamment Safari) : cette étape ne repose pas dessus.
Aucun test navigateur réel Windows n’a été exécuté. Voir la
[revue finale](docs/preprod-final-review.md) et ses sources navigateur.

Pour sortir du mode temporaire : installer la terminaison TLS et son certificat,
choisir le domaine, configurer `WAVY_ACCESS_MODE=https`, `WAVY_COOKIE_SECURE=true`,
`WAVY_PUBLIC_URL=https://<domaine-retenu>` et le même CORS, valider la configuration
puis appliquer les changements par les déploiements contrôlés. Supprimer les
anciennes sessions navigateur et vérifier login/logout via HTTPS. Le port
interne reste HTTP ; aucun nouveau renommage n’est nécessaire.

## Accès B : domaine et reverse proxy HTTPS

Le domaine définitif reste **à décider**, aucun domaine fictif n’est déclaré
comme cible. Configurer le reverse proxy TLS vers `127.0.0.1:24443`, puis
`WAVY_ACCESS_MODE=https`, une origine publique HTTPS exacte et le même CORS.
Configurer les en-têtes de proxy de confiance ; le Nginx embarqué ERP Shell
réécrit actuellement `X-Forwarded-Proto` avec son `$scheme` HTTP : une adaptation
revue du proxy/Nginx sera nécessaire pour préserver correctement le schéma
externe. Ne pas ouvrir directement les DB, APIs ou Gateway.

## Commandes futures sur wavy-preprod

Prérequis : dépôt Git synchronisé, Docker/Compose v2 avec rendu JSON, Bash,
Python **3.11+**, OpenSSL, curl, git, flock et outils GNU usuels ; accès GHCR
(éventuellement token `read:packages` via `docker login --password-stdin`).
Les opérations mutantes PREPROD refusent le MSI et tout contexte Docker distant.

Validation sans démarrage :

```bash
./scripts/validate-preprod-config.sh
```

Première installation **uniquement sur VM sans état PREPROD** :

```bash
./scripts/initialize-preprod.sh --empty-installation
```

Ce chemin vérifie configuration, espace disque, absence de conteneurs/volumes,
13 tags distants, RepoDigests et labels OCI. Il tire PostgreSQL par digest puis
utilise un override temporaire épinglant toutes les images applicatives. Après
confirmation, il crée la stack et attend les healthchecks. Les migrations et le
bootstrap sont ceux des images ; aucun client Flyway externe n’est lancé. Pas
de backup préalable pour des bases inexistantes. L’état est `PENDING_SMOKE`.
En cas d’échec partiel, conserver les volumes et diagnostiquer ; ne pas relancer
l’initialisation ni supprimer les données automatiquement.

Relever les IDs réels après bootstrap et fournir au processus les cinq variables
`WAVY_SMOKE_TENANT_ID`, `WAVY_SMOKE_USER_ID`, `WAVY_SMOKE_COMPANY_ID`,
`WAVY_SMOKE_USER`, `WAVY_SMOKE_PASSWORD` depuis le gestionnaire de secrets.
Aucun ID arbitraire ni compte fictif n’est accepté comme preuve. Puis :

```bash
./scripts/validate-preprod-runtime.sh
```

Cette validation vérifie les images actives, Flyway, healthchecks, smoke tests
et une première sauvegarde ; elle remplit alors les historiques techniques,
avec journal `VALIDATE_INITIAL`, sans fausse entrée `DEPLOY`.

Mises à jour et rollback :

```bash
./scripts/deploy.sh preprod socle-api
./scripts/rollback.sh preprod socle-api <version-deja-validee>
./wavy restart preprod socle-api
./wavy status preprod
./wavy health preprod
./scripts/smoke-test.sh preprod
./wavy logs preprod socle-api
./wavy backup preprod
./wavy restore preprod backups/preprod/<lot> --with-documents
```

Chaque remplacement est ciblé (`--no-deps --no-build --pull never`), avec
verrou exclusif, Git propre, précontrôle des secrets/contexte smoke et du disque,
vérification distante/version/digest/OCI, sauvegarde des **cinq** bases même pour
un front, cache de l’image active, rendu Compose final puis attente `healthy`,
contrôle des logs Flyway, healthchecks et smoke tests. L’ID actif et la référence
par digest doivent correspondre. Aucun rollback automatique ; une migration
peut rendre une ancienne image incompatible. Le rollback ne restaure jamais
une base et n’édite pas les manifestes : les réaligner ensuite par une modification
Git revue pour ne pas redéployer accidentellement la version abandonnée.

`wavy build preprod`, `wavy restart preprod all` et `wavy start preprod` refusent
les raccourcis non vérifiés ; utiliser les commandes explicites ci-dessus.
L’ancien override `.preprod.build.yml` est neutralisé et ne sert plus à construire.
`test-database-from-zero.sh` est désactivé : ses noms fixes de conteneurs et le
projet PREPROD ne permettent pas un test destructif éphémère sûr.
Les journaux runtime PREPROD sont séparés sous `deployments/preprod*.tsv`, ignorés
par Git ; les historiques techniques TSV restent destinés au versionnement et
à la collecte dans une modification Git revue, jamais à un commit automatique.

## Sauvegarde et restauration

La sauvegarde prend le verrou global PREPROD puis le verrou backup pour empêcher
un arrêt des APIs concurrent à un déploiement ou une restauration. Un appel depuis
release/validate-runtime réutilise le verrou hérité jusqu’au retour au parent.

Le volume `documents-preprod` est réservé à Contrats, seul auteur de fichiers
persistants dans les images publiées auditées. Chemin :
`/app/data/contrats/<tenant>/<societe>/<contrat>/<UUID>.<extension>`. Les chemins
et métadonnées sont stockés en base ; restaurer seulement PostgreSQL ferait
perdre la cohérence des pièces jointes. Factures prépare des métadonnées et
génère les PDF en mémoire ; Trésorerie importe les flux en base. Leurs montages
inutilisés ont été retirés. Cela ne prétend pas que Factures archive les PDF
originaux : cette fonctionnalité n’est pas démontrée par l’image actuelle.

L’initialisation vide prépare `contrats` avec UID/GID **100:101** et mode 0700,
relevés dans `/etc/passwd` de l’image Contrats, sans démarrage sur MSI. Le
conteneur reste read_only et son seul volume de données est writable. Une
nouvelle image changeant d’UID/GID nécessite une migration des permissions revue.
`down --volumes` détruirait les fichiers ; aucun script de cette procédure ne
l’exécute. Les suppressions métier Contrats sont logiques, pas des effacements
physiques : prévoir une politique documentaire distincte de la rétention backup.

Chaque lot contient cinq `pg_dump -Fc` et **documents.tar.enc**, chiffrés par
AES-256-CBC avec sel/PBKDF2. Un manifest **format 2** authentifie les six fichiers
par HMAC-SHA256, clé dérivée séparément avec sel aléatoire et PBKDF2 200000.
Les vérifications restent actives même avec `PYTHONOPTIMIZE` ; aucun `assert`
n’est utilisé pour décider de l’intégrité du lot. Passphrase via environnement,
jamais affichée. Répertoires 700, fichiers 600 ; publication atomique uniquement
après succès complet et reprise des services. Archive relue avant publication.

**Fenêtre de maintenance obligatoire à chaque backup**, donc également avant
un deploy/rollback : arrêter proprement Gateway puis les cinq APIs pendant la
capture DB + documents ; reprendre uniquement ces conteneurs à la fin, y compris
sur échec du backup. `SERVER_SHUTDOWN=graceful`, délai Spring 45 s, stop Docker
60 s ; un arrêt forcé est refusé. Aucun autre acteur ne doit écrire directement
en base pendant cette fenêtre. Le remplacement de l’image reste ciblé, mais
la sauvegarde implique bien une interruption temporaire des six backends.

Un conteneur utilitaire éphémère, **image PostgreSQL déjà épinglée**, est prévu
pour tar : sans réseau, rootfs read_only, pas de pull, volume documentaire seul
monté en lecture pour le backup. Rien de tout cela n’est exécuté sur MSI. Tar
conserve les modes et identifiants numériques. Tout échec d’archive interrompt
le lot. La rétention ne s’applique qu’aux lots complets reconnus.

La restauration exige **`--with-documents`**, un lot format 2 authentifié et une
confirmation mentionnant les **cinq bases ET les documents**. Aucun mode DB seul
implicite. Les cinq dumps et l’archive sont déchiffrés et contrôlés avant toute
écriture. Le contrôle tar refuse chemins absolus, `..`, liens, périphériques,
setuid/setgid, doublons et propriétaires autres que 100:101. Prévoir sur le
filesystem temporaire l’espace pour les dumps et documents déchiffrés.

Arrêter préalablement les six backends et conserver un lot récent. Après
confirmation, les bases sont restaurées avec `--clean --if-exists --no-owner
--exit-on-error --single-transaction`, puis le seul répertoire `contrats` est
remplacé depuis l’archive. Les APIs redémarrent ensuite, healthchecks et smoke
tests sont obligatoires. Une erreur de restauration laisse les backends arrêtés
avant la phase de reprise ; il n’existe pas de transaction globale DB+fichiers.
Les anciens lots format 1 sans documents sont refusés, jamais acceptés comme
restauration complète. Aucun backup/restore réel exécuté dans cette revue.

## Validation statique exécutée sur MSI

```bash
python3 scripts/test-preprod-config.py
python3 scripts/test-preprod-guards.py
bash scripts/test-version-history.sh
bash -n wavy
for script in scripts/*.sh; do bash -n "$script"; done
git check-ignore -v .env.preprod
git diff --check
```

Le test PREPROD génère uniquement un dotenv factice dans `/tmp`, utilise
`docker compose --env-file <temp> --env-file versions/preprod.env -p wavy-preprod
-f docker-compose.preprod.yml config --quiet`, puis vérifie le JSON rendu et
les cas de refus. Il ne démarre rien et ne nécessite pas de daemon Docker.
La CI exécute uniquement ces validations ; elle ne déploie jamais.

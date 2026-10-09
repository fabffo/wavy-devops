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
Le Socle autorisé est **0.1.0-a9352ec**, digest
`sha256:cc3af16eef10dbe0946e3dfafd80c1b30967396c81deaac54a8e64826e29b388`.
Image validée et publiée selon les preuves fournies : labels OCI
`revision=a9352ec`, `version=0.1.0`,
`source=https://github.com/fabffo/wavy-socle-api`.
Cette nouvelle image reste à déployer et à valider sur la VM PREPROD ; aucune
entrée historique ne doit être ajoutée avant la réussite des contrôles runtime.
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

`WAVY_BOOTSTRAP_PLATFORM_ADMIN_ENABLED=false` par défaut dans le modèle et
Compose. Cette option peut être absente du dotenv existant : elle vaut alors
`false`. Si elle est présente, seules les valeurs littérales `true` et `false`
sont acceptées (une valeur vide, `TRUE` ou `1` est refusée). Elle est transmise
uniquement au Socle ; une variable héritée du shell ne peut pas l'activer.

Lorsque `WAVY_BOOTSTRAP_ENABLED=true` :

- Option plateforme `false` : le bootstrap attribue `ADMIN_TENANT` uniquement.
- Option plateforme `true` : l'administrateur bootstrap configuré conserve
  `ADMIN_TENANT` et reçoit aussi `ADMIN_PLATEFORME`. Ce rôle permet notamment
  la création de tenants et leur administration à l'échelle de la plateforme.

Les deux options doivent être `true` pour amorcer ce privilège. Si le bootstrap
est désactivé, l'option plateforme n'attribue aucun rôle. Le bootstrap reste
idempotent : il crée le rôle ou l'association seulement si nécessaire, répare
l'administrateur existant et conserve son ID, son hash et ses associations
tiers/société. Il ne promeut pas les autres `ADMIN_TENANT` et ne leur permet
toujours pas de s'élever via l'API normale. Remettre l'option à `false` ne
révoque pas un rôle plateforme déjà attribué.

L'activation est une décision explicite de l'opérateur dans le dotenv privé,
à préparer lors d'une opération ultérieure. Aucune identité réelle ni secret
ne doit être ajouté à Git. L'historique `versions/history/preprod/socle-api.tsv`
reste inchangé jusqu'à une validation runtime réussie de cette nouvelle image.
La prochaine release sera également la première validation runtime réelle
du reload Nginx PREPROD introduit par `94fed00` ; ce correctif reste inchangé.

`WAVY_BOOTSTRAP_ADMIN_FIRST_NAME` et `WAVY_BOOTSTRAP_ADMIN_LAST_NAME`
représentent le prénom et le nom de l'administrateur bootstrap. Les renseigner
uniquement dans le vrai `.env.preprod` sur la VM ; aucune identité réelle dans
Git. Compose transmet ces valeurs au Socle. Avec `WAVY_BOOTSTRAP_ENABLED=true`,
elles sont obligatoires, non vides et ne peuvent pas contenir `CHANGE_ME`.
Avec `false`, elles peuvent être absentes ou vides ; le refus global des
placeholders reste actif, comme pour les autres variables.
Le nouveau bootstrap retrouve l'administrateur existant, conserve son hash de
mot de passe, applique cette identité, recherche ou crée son tiers et répare
`utilisateur_tiers` de manière idempotente. Ces comportements applicatifs
devront être confirmés lors de la validation runtime sur la VM.

## IA Factures PREPROD

L'IA est facultative et les sept variables sont transmises uniquement à
`wavy-factures-api-preprod`. Dans le dotenv privé, l'opérateur peut aligner
provider et modèle sur RECETTE avec ces valeurs :

```dotenv
WAVY_AI_PROVIDER=anthropic
WAVY_AI_MODEL=claude-sonnet-4-5-20250929
WAVY_AI_API_KEY=
WAVY_AI_TIMEOUT_SECONDS=60
WAVY_AI_MAX_FILE_SIZE_MB=10
WAVY_AI_ACHAT_AUTO_CREATION_ENABLED=false
WAVY_AI_ACHAT_MINIMUM_CONFIDENCE=0.90
```

Renseigner la clé depuis le gestionnaire de secrets, avec une clé dédiée à
PREPROD : la ligne vide ci-dessus n'est pas une configuration IA complète.
Provider, modèle et clé doivent être renseignés ensemble ; pour conserver
l'IA désactivée, laisser les trois vides ou absents. Les quatre autres défauts
Compose sont respectivement `60`, `10`, `false`, `0.90`. Si ces paramètres sont
présents dans le dotenv, ils doivent être valides et non vides : timeout et
limite en Mo sont des entiers strictement positifs, création automatique vaut
exactement `true` ou `false`, confiance est un nombre fini entre 0 et 1 inclus.
La création automatique exige une configuration IA complète et reste à `false`
jusqu'à une activation explicite après validation métier PREPROD.

Conserver `.env.preprod` ignoré par Git, avec permissions `600`. Ne jamais
copier la clé RECETTE, ajouter un secret au dépôt, afficher le dotenv ou le
rendu `docker compose config` contenant la clé, ni activer une trace shell.
Le validateur masque les sorties Compose et ne restitue aucune valeur IA.
L'envoi de documents au fournisseur doit être autorisé pour les données de
PREPROD ; utiliser des documents de test sans données sensibles pour valider
l'extraction et le seuil avant d'activer la création automatique.

Après synchronisation du changement DevOps revu et configuration du dotenv,
l'opérateur exécutera uniquement sur la VM les commandes suivantes :

```bash
./scripts/validate-preprod-config.sh
./wavy restart preprod factures-api
```

Le restart ciblé recrée Factures avec les nouvelles variables, à version et
digest autorisés inchangés, via le flux de release protégé existant. Ce flux
comprend la sauvegarde des cinq bases et des documents, une interruption des
backends, les healthchecks, le contrôle Nginx et les smoke tests ; prévoir la
fenêtre de maintenance décrite plus bas. Un simple `docker restart` ne recharge
pas les variables. Vérifier ensuite sur des documents factices le provider,
le modèle et le comportement métier sans exposer la clé dans les logs.
Ces commandes ne sont pas exécutées pendant la préparation locale.

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

## 502 Nginx malgré un Gateway healthy

Symptôme rencontré : `POST /api/auth/session` via ERP Shell retourne
`502 Bad Gateway nginx/1.27.5`, alors que les conteneurs sont healthy et les
six smoke tests backend passent. Les workers Nginx peuvent conserver l'ancienne
IP du Gateway après sa recréation. La résolution Docker courante et un appel
direct réussi depuis ERP Shell ne prouvent pas que les workers utilisent cette IP.
Le healthcheck ERP Shell ne teste que `/`, et les smoke tests historiques
interrogent Gateway depuis Socle, sans passer par Nginx ERP Shell.

Diagnostic sur la VM, à effectuer par l'opérateur :

```bash
docker inspect -f '{{.State.Health.Status}}' wavy-gateway-preprod
docker exec wavy-erp-shell-preprod getent hosts wavy-gateway-preprod
docker exec wavy-erp-shell-preprod \
  wget -S -O /dev/null \
  http://wavy-gateway-preprod:8088/actuator/health
```

Si Gateway est réellement indisponible, corriger cette panne avant tout reload.
Correction d'urgence, seulement après un `nginx -t` réussi :

```bash
docker exec wavy-erp-shell-preprod nginx -t && \
  docker exec wavy-erp-shell-preprod nginx -s reload
docker exec wavy-erp-shell-preprod \
  wget -S -O - http://127.0.0.1/api/tiers/health
```

Le processus DevOps effectue désormais cette protection automatiquement avec
`preprod_reload_erp_shell_nginx` dans `scripts/_preprod.sh`. Il vérifie que
ERP Shell et Gateway existent et tournent, attend Gateway healthy, contrôle
sa résolution depuis ERP Shell et une réponse Actuator `UP`, puis exécute
`nginx -t` avant `nginx -s reload`. Ensuite il contrôle ERP Shell healthy,
revérifie Gateway et teste le proxy local `/api/tiers/health`, avec validation
du module `wavy-tiers-api` et du statut `OK` (une page HTML SPA ne suffit pas).
Cette route de santé est publique ; aucun secret supplémentaire n'est nécessaire.
Le reload est asynchrone : le test du proxy effectue au plus 30 tentatives HTTP
(timeout 5 s chacune), espacées de 2 s uniquement en cas d'échec. Les attentes
Docker healthy ont au plus 30 tentatives espacées de 2 s pour l'état `starting` ;
`unhealthy`, conteneur arrêté ou healthcheck absent provoquent une erreur explicite.
Tout échec bloque la validation, les smoke tests finaux et l'enregistrement de
l'image dans l'historique validé ; la release reste journalisée `KO`.

### Flux audités et emplacement de la protection

- `deploy.sh preprod` et `rollback.sh preprod` délèguent à
  `release-preprod.sh`. Celui-ci utilise `up --no-deps --force-recreate`
  pour le seul composant ciblé : Gateway est recréé si c'est la cible,
  et les fronts des modules sont d'autres upstreams Nginx recréables.
- Chaque release sauvegarde auparavant les bases et documents. Cette sauvegarde
  arrête Gateway puis les cinq APIs et les redémarre en ordre inverse, avec
  Gateway en dernier. Même `deploy.sh preprod socle-api` fait donc repartir
  Gateway alors qu'ERP Shell reste actif. Un stop/start ne recrée pas le
  conteneur ; la protection ne suppose cependant pas une IP inchangée.
- `./wavy restart preprod <composant>` délègue à ce même déploiement ciblé,
  donc bénéficie du même contrôle. `restart preprod all` reste interdit.
- Un seul reload contrôlé est exécuté par release PREPROD, après le remplacement
  et les contrôles du composant, avant `healthcheck.sh` et `smoke-test.sh`.
  Le choix couvre tous les composants plutôt que seulement Gateway, puisque
  toutes ces releases font repartir Gateway. Aucun reload périodique ni reload
  ajouté aux simples commandes status/health/smoke, LOCAL ou RECETTE.
- La première installation (`initialize-preprod.sh`) crée aussi réseau et
  conteneurs, mais lance un ERP Shell neuf après ses dépendances healthy :
  il n'y a pas de workers préexistants à rafraîchir. Le restore redémarre les
  conteneurs existants sans recréer réseau ou images. Les commandes Docker
  manuelles de recréation/reconnexion réseau contournent la protection des
  releases : appliquer alors les contrôles et la correction d'urgence ci-dessus.

### Alternative : DNS dynamique Docker

Le template applicatif lu pour l'audit utilise `proxy_pass ${API_UPSTREAM}`
sans URI pour `/api/` et des upstreams terminés par `/` pour les modules.
`NGINX_ENVSUBST_FILTER=_UPSTREAM$` remplace ces variables d'environnement au
démarrage : elles ne sont pas des variables Nginx évaluées à chaque requête.
Ajouter seulement `resolver 127.0.0.11` ne rendrait pas ces destinations
statiques dynamiques.

Nginx OSS 1.27.5 supporte `server <hôte>:<port> resolve` dans un bloc `upstream`
avec une `zone` partagée et un `resolver 127.0.0.11` : cette fonctionnalité est
disponible depuis 1.27.3 ([documentation officielle upstream](https://nginx.org/en/docs/http/ngx_http_upstream_module.html#resolve)).
Cette approche permettrait de suivre les changements d'IP hors des releases,
mais demande une modification du template applicatif et une validation de
l'image réellement exécutée, du DNS Docker et des routes des modules.
Une autre approche utilise une variable Nginx dans `proxy_pass` avec le resolver,
mais la gestion des URI change lorsqu'une URI est incluse dans la destination :
il faut préserver explicitement les réécritures des préfixes `/modules/.../`
([documentation officielle proxy_pass](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)).

Le reload contrôlé est retenu pour ce correctif : il conserve les règles de
routage et les images actuelles et reproduit la correction runtime confirmée.
Sa limite est qu'il dépend du passage par les commandes DevOps protégées ;
une résolution dynamique traiterait aussi les changements d'IP extérieurs à ces
commandes, au prix d'une évolution applicative à tester séparément. Aucun
template Nginx applicatif ni fichier Compose n'est modifié ici.

## Validation statique exécutée sur MSI

```bash
python3 scripts/test-preprod-config.py
python3 scripts/test-preprod-guards.py
python3 scripts/test-preprod-nginx.py
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

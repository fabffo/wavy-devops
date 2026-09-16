# Revue finale bloquante PREPROD — revalidée le 16 septembre 2026

**GO POUR COMMIT DEVOPS PREPROD**, pour le premier jalon technique en tunnel
HTTP temporaire explicitement configuré. Ce GO autorise la préparation du
commit ; il ne vaut ni validation métier, ni autorisation de déploiement, ni
certification de la terminaison HTTPS finale. Aucun commit, staging ou push effectué.

## Revalidation locale du 16 septembre 2026

Le rapport et toutes les corrections décrites ci-dessous étaient déjà présents
à l’ouverture de cette nouvelle revue. L’état initial de cette passe correspond
à l’**inventaire final précis** ci-dessous : 16 fichiers suivis modifiés et
30 fichiers non suivis, tous rattachés au lot PREPROD. Aucun fichier hors lot
modifié n’a été identifié. L’inventaire initial plus bas est celui de la passe
précédente, conservé pour traçabilité.

Les sources des huit révisions citées ont été relues localement, ainsi que les
configurations génériques, secure, recette et preprod et les conditions Java.
Les contrôles exécutés cette fois restent statiques : aucun contexte Spring,
navigateur Windows ou service applicatif démarré. La qualification navigateur
est une analyse du flux ; les références documentaires antérieures sont
conservées, sans consultation réseau pendant cette passe MSI.

Une correction nécessaire supplémentaire concerne la **concurrence backup /
déploiement** : auparavant, le backup autonome ne prenait que le verrou backup,
et pouvait arrêter les APIs pendant le remplacement d’un composant. Il prend
maintenant aussi le verrou global `deployments/preprod.lock`, avant le verrou
backup. Lorsqu’il est appelé par release ou validate-runtime, le descripteur 9
hérité est réutilisé sans rouvrir le fichier et sans libérer le verrou du parent.
Le verrou global reste détenu jusqu’à la fin du backup autonome.

Un test local sans Docker vérifie l’acquisition autonome, le refus face à un
verrou concurrent, l’appel enfant avec descripteur hérité et le maintien du
verrou parent après retour. **25/25 tests passent : 15 configuration + 10
garde-fous**. Les 24 tests présents au début de cette passe restent verts ;
les 20 de la demande sont conservés avec les quatre ajouts de la passe
précédente et ce cinquième test. Syntaxe Bash/Python, historique, Compose avec
secrets factices hors dépôt et `git diff --check` : OK.

Fichiers retouchés pendant cette passe uniquement : `scripts/_preprod.sh`,
`scripts/backup-preprod.sh`, `scripts/test-preprod-guards.py`, `README_PREPROD.md`
et ce rapport. Aucun fichier supplémentaire créé ; les fichiers déjà non suivis
restent non suivis. Aucun staging, commit, push, build, conteneur, volume,
backup/restore réel, PostgreSQL, Flyway ou accès VM.

## Périmètre et preuves

Travail uniquement sur MSI dans `~/projets/wavy-devops`. Le lot préparé est
préservé. Aucune modification hors lot détectée dans l’état initial. Les docs
images/versioning/smoke et le manifeste PREPROD étaient déjà non suivis dans la
préparation précédente : conservés et complétés, pas supprimés. Les adaptations
aux scripts communs sont conditionnées à PREPROD ; les fichiers spécifiques
RECETTE/LOCAL ne sont pas modifiés.

Lecture des sources aux **révisions publiées**, pas seulement au HEAD courant :
Socle 6570deb, Tiers 7642a09, Contrats 527874b, Factures 4e5a390,
Trésorerie 45fd268, Gateway 98e2ced, PWA e8990f9, ERP Shell 5f08d59.
Les images locales Contrats et PWA ont été lues par `docker image save` vers
un fichier temporaire anonyme : aucun conteneur lancé/créé, aucune image tirée.
Les tests utilisent seulement des fixtures hors dépôt et des fonctions Docker
simulées ; aucune opération backup/restore réelle n’est exécutée.

## Tableau de décision

| Sujet | État initial | Analyse | Correction éventuelle | État final |
|---|---|---|---|---|
| Profil Socle | preprod,secure, image 6570deb | Bootstrap conditionné par wavy.bootstrap.enabled ; secure sélectionné | Paramètres cookies explicites par mode et Swagger désactivé dans Compose | OK |
| Profil Tiers | Pas de fichier preprod | Générique + secure suffisent ; valeurs Compose prioritaires | Swagger/OpenAPI désactivés ; show-sql=false ; cookies explicites | OK |
| Profil Contrats | Pas de fichier preprod | secure et filtre de contexte sélectionnés ; recette n’apporte rien d’indispensable non injecté | Même durcissement Compose | OK |
| Profil Factures | preprod + secure Java | Flyway, validate, SQL init never résolus | Durcissement commun, aucun changement applicatif | OK |
| Profil Trésorerie | preprod + secure Java | Cohérent ; CORS Java conserve des origines locales internes | Pas de port hôte, Gateway impose le CORS public ; aucun changement applicatif | OK pour jalon |
| Profil Gateway | preprod ; WebFlux | Auth-filter actif par défaut ; routes et CORS injectés ; pas de session Servlet Gateway | Cookies documentés comme responsabilité Socle | OK |
| TLS | Aucun TLS démontré dans le lot | Nginx Shell écoute 80 ; aucun proxy TLS/certificat livré ; terminaison externe non vérifiée car VM hors périmètre | Choix B explicite ; HTTPS final à provisionner | B temporaire accepté |
| Secure cookie | true sur HTTP ; port déjà renommé HTTP | Exception localhost non portable ; cookie émis par Socle | false uniquement tunnel ; true obligatoire HTTPS ; HttpOnly/Strict conservés | CONDITIONNEL au mode validé |
| tunnel SSH | Loopback HTTP | SSH chiffre le transport, pas le protocole navigateur | Origine exacte localhost ; aucune exposition DB/API/Gateway | OK temporaire |
| PWA | Interne, sans upstream Shell | Bundle publié apiBaseUrl="/api" ; aucun appel par Shell ni smoke API | Documentée optionnelle, pas de port supplémentaire | OPTIONAL |
| stockage documentaire | Volume partagé, droits non préparés | Seul Contrats écrit des fichiers ; UID/GID image 100:101 | Montages Factures/Trésorerie retirés ; init contrats 0700/100:101 | OK |
| backup documentaire | Absent | DB contient les chemins des pièces : fichiers indispensables | Archive tar chiffrée + HMAC, lot format 2, arrêt propre des écritures | IMPLÉMENTÉ, tests statiques |
| restore documentaire | Absent | DB et fichiers doivent revenir du même lot | --with-documents + confirmation, contrôle tar, remplacement explicite, reprise après succès | IMPLÉMENTÉ, tests statiques |

## Résolution détaillée Tiers et Contrats

Activer un profil Spring ne nécessite pas un fichier homonyme : il sélectionne
les configurations/beans conditionnels et charge les fichiers spécifiques s’ils
existent. Les variables d’environnement remplacent les valeurs des fichiers.
Références : [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
et [Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html).

| Question | Tiers 7642a09 | Contrats 527874b |
|---|---|---|
| preprod accepté sans fichier dédié ? | Oui : nom valide ; aucun validateur applicatif ne le refuse | Oui, même constat |
| secure réellement actif ? | @Profile({secure,production}) sur chaîne et filtre ; branche local/gateway inactive | Chaîne et filtre secure actifs ; local/gateway/test inactifs ; double enregistrement Servlet désactivé |
| Groupes Spring | recette inclut secure, mais preprod,secure est explicite et n’a pas besoin de ce groupe | Idem |
| Autres annotations conditionnelles | Pas de @ConditionalOnProperty ou @ConfigurationProperties imposant recette trouvé dans src/main/java au commit ciblé | Idem |
| Flyway | enabled=true, validate-on-migrate=true, clean-disabled=true par environnement | Idem |
| DDL | SPRING_JPA_HIBERNATE_DDL_AUTO=validate | Idem |
| SQL init | SPRING_SQL_INIT_MODE=never | Idem |
| Swagger/OpenAPI | Initialement permitAll dans SecurityConfig ; désormais désactivé par propriétés Springdoc | Initialement protégé par auth ; désormais désactivé |
| Actuator | health/info exposés, détails never | health/info configurés, mais SecurityConfig refuse info et autres /actuator ; health seul accessible |
| Cookies/session | Ne crée pas WAVY_SESSION ; authentification vérifiée auprès de Socle ; réglages Servlet injectés au cas où une session technique est créée | Même principe |
| CORS | Liste injectée, credentials autorisés, wildcard global refusé par le code | Idem |
| Apport recette manquant ? | Aucun indispensable : URL DB/Socle, Flyway, show-sql, détails health et cookies sont explicitement injectés | Idem ; SQL init never également injecté |

Cette conclusion porte sur la résolution statique des propriétés/conditions aux
commits ciblés et sur le rendu Compose. Aucun contexte Spring, aucune base,
aucune migration n’a été démarré pour fabriquer une preuve runtime.

## Flux d’authentification et choix TLS

Windows → http://localhost:24443 → tunnel SSH → loopback VM:24443 → Nginx
ERP Shell:80 → Gateway:8088 → Socle:8080. Le POST `/api/auth/session` est
transmis au Socle ; celui-ci crée la session et renvoie WAVY_SESSION, HttpOnly,
Path=/ et SameSite=Strict. Gateway relaie Cookie/Authorization et consulte
`/api/profil` pour injecter un contexte authentifié. Les variables Servlet du
Gateway WebFlux ne suffisent donc pas à sécuriser la session applicative.

Avec Secure=true, certains navigateurs acceptent l’exception HTTP localhost,
mais ce n’est pas une garantie multiplateforme. SameSite=Strict est compatible
avec les requêtes de même site dans le Shell ; il ne chiffre pas HTTP. Aucun
test Windows réel n’a été réalisé. Voir [MDN Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)
et [MDN Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies),
qui signale notamment l’absence de l’exception localhost dans Safari.

**B retenu** : mode technique temporaire, COOKIE_SECURE=false exclusivement
avec mode tunnel et URL/CORS `http://localhost:<port HTTP>`. Les tests refusent
false en mode HTTPS. Le port reste lié à 127.0.0.1, seules les APIs internes
peuvent recevoir l’authentification. Aucune décision de domaine ni création de
certificat/clé réelle pour simuler A. Le nom WAVY_PUBLIC_HTTP_PORT était déjà
corrigé avant cette revue et est conservé.

Sortie de B : reverse proxy TLS + certificat approuvé + domaine décidé ; passer
mode=https, COOKIE_SECURE=true, URL/CORS HTTPS puis redéployer les composants
concernés par le chemin contrôlé. Le template Nginx Shell réécrit actuellement
X-Forwarded-Proto avec son schéma HTTP ; configurer cette chaîne de confiance
lors de la terminaison TLS. Socle force Secure à la création en mode HTTPS ;
à la suppression il invalide la session et émet Max-Age=0 avec SameSite=Lax.
Ces attributs de suppression différents ne changent pas l’identité nom/path du
cookie. Login/logout et headers proxy devront être validés au passage HTTPS.

## PWA

Aucun port publié, aucune référence PWA dans le Shell/nginx au commit 5f08d59,
aucun upstream PWA, aucun smoke test métier dépendant d’elle. La configuration
réellement embarquée a été retrouvée dans `usr/share/nginx/html/main-B6X6ECLC.js`
de l’image e8990f9 : `apiBaseUrl:"/api"`. L’URL est correcte pour un futur accès
même origine avec routage API. Son serveur statique seul ne fournit pas ce
proxy : ne pas prétendre une PWA publiquement utilisable aujourd’hui.

Elle est **OPTIONAL au premier jalon** : conservée dans Compose et dans
l’inventaire de 13 images contrôlées, mais pas nécessaire au bootstrap ni aux
smoke tests des six APIs. L’initialiseur actuel la démarre avec le lot ; cela
ne crée pas un besoin fonctionnel de point d’entrée PWA. Aucun port ajouté.

## Documents : contenu réel, permissions, sauvegarde

- Contrats : PieceJointeContratService écrit par Files.createDirectories et
  MultipartFile.transferTo dans `/app/data/contrats/<tenant>/<societe>/<contrat>/<UUID>.<ext>`.
  Le chemin absolu et les métadonnées sont en PostgreSQL. Suppression métier
  logique (`actif=false`) ; fichiers conservés. Les UUID et sous-répertoires
  préviennent les collisions usuelles.
- Factures : PieceJointeFactureService et PieceJointeSalaireService calculent
  hashes et chemins logiques (dont salaires/...), sans écrire ces fichiers.
  FactureVentePdfService utilise ByteArrayOutputStream ; extractions IA lisent
  getBytes. Aucun auteur de fichiers persistants trouvé dans src/main/java à
  4e5a390. Le backup ne prétend pas sauver des originaux jamais persistés par
  l’application : c’est une limite fonctionnelle existante, pas corrigée ici.
- Trésorerie : les imports lisent MultipartFile.getInputStream puis enregistrent
  les lignes en base ; aucun chemin persistant dans /app/data trouvé à 45fd268.

Le partage n’était donc pas nécessaire. Contrats seul conserve le volume writable
sur rootfs read_only. `/etc/passwd` et `/etc/group` de l’image publiée établissent
100:101 ; l’initialiseur prépare seulement le répertoire contrats avec ces
identifiants et mode 0700 après confirmation d’installation vide. Aucun volume
existant ni application n’a été modifié. Une migration d’UID dans une future
image devra être traitée explicitement. Ne jamais utiliser down --volumes.

Backup : arrêt gracieux de Gateway puis des cinq APIs, aucun autre acteur
écrivant en DB pendant la fenêtre ; cinq dumps et tar des pièces dans le même
lot, chiffrement identique, HMAC des six fichiers, archive relue avant publication.
L’utilitaire Docker futur n’a ni réseau ni rootfs writable, son image est épinglée,
son unique volume est monté readonly pour l’archive. Sur échec, reprise des
services arrêtés et aucune publication d’un lot incomplet. **Le backup impose
une maintenance globale même si le remplacement applicatif reste ciblé.**

Restore : option --with-documents obligatoire et confirmation destructive
explicite ; même lot format 2, HMAC/checksums, déchiffrement de tout le lot et
validation tar avant écriture. Liens, types spéciaux, traversées, doublons et
UID/GID inattendus refusés. Cinq pg_restore puis remplacement de contrats,
permissions tar conservées. Reprise/health/smoke après succès. Une erreur avant
reprise laisse les backends arrêtés ; pas de transaction globale DB/fichiers.
Les anciens lots sans documents ne sont pas acceptés comme restauration complète.

## Validation et secrets

- **25/25 tests PREPROD** : 15 tests configuration et 10 tests garde-fous.
  Les 20 tests précédents passent toujours, avec fixture documentaire adaptée
  au format 2. Quatre tests ajoutés lors de la passe précédente : HTTPS impose Secure ; refus d’un volume
  partagé avec Factures ; validation chemins/types/propriétaires tar ; reprise
  des seuls services concernés après arrêt simulé en échec. Le test HMAC
  existant vérifie aussi l’altération documentaire.
- Tests d’historique : OK ; fichiers temporaires uniquement.
- bash -n exécuté séparément pour chaque scripts/*.sh puis wavy : OK.
- Syntaxe Python analysée sans création de pycache : OK.
- docker compose --env-file <temp-factice> --env-file versions/preprod.env
  -p wavy-preprod -f docker-compose.preprod.yml config --quiet : **code 0**.
- JSON résolu inspecté par assertions de validation, sans sortie de secrets :
  seul ERP Shell publie 127.0.0.1:24443→80 ; 13 images individuelles ; aucun
  build ; profils preprod,secure ; PWA interne ; documents Contrats seuls.
- git diff --check : OK. git status/git diff examinés ; index vide.
- Aucun PAT, clé API ou clé privée détecté par signatures dans les ajouts ;
  revue des affectations sensibles : uniquement placeholders, références de
  variables et fixtures clairement factices. Le modèle ne contient que
  CHANGE_ME pour ses secrets non vides. Aucun vrai .env.preprod créé ; ignoré.

Les vérifications d’intégrité et OCI ont aussi été rendues indépendantes du
mode optimisé Python (conditions explicites au lieu d’assert opérationnels).
Aucun secret détecté n’a été affiché : **SECRET_ADDED=NO**.

```text
TIERS_PREPROD_PROFILE=OK
CONTRATS_PREPROD_PROFILE=OK
PREPROD_TLS_STRATEGY=B_TUNNEL_HTTP_TEMPORAIRE_PUIS_HTTPS
COOKIE_SECURE_COMPATIBLE=CONDITIONAL
PWA_PREPROD=OPTIONAL
DOCUMENT_BACKUP_REQUIRED=YES
DOCUMENT_BACKUP_IMPLEMENTED=YES
DOCUMENT_RESTORE_IMPLEMENTED=YES
PREPROD_TESTS=25/25_PASS
COMPOSE_CONFIG=OK_CODE_0
GIT_DIFF_CHECK=OK
SECRET_ADDED=NO
```

RECETTE modifiée : NON. LOCAL modifié : NON. Dépôts applicatifs modifiés : NON.
VM PREPROD modifiée : NON. PostgreSQL modifié : NON. Flyway exécuté : NON.
Build Docker effectué : NON. Déploiement effectué : NON.
Backup/restore/rollback réel : NON. Conteneur/volume PREPROD créé : NON.
Git add/commit/push : NON.

## Inventaire initial de la passe précédente

Tous les fichiers ci-dessous appartiennent au lot PREPROD préparé ; aucune
modification hors périmètre identifiée. M = modifié suivi ; ?? = nouveau non suivi.

```text
 M .env.preprod.example
 M .github/workflows/preprod-validation.yml
 M .gitignore
 M README_PREPROD.md
 M docker-compose.preprod.build.yml
 M docker-compose.preprod.yml
 M docs/deployment.md
 M scripts/_common.sh
 M scripts/backup-preprod.sh
 M scripts/deploy.sh
 M scripts/restore-preprod.sh
 M scripts/rollback.sh
 M scripts/smoke-test.sh
 M scripts/test-database-from-zero.sh
 M scripts/validate-preprod-config.sh
 M wavy
?? docs/images.md
?? docs/preprod-review.md
?? docs/smoke-tests.md
?? docs/versioning.md
?? scripts/_preprod.sh
?? scripts/initialize-preprod.sh
?? scripts/preprod_backup_manifest.py
?? scripts/preprod_config.py
?? scripts/release-preprod.sh
?? scripts/test-preprod-config.py
?? scripts/test-preprod-guards.py
?? scripts/validate-preprod-runtime.sh
?? versions/history/preprod/contrats-api.tsv
?? versions/history/preprod/contrats-front.tsv
?? versions/history/preprod/erp-shell.tsv
?? versions/history/preprod/factures-api.tsv
?? versions/history/preprod/factures-front.tsv
?? versions/history/preprod/gateway.tsv
?? versions/history/preprod/pwa.tsv
?? versions/history/preprod/socle-api.tsv
?? versions/history/preprod/socle-front.tsv
?? versions/history/preprod/tiers-api.tsv
?? versions/history/preprod/tiers-front.tsv
?? versions/history/preprod/tresorerie-api.tsv
?? versions/history/preprod/tresorerie-front.tsv
?? versions/preprod.digests
?? versions/preprod.env
```

## Inventaire final précis du lot à revoir pour commit

```text
 M .env.preprod.example
 M .github/workflows/preprod-validation.yml
 M .gitignore
 M README_PREPROD.md
 M docker-compose.preprod.build.yml
 M docker-compose.preprod.yml
 M docs/deployment.md
?? docs/images.md
?? docs/preprod-final-review.md
?? docs/preprod-review.md
?? docs/smoke-tests.md
?? docs/versioning.md
 M scripts/_common.sh
?? scripts/_preprod-documents.sh
?? scripts/_preprod.sh
 M scripts/backup-preprod.sh
 M scripts/deploy.sh
?? scripts/initialize-preprod.sh
?? scripts/preprod_backup_manifest.py
?? scripts/preprod_config.py
?? scripts/preprod_document_archive.py
?? scripts/release-preprod.sh
 M scripts/restore-preprod.sh
 M scripts/rollback.sh
 M scripts/smoke-test.sh
 M scripts/test-database-from-zero.sh
?? scripts/test-preprod-config.py
?? scripts/test-preprod-guards.py
 M scripts/validate-preprod-config.sh
?? scripts/validate-preprod-runtime.sh
?? versions/history/preprod/contrats-api.tsv
?? versions/history/preprod/contrats-front.tsv
?? versions/history/preprod/erp-shell.tsv
?? versions/history/preprod/factures-api.tsv
?? versions/history/preprod/factures-front.tsv
?? versions/history/preprod/gateway.tsv
?? versions/history/preprod/pwa.tsv
?? versions/history/preprod/socle-api.tsv
?? versions/history/preprod/socle-front.tsv
?? versions/history/preprod/tiers-api.tsv
?? versions/history/preprod/tiers-front.tsv
?? versions/history/preprod/tresorerie-api.tsv
?? versions/history/preprod/tresorerie-front.tsv
?? versions/preprod.digests
?? versions/preprod.env
 M wavy
```

Fichiers hors périmètre préservés : tous les fichiers spécifiques RECETTE/LOCAL,
les autres fichiers du dépôt et tous les dépôts applicatifs. Aucun staging.
Les historiques PREPROD ne contiennent encore que les en-têtes, sans DEPLOY.

Message proposé (non exécuté) :

```text
feat(devops): industrialise environnement preprod
```

**GO POUR COMMIT DEVOPS PREPROD**

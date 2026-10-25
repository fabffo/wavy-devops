# Livraison cohérente PWA + Notes de frais — préparation inactive

État au 20 octobre 2026 : quatre images publiées selon la déclaration de livraison et vérifiées
localement (RepoDigests et labels OCI). Préparation inactive, aucun déploiement effectué ici.
**Correctifs du 21 octobre : prêts pour revue locale**, voir la dernière section. Aucun GO de déploiement ou de commit.
Les manifestes actifs `docker-compose.preprod.yml`, `docker-compose.recette.yml`, les versions,
digests et historiques ne sont pas modifiés. Les fichiers de ce répertoire ne sont appelés
par aucune commande de déploiement active. Ne pas les activer séparément.

## Architecture et accès

La PWA de production utilise `/pwa/` (base Angular, manifeste, routes, ressources et service worker).
Le Shell ouvre la PWA en pleine page sur la même origine ; Notes de frais possède aussi un lien.
La session serveur existante est réutilisée. Les guards relisent la session à chaque navigation ;
un changement de société utilise `POST /api/auth/session/societe`. Les anciens appels sont annulés
et les pages sont recréées au changement de tenant, société ou utilisateur. Une expiration 401
vide le contexte et renvoie vers la connexion. La reprise après retour dans l'application relit
la session serveur. Les APIs revalident le contexte et les rôles authentifiés.

Le service worker ne cache que les bundles et icônes publics, pas les API ou justificatifs.
Son périmètre est `/pwa/`. La mise à jour est proposée à l'utilisateur avant rechargement pour
éviter de perdre un formulaire en cours. Les téléchargements privés portent `no-store` et
les aperçus utilisent des URLs blob temporaires, avec iframe sandbox pour PDF.

**Double fermeture par défaut** : `public/pwa-integration.json` vaut false et l'image Shell
inclut `nginx-pwa-disabled.conf`, qui répond 404 pour `/pwa`. Les liens sont conditionnés au
commutateur et aux droits Notes de frais dans le Shell. L’override candidat monte explicitement deux fichiers fermés. Les fichiers `enabled` sont
des références pour la future activation contrôlée, jamais chargées par cet override. Le commutateur est une règle de présentation,
pas une autorisation ; les guards et les APIs restent obligatoires.

## Stockage et cycle de vie

Réutilisation du volume documentaire existant `documents-preprod` et de sa chaîne d'archivage,
chiffrement AES-256/PBKDF2, manifeste HMAC et restauration avec arrêt des écritures.
Le sous-répertoire `notes-frais` est monté seul dans Factures API à `/app/justificatifs`, sans
lui donner accès aux documents Contrats. Le moteur de dépôt est spécifique aux notes parce que
le service Contrats dépend de ses propres entités et droits et accepte d'autres formats.

Une note possède un original courant, UUID serveur dans les colonnes `piece_*` existantes.
JPEG/PNG/PDF sont vérifiés puis écrits réellement (fichier privé, fsync, renommage atomique,
fsync du dossier) avant association transactionnelle. Le rollback supprime le nouveau fichier.
Remplacement et suppression effacent l'ancien original seulement après commit. La réconciliation
rattrape les orphelins et temporaires de crash après une grâce de 24 h par défaut (minimum 600 s),
avec vérification de l'absence de référence en base. Les dépôts ont un timeout de transaction
120 s. Une indisponibilité de la base interrompt le nettoyage sans suppression non vérifiée.
Aucun lien symbolique n'est suivi. Aucun chemin fourni par le navigateur n'est utilisé.

Limite serveur configurable via `WAVY_FACTURES_JUSTIFICATIF_MAX_BYTES` : défaut 10 Mio,
maximum de sécurité 50 Mio. Coordonner les limites multipart et reverse proxy si cette politique
est modifiée. L'interface mobile lit `justificatifMaxBytes` dans le fichier public de politique. Aligner cette
valeur et les limites serveur/proxy lors de toute modification de la politique (10 Mio pour ce lot).
Les anciennes pièces plus grandes que la nouvelle limite d'import restent lisibles jusqu'à 50 Mio.
Les images sont limitées à 25 millions de pixels. Les contrôles de format ne remplacent pas
un antivirus ; prévoir une politique adaptée avant ouverture à des utilisateurs non maîtrisés.

Aucune modification de schéma et aucune migration nouvelle. Les anciennes références calculées
sans original ne sont jamais présentées comme un fichier conservé : l'interface signale leur absence.

## Préparation DevOps et promotion future — NE PAS EXÉCUTER pendant cette revue

1. Les quatre images publiées sont renseignées dans `release-plan.json.images` et ont été
   vérifiées localement. `validate-bundle.py --local-images` contrôle leurs RepoDigests,
   labels OCI et références immuables. Cela ne constitue ni une validation runtime ni un GO
   de commit : les anomalies de la revue finale ci-dessous restent à corriger.
2. Faire valider le domaine et le certificat HTTPS : PREPROD est actuellement décrite avec un tunnel
   HTTP, ce qui ne suffit pas pour un smartphone distant. `edge-https.conf.template` est un modèle
   inactif de terminaison TLS vers le port ERP loopback. Ne pas exposer ce port directement.
   La configuration machine devra utiliser `WAVY_ACCESS_MODE=https`, `WAVY_COOKIE_SECURE=true`,
   une origine HTTPS exacte pour `WAVY_PUBLIC_URL` et CORS. Préserver Anthropic, modèle et clé.
   Le cookie Socle doit garder Path=/, HttpOnly et SameSite existants. Aucun secret/certificat ici.
3. Provisionner `notes-frais` dans le volume documentaire existant avec le compte applicatif attendu
   (100:101, confirmé par `id` dans l’image Factures API finale, sans réseau), mode 0700, avant de monter son subpath. Ne jamais
   remplacer le volume ni changer les propriétaires du répertoire Contrats. La racine doit être
   réelle, préexistante et durable ; aucun fallback vers le disque éphémère n'est autorisé.
4. Utiliser l’adaptateur candidat et son validateur après revue complète.
   `integration-scripts.patch` est désormais une référence historique, à ne pas appliquer :
   il ne décrit pas l’orchestrateur ni le nouveau validateur. Le candidat exige le montage subpath.
   Les sauvegardes incluent **contrats ET notes-frais**, sont relues avant publication et authentifiées
   par le manifeste existant. La restauration remet les deux racines avec les cinq bases et les APIs
   arrêtées. Les anciennes archives Contrats seules restent acceptées et recréent une racine Notes
   de frais vide, cohérente avec une sauvegarde de base antérieure au nouveau parcours.
5. Examiner `compose.override.yml` avec `WAVY_PWA_CANDIDATE_DIR` absolu et les quatre références
   `PWA_RELEASE_*_IMAGE` immuables. Le test Compose utilise exclusivement des valeurs factices.
   Ce fichier est une préparation ; il n'est pas chargé par les scripts actifs. Lors de la promotion,
   intégrer les montages et dépendances dans la configuration revue tout en conservant le mécanisme
   standard versions/digests et les contrôles de release ciblée. Ne pas désactiver les garde-fous.
6. Livraison fonctionnelle unique : sauvegarde complète vérifiée, puis déploiement ciblé Factures API,
   Factures Front puis PWA, contrôles session/stockage/isolation, **Shell et activation publique en dernier**.
   Si une étape échoue, garder la route fermée ; ne pas déclarer le parcours livré partiellement.
   Préserver `preprod_reload_erp_shell_nginx`, ses contrôles DNS, `nginx -t`, reload et contrôles proxy.
   Les historiques de chaque image ne sont mis à jour qu'après les contrôles runtime réussis.
7. Rollback : fermer d'abord la route et les liens, revenir au lot applicatif cohérent précédent avec
   les digests déjà validés. Conserver le volume et les colonnes existantes. Aucun restore automatique.
   Un ancien code Notes de frais peut écraser ses métadonnées documentaires s'il est remis en écriture :
   charger d'abord `edge-rollback-readonly.conf.template`, qui ferme `/pwa/` et refuse
   les écritures HTTP Notes de frais sur le proxy public indépendamment de l'image Shell.
   Garder ce parcours en lecture seule jusqu'au rétablissement du lot compatible. Une restauration
   explicite doit remettre ensemble bases ET fichiers ; les restores distribués ne sont pas atomiques.

## Tests locaux reproductibles

- `python3 preparation/pwa-notes-frais/test-candidate.py` : 9 tests, Compose fictif, archives sûres,
  chiffrement/déchiffrement, intégrité HMAC, restauration d'octets originaux, compatibilité ancien lot,
  scripts candidats et refus d'un lot d'images incomplet. Les dumps sont des fixtures, pas de vraies DB.
- `python3 preparation/pwa-notes-frais/test-nginx-local.py` : nginx -t sur l’image Shell exacte déjà locale,
  réseau coupé, sans build/pull et sans démarrer de serveur : route fermée, candidate,
  terminaison HTTPS et rollback (certificat fictif temporaire, non conservé).
- Suites actives config/garde-fous/Nginx/historique : doivent rester conformes avant promotion.
- Tests Java isolés, avec `spring.flyway.enabled=false`, Hibernate create-drop et fixture SQL de test
  explicitement sélectionnée pour la table native hors JPA ; aucun Flyway exécuté ni base existante utilisée.
- Builds production des trois Angular ; leurs tests unitaires.
- Depuis Shell : `npx playwright test --config playwright.pwa-local.config.ts`. Les trois builds locaux
  sont servis sur 127.0.0.1. APIs et IA sont simulées, service worker bloqué pour déterminisme.
  Parcours JPEG/PNG/PDF réels côté Java ; navigateur : PNG et PDF, société, sauvegarde multipart,
  consultation PWA puis ERP, rechargement, téléchargement et URL mobile avec session expirée.
  Ce test ne valide ni l'IA distante, ni un navigateur connecté au backend réel, ni l'installation native.

## Validation réelle PREPROD à planifier, non exécutée

Sur navigateur puis Android Chrome et iOS Safari, en HTTPS : login ERP, accès menu et raccourcis,
retour Notes de frais, changement de société et vérification serveur, photo caméra, import PDF,
extraction IA réelle, correction, création, aperçu et téléchargement ERP/PWA, rechargement et
redémarrage/recréation du conteneur conservant le volume. Tester expiration/déconnexion, retour
au premier plan, refus cross-tenant/société/utilisateur et supervision, installation, mise à jour
service worker et absence de cache privé, lecture PDF et téléchargements mobiles.
Tester une sauvegarde/restauration complète sur une infrastructure isolée avant l'activation réelle.
Ne déclarer ces contrôles réussis qu'après leur exécution. Le domaine/certificat,
les essais physiques et la restauration opérationnelle restent des prérequis de déploiement.

Voir `FILES.txt` pour l'inventaire complet de l'évolution (les fichiers locaux exclus n'y figurent pas).

## Résultats de la validation locale de cette évolution

Suites ci-dessous réexécutées après correction des deux anomalies, le 15 octobre 2026.
Le contrôle nginx -t antérieur est conservé : ses fichiers de configuration sont inchangés.

- Shell : 20/20 tests ; Factures Front : 163/163 ; PWA : 55/55.
- Factures API : 157 tests ciblés Notes de frais / documents / extraction / services achat-vente,
  Maven verify réussi, Flyway désactivé, bases Testcontainers uniquement.
- Trois builds Angular production réussis. Avertissements de budget Shell et Factures Front.
- Playwright Chromium local : quatre scénarios réussis, APIs simulées (PNG, PDF, session expirée, réponses de session concurrentes).
- Config active : 36/36 ; garde-fous : 10/10 ; Nginx : 5/5 ; historique : huit contrôles réussis.
- Candidat : 8/8 ; nginx -t : route fermée et candidate conformes, conteneur local sans réseau.
- Compose avec valeurs factices, syntaxe Bash et git diff --check conformes.
- Manifestes actifs, versions, digests, historiques, configuration IA et fichiers locaux préservés.

Commande Java reproductible depuis wavy-factures-api, sans migration Flyway :

```bash
mvn -q -Dspring.flyway.enabled=false -Dspring.jpa.hibernate.ddl-auto=create-drop \
  -Dspring.jpa.defer-datasource-initialization=true -Dspring.sql.init.mode=always \
  -Dspring.sql.init.schema-locations=classpath:schema-sans-flyway-fixture.sql \
  -Dspring.test.context.cache.maxSize=3 \
  -Dtest='*NoteFrais*,Justificatif*Tests,*ExtractionIaServiceTests,*ExtractionNormalisation*Tests,FactureAchatServiceTests,FactureVenteServiceTests' verify
```

## Corrections des deux anomalies de concurrence (revue finale)

### 1. Remplacements de justificatifs à partir d'un snapshot PostgreSQL obsolète

Reproduction : une transaction T2 charge une note portant l'original A. Pendant qu'elle attend,
T1 remplace A par B et valide. T2 dépose de nouveau A puis valide. Sans verrou et relecture,
Hibernate DynamicUpdate compare les métadonnées au snapshot A : la nouvelle référence UUID
est enregistrée, mais le hash redevenu A peut être omis de l'UPDATE. La base conserve alors
le hash B pour les octets A. Les deux dépôts réussissent ; le téléchargement renvoie 404
au contrôle d'intégrité. Un ancien fichier peut aussi rester orphelin.

Attendu : un dernier dépôt validé possède toujours une référence, des métadonnées et des octets
cohérents ; une lecture déjà engagée ne perd pas son original pendant un remplacement/suppression.

Correction : verrou PostgreSQL exclusif sur la note, avec périmètre tenant/société/utilisateur
ou supervision, avant les mutations et changements de statut. Relecture du snapshot lors de la
première acquisition ; les appels imbriqués conservent les changements déjà réalisés sous verrou.
Les consultations documentaires gardent un verrou partagé jusqu'à la copie des octets.
Les transformations de plusieurs notes prennent les verrous dans l'ordre des identifiants.
Un verrou transactionnel consultatif tenant/société/hash sérialise également le contrôle des
doublons entre créations de notes distinctes, sans changer les règles d'accès ni de doublon.
Aucune migration : ces verrous utilisent le schéma existant. Les callbacks de commit/rollback
et la réconciliation restent en place ; aucun fichier existant n'est réparé automatiquement.

Composants : NoteFraisRepository, NoteFraisService, NoteFraisJustificatifService.
Le nouveau NoteFraisJustificatifConcurrenceTests utilise PostgreSQL Testcontainers réel,
transactions et barrières/latches : snapshot obsolète, lecture/remplacement, lecture/suppression,
créations simultanées du même original, statut devenu non modifiable, rollback du remplacement.
Le test du snapshot échoue avant correction (404 au lieu de 200), puis réussit après correction.
La suite existante vérifie notamment la modification multipart, les droits, les erreurs disque
et le nettoyage après commit/rollback. Le stockage testé est un répertoire temporaire local.

### 2. Réponses de session reçues dans le désordre dans la PWA

Reproduction : le guard de navigation lance GET /auth/session et sa réponse société A est retardée.
Un retour au premier plan lance une seconde lecture, qui reçoit la société B. La réponse A arrive
ensuite. Les lectures partageaient la même génération : A écrasait le contexte B, alors que la
session serveur était B. Les pages/en-têtes pouvaient revenir à une ancienne société (les contrôles
serveur restent obligatoires). Une réponse filtrée sans émission pouvait aussi bloquer les
rafraîchissements ultérieurs, dont le drapeau n'était libéré que sur next/error.

Attendu : seule la lecture la plus récente fait autorité ; les guards et rafraîchissements en
attente reçoivent son résultat. Un changement de société est confirmé par la session serveur.

Correction : annulation du GET remplacé et distribution de la dernière réponse à tous les lecteurs
en attente. Les POST de changement de société sont sérialisés, jamais annulés après envoi ; les
lectures attendent la dernière confirmation. Une génération d'authentification empêche les
réponses antérieures à une déconnexion de restaurer le contexte. La file continue après erreur ;
les lectures lancées depuis le callback d'un POST sont également débloquées. Les drapeaux de
synchronisation et de profil sont libérés par finalize, même sur complétion sans valeur.
AuthService traite une restauration terminée sans résultat comme non authentifiée.

Composants : ContextService, AuthService, App, ProfilPage et leurs tests.
Le test des deux GET échoue avant correction (société A et résultats [B,A]) puis passe
(société B et résultats [B,B]). Les tests couvrent aussi les POST simultanés, l'erreur dans la
file, la déconnexion pendant une mutation et le rafraîchissement terminé sans résultat.
Un quatrième scénario Chromium reproduit navigation + focus et retour tardif de l'ancienne
réponse ; le contexte et le sélecteur restent sur B. APIs simulées, pas de backend réel dans
ce scénario navigateur. Les droits et le stockage sont vérifiés séparément côté Java.


## Revue initiale de préparation release — 20 octobre 2026 (historique)

Décision initiale : **NO-GO POUR REVUE RELEASE PREPROD**. Les blocages constatés
ci-dessous sont conservés comme historique ; la correction candidate est décrite dans la
section « Orchestrateur coordonné » à la fin de ce document. Le lot d’images est statiquement cohérent ; cela ne suffit
pas à rendre le déploiement coordonné exécutable.

### Preuves des images et portée des vérifications

`release-plan.json` contient les quatre tags, digests, références épinglées, plateformes et
labels OCI réellement lus dans le cache Docker local Unix. Les trois digests complets fournis
correspondent exactement. Le digest Factures API, tronqué à `sha256` dans la demande, a été
retrouvé dans son RepoDigest local :
`sha256:a414a866c910bd20a4c8af4018fc0e31db513ffff1cca76b15c913807f75d0e5`.
Les quatre images sont linux/amd64, version OCI 0.1.0, source GitHub de leur composant et
révision conforme au suffixe du tag. Le registre distant n’a pas été réinterrogé.
Aucun secret de registre ni fichier dotenv machine n’a été lu pour ces contrôles.

Le Shell final contient réellement la route `/pwa` fermée et `enabled:false`.
Son template Nginx conserve `/api/`, les cinq routes `/modules/.../` et le fallback ERP.
Le snippet ouvert enlève le préfixe `/pwa/` vers le serveur PWA, transmet Cookie/Host/proto
et désactive le cache proxy. La terminaison HTTPS conserve le chemin de toutes les requêtes.
La syntaxe Nginx est testée sur le template extrait de cette image, pas seulement sur un checkout.
La session commune suppose une même origine HTTPS, cookie Path=/, HttpOnly, Secure et politique
SameSite PREPROD conservée (Strict dans Compose), ainsi que CORS exact et absence de cache privé.
Ce sont des prérequis runtime, pas une session réellement testée.

Le processus Factures API de l’image finale s’exécute en uid 100/gid 101. Le montage candidat
RW est limité au subpath `notes-frais` du volume existant ; Contrats conserve sa racine.
Le mode 0700 du dossier et 0600 des fichiers permet la lecture/écriture au propriétaire.
Aucun volume réel n’a été inspecté ou modifié : l’existence du subpath, les droits effectifs,
la capacité Docker/Compose à le monter, l’espace disque et la persistance restent à éprouver.
Ne jamais créer le dossier par un démarrage applicatif sur un disque éphémère, ni faire de
chown récursif du volume Contrats. Vérifier les droits avec le compte 100:101 avant ouverture.

### Blocages DevOps observés

1. `release-preprod.sh` traite un seul composant, verrouille par invocation et lance
   `up --no-deps`. Les dépendances healthy ajoutées au candidat ne constituent donc pas un
   verrou de release. Aucun orchestrateur du lot ni fermeture automatique en cas d’échec
   après activation n’existe. La fermeture par défaut est maintenant explicite dans l’override,
   mais elle ne ferme pas automatiquement un parcours déjà ouvert en exploitation.
2. Les scripts actifs ne chargent pas cet override. Le patch candidat ne suffit pas à la
   promotion : son `preprod_config.py` refuse encore les bind mounts et attend les images
   taguées des manifestes actifs ; son rendu standard ne charge pas l’override. Le rendu
   Compose local réussi prouve la syntaxe et la fusion, pas l’acceptation par ce validateur.
   Il faut une intégration revue du stockage, des références et des montages contrôlés,
   sans neutraliser la validation générale, les labels, les historiques ou les protections Git.
3. Le backup actif archive seulement Contrats. Promouvoir et vérifier le patch documentaire
   AVANT la première écriture Notes de frais. Le backup candidat exige le dossier notes-frais :
   pour la première promotion, conserver un backup ancien complet, créer le dossier vide
   avec les bons droits, puis produire le nouveau backup complet avant de remplacer les images.
4. La restauration candidate remplace cinq bases et deux racines documentaires avec les
   backends arrêtés, après HMAC, déchiffrement et catalogues pg_restore. Elle reste distribuée,
   sans atomicité entre bases/documents. Un échec intermédiaire impose de garder les backends
   arrêtés et l’accès fermé jusqu’à reprise du même lot. Aucun restore réel effectué ici.

### Ordre précis de l’opération future (non exécutée)

1. Approuver l’intégration DevOps et l’orchestrateur. Sur la cible autorisée, prendre un verrou
   de lot unique ; vérifier identité hôte/projet, Git propre, disque, outils et support subpath,
   les quatre RepoDigests/labels/plateformes et les digests précédents de rollback. Préserver
   IA et secrets machine. Vérifier HTTPS, certificat, cookies, CORS et contexte smoke autorisé.
2. Fermer la route PWA et les liens AVANT mutation ; vérifier effectivement les 404 externes.
   Prévoir un canal de tests interne contrôlé pour les parcours avant ouverture publique.
3. Sauvegarder le lot existant avec la chaîne actuelle ; vérifier HMAC et restaurabilité sur
   infrastructure isolée. Préparer uniquement le dossier notes-frais vide 100:101/0700 dans
   le volume existant. Intégrer la chaîne documentaire candidate revue ; produire puis
   restaurer à blanc un lot des cinq bases ET contrats/notes-frais. Les fixtures locales ne
   remplacent jamais cet exercice. Faire cela avant toute nouvelle écriture applicative.
4. Déployer **Factures API** au digest exact, route toujours fermée ; contrôler santé,
   configuration stockage, droits réels et absence d’erreur de validation de schéma/migration.
   Aucun changement de politique Flyway et aucune migration manuelle dans ce lot.
5. Déployer **Factures Front** au digest exact ; vérifier ERP et parcours Notes de frais.
6. Déployer **Wavy PWA** au digest exact ; vérifier santé, base href et ressources `/pwa/`,
   service worker limité à ce scope et absence de cache de session/documents.
7. Avec accès de test contrôlé, vérifier session ERP/PWA, expiration/déconnexion, changement
   de société, isolation tenant/utilisateur, JPEG/PNG/PDF, upload/lecture/téléchargement,
   limites, redémarrage conservant les documents, routes ERP/API et scénarios Android/iOS.
   Lier les preuves aux quatre digests réellement en cours, pas seulement à leurs tags.
8. Déployer **ERP Shell en dernier**, initialement fermé, puis seulement après tous les contrôles
   activer route et liens dans une transaction d’activation gérée par l’orchestrateur.
   Préserver `preprod_reload_erp_shell_nginx` : résolution Gateway, nginx -t, reload et
   requêtes proxy après reload. Effectuer les contrôles externes HTTPS et de non-régression.
   Les historiques restent append-only et ne sont validés qu’après réussite des contrôles runtime.
9. Sur toute erreur, y compris après ouverture : l’orchestrateur doit fermer route ET liens,
   recharger/vérifier Nginx et prouver les 404. Une simple dépendance Compose, un fichier
   de présentation false ou une consigne manuelle ne satisfait pas cette exigence.
10. Pour rollback, fermer d’abord la PWA et bloquer les écritures Notes de frais à l’edge
    avec le modèle readonly, vérifier cette protection, puis rétablir le lot précédent cohérent
    aux digests historiques. Recharger les upstreams et refaire health/smoke sans ouverture PWA.
    Les clients déjà installés peuvent encore exécuter leurs bundles : bloquer aussi les écritures
    API, pas seulement `/pwa/`. Conserver le volume ; ne pas restaurer automatiquement une base.
    Si un restore est explicitement décidé, arrêter les six backends et remettre ensemble les
    cinq bases et les deux racines du même backup authentifié, puis contrôles avant reprise.
    Ne jamais remettre en écriture un ancien code qui pourrait écraser les métadonnées `ndf:`.

### Vérifications locales de cette revue

- Lot : `validate-bundle.py --local-images`, références/labels/plateformes conformes.
- Candidat : 9 tests, Compose avec valeurs fictives, archive documents chiffrée/HMAC,
  restauration d’octets, rejet des archives dangereuses, compatibilité ancien format,
  patch appliqué uniquement dans une copie temporaire, fermeture par défaut.
- Nginx : quatre nginx -t réussis, conteneurs jetables locaux sans réseau, sans serveur,
  sans pull et sans build. Cela ne teste pas DNS réel, TLS public ou proxy fonctionnel.
- Suites actives réexécutées : configuration 36/36, garde-fous 10/10, Nginx 5/5,
  build-image 14/14 ; historique version/digest : huit contrôles réussis.
- Compose rendu avec environnement fictif puis avec les quatre références exactes : conforme ;
  les services hors lot restent identiques. Aucun accès à une configuration machine réelle.
- `bash -n` sur `wavy`, tous les scripts actifs et les scripts Bash candidats : conforme.
  `git diff --check` conforme ; aucun diff dans les manifestes actifs, versions, historiques
  ou scripts actifs. Aucun commit, push, build Docker, déploiement ou modification de base.

Non validés ici : restauration PostgreSQL réelle, permissions/persistance sur la cible,
HTTPS public et cookies réels, compatibilité fonctionnelle des quatre images avec les autres
APIs existantes, navigateur/backend réel, mobiles physiques, activation/fermeture automatique
et rollback opérationnel. Le compte rendu historique du 15 octobre ci-dessus reste conservé ;
il ne constitue pas une réexécution des tests applicatifs des images par cette revue.


## Orchestrateur coordonné — correction candidate du 20 octobre 2026

Décision avant revue finale : **GO POUR REVUE ORCHESTRATEUR PWA PREPROD**, uniquement pour revue du code
candidat et de ses tests locaux. Aucun GO de déploiement ou d’activation réelle. La décision
initiale et les résultats historiques ci-dessus restent conservés. Aucun script ni manifeste
actif, aucun historique de versions, aucun dépôt applicatif n’a été modifié par cette correction.
Les fichiers déjà présents dans ce candidat ont été conservés et amendés au besoin.

### Causes et corrections

Le chemin actif `deploy.sh preprod` délègue à `release-preprod.sh`, qui traite un composant
et prend son verrou pour cette seule invocation. Quatre appels successifs laissent des
intervalles entre verrous ; `up --no-deps` ignore les conditions healthy de Compose. Il n’existait
pas de reçu de préparation/validation pour autoriser une activation globale, ni de fermeture
sur échec de l’ensemble. Le nouvel orchestrateur possède son verrou pendant toute une action
et gère explicitement chaque transition. Il n’appelle pas quatre fois le script de release actif.

Le validateur candidat précédent était une copie du validateur actif : les bind mounts étaient
tous refusés et les images restaient comparées aux tags des anciennes versions actives.
Le nouveau `scripts/preprod_config.py` importe le validateur actif, vérifie les différences
candidates par liste fermée, puis normalise uniquement ces différences avant de réappliquer
**toute** la validation générale active. Il rend réellement le Compose candidat aux références
du plan et ne change aucune version active. Le patch `integration-scripts.patch` est conservé
comme référence historique ; ne pas l’appliquer pour installer ce nouveau mécanisme.

### Machine d’état, verrou et traces

Entrée : `scripts/release-pwa-preprod.sh`, moteur `scripts/release_pwa_preprod.py`.
Sans `--execute-on-approved-host`, la commande refuse toute exécution runtime. Même avec
cette option elle exige l’hôte `wavy-preprod`, aucun override Docker distant, puis le daemon
Unix local système. Aucune de ces actions runtime n’a été exécutée pendant cette correction.

Chaque action acquiert elle-même `deployments/preprod.lock` avec un flock exclusif non bloquant,
sur le même inode que les releases, backups et restores actifs. Le verrou n’est jamais supprimé.
La concurrence est refusée avant toute fermeture ou mutation. Le backup hérite du descripteur
verrouillé ; le test local vérifie l’absence de deadlock et le maintien de l’exclusion.

L’état privé `deployments/pwa-release/state.json` est écrit atomiquement, fsync fichier et dossier,
en 0600 dans un répertoire 0700. Il contient l’identifiant du lot, le hash du plan, le hash des
sources/configurations et du dotenv (jamais leur contenu secret), le snapshot des quatre images
précédentes, les étapes achevées, les images/conteneurs observés et le reçu du backup. La validation
et l’activation refusent une configuration ou un conteneur changé depuis la préparation.
Le journal JSONL append-only en 0600 contient uniquement UTC, identifiant du lot, code d’action
et résultat. Les sorties enfants, erreurs brutes, dotenv, identifiants de connexion et preuves
fonctionnelles ne sont jamais reproduits dans les journaux. Les preuves restent dans l’état privé.

Transitions normales : `preparing → prepared → validated → activating → active`.
Tout échec d’action, y compris pendant les contrôles après ouverture, tente de fermer le Shell
avant d’enregistrer `failed`. SIGINT/SIGTERM empruntent également ce chemin. L’état antérieur
permet un rollback après interruption en préparation ou pendant un rollback.
Une activation refusée ne peut pas être relancée sans remettre le lot en état cohérent.

### Préparation fermée (`prepare`)

1. Valider la preuve préalable privée et récente (moins de 24 h) : exercice de restauration des
   cinq bases/documents, certificat HTTPS et stockage préprovisionné. Le modèle
   `prerequisites-evidence.example.json` contient uniquement des valeurs fausses/placeholders.
2. Contrôler hôte, Git synchronisé (scripts actifs et candidat compris), contexte smoke présent,
   espace libre, cinq conteneurs DB du bon projet, Compose complet, HTTPS avec validation TLS.
   Vérifier quatre images locales épinglées, RepoDigests, labels OCI, plateforme du daemon.
   Aucun build ou pull n’est réalisé par l’orchestrateur : les images doivent être préchargées.
3. Capturer durablement les quatre images précédentes et vérifier leurs versions/digests dans
   les historiques validés. Refuser un snapshot incomplet ou impossible à reproduire.
4. **Arrêter et vérifier l’arrêt du Shell**, avec `docker kill` en secours si stop échoue.
   C’est la fermeture publique de sécurité : la PWA et les routes ERP/API publiques deviennent
   indisponibles pendant la fenêtre de maintenance. Les autres services restent présents.
5. Vérifier le volume et ses labels sans aucune écriture, absence de symlink sur les racines,
   notes-frais 100:101/0700, lecture/parcours sous 100:101 et support effectif du subpath.
   Le candidat ne provisionne pas le volume : il échoue si le répertoire est absent ou inaccessible.
6. Lancer le backup candidat : arrêt ordonné des écritures, cinq dumps et contrats/notes-frais,
   chiffrement AES-256/PBKDF2, relecture de l’archive documentaire et manifeste HMAC. Le verrou
   global reste détenu. Conserver le chemin relatif et le SHA-256 du manifeste du nouveau lot.
7. Recréer exactement **Factures API → Factures Front → PWA → ERP Shell fermé**, sans build,
   sans pull et sans démarrage des dépendances. Pour chaque composant : healthy et contrôle
   référence/image ID ; pour l’API, recherche d’erreurs Flyway dans les deux flux de logs, masqués.
8. Exécuter le helper existant `preprod_reload_erp_shell_nginx` (DNS Gateway, nginx -t, reload,
   health et proxy), healthcheck et smoke existants, puis vérifier en HTTPS les 404 `/pwa` et
   `/pwa/` et le commutateur false. Le Shell peut alors servir l’ERP, le parcours PWA reste fermé.

Le stockage documentaire reste le volume durable existant, subpath notes-frais isolé de Contrats,
RW pour Factures seulement. Il n’existe aucun bind de documents hôtes arbitraires. Aucun changement
de schéma, de politique PostgreSQL/Flyway, de chiffrement ou de permissions Contrats n’est introduit.

### Validation fonctionnelle (`validate`) et activation (`activate`)

`validate` exige une attestation privée 0600 appartenant au compte opérateur, sans symlink,
postérieure à `preparedAt`, de moins de 24 h, liée au hash du plan, à `run`, aux références,
image IDs ET container IDs observés, ainsi qu’au reçu du backup exact. Copier les champs
`observed` et `backup` de l’état privé dans une preuve basée sur
`functional-evidence.example.json`. Le modèle fourni n’est jamais une preuve valide.
Tous les contrôles fixes du plan sont obligatoires : HTTPS, cookie Secure, UID/GID, restauration,
isolation de session, navigateur, Android et iOS. Une preuve d’un autre run, périmée, partielle
ou liée à d’autres images/backup est refusée et entraîne la fermeture de sécurité.

Les contrôles physiques sont attestés par un relecteur identifié ; le programme ne prétend
pas automatiser ni certifier la véracité de ces essais. Un canal HTTPS restreint doit être
prévu pour tester le parcours complet avant ouverture publique, avec les mêmes règles de
session et d’isolation. Ce canal et l’exercice de restauration réel restent à organiser sur
une infrastructure autorisée ; ils n’ont pas été testés ici.

`validate` relit également les conteneurs et exécute de nouveau les contrôles locaux runtime.
Il n’ouvre aucune route. `activate` est une commande séparée : revalidation de l’état/proof,
Git/configuration, HTTPS, stockage, images et healthy, puis seulement recréation du Shell avec
`compose.activation.yml`. Contrôles Nginx/proxy, APIs, routes HTTPS et commutateur true après
ouverture ; en cas d’échec le Shell est arrêté automatiquement. Les autres conteneurs doivent
encore correspondre aux IDs validés avant de publier le succès. Les historiques par composant
sont uniquement enrichis après tous ces contrôles, puis un reçu global est ajouté en JSONL.

Le CLI du validateur autorise le rendu du mode ouvert pour revue, mais refuse sa commande
Compose `up` directe. Seul le moteur validé utilise l’activation dans son chemin normal.
Un administrateur Docker peut toujours contourner des scripts : restreindre les droits
opérationnels et ne jamais activer les fichiers enabled manuellement.

### Rollback coordonné (`rollback`)

Prendre le même verrou, fermer le Shell, vérifier les quatre anciennes images du snapshot et
leur plateforme. Restaurer API, Front, PWA dans cet ordre, avec contrôle healthy/image à chaque
étape. Une erreur est enregistrée ; les autres composants non publics sont tentés pour limiter
le lot résiduel. Ne jamais recréer/démarrer un point d’entrée public après rollback partiel.

Si les trois premiers composants sont conformes, **recréer le Shell ancien sans le démarrer**,
avec `up --no-start --no-deps --no-build --force-recreate --pull never`, et vérifier son image et
son arrêt. Cela évite toute ouverture transitoire par un ancien Shell qui ne connaîtrait pas le
snippet de fermeture. Le rollback complet restaure donc les quatre images mais laisse l’ERP
public arrêté ; son healthcheck HTTP n’est volontairement pas déclaré validé.

États : `rolled-back` si les quatre images sont restaurées, sinon `rollback-failed` avec la liste
exacte des composants restaurés. Le même rollback peut être réessayé depuis cet état ou depuis
un état `rolling-back` interrompu. Le snapshot initial n’est jamais remplacé par le snapshot
d’un rollback partiel. Les justificatifs et bases restent conservés ; aucun restore automatique.

Avant toute remise en écriture de l’ERP ancien, faire appliquer/revoir la protection edge readonly
Notes de frais du modèle fourni, tester les refus des écritures et les routes ERP/API. Un vieux
code pourrait sinon écraser les métadonnées ndf:. La réouverture d’un ancien lot n’est pas une
action automatique de cet orchestrateur. Un restore décidé séparément doit associer les CINQ
bases et les deux racines du même lot HMAC, six backends arrêtés. Le script candidat de restore
utilise désormais le même adaptateur de configuration ; aucune restauration réelle testée ici.

### Règles exactes du validateur candidat

- Références des quatre composants strictement égales à celles de `release-plan.json`, dépôt
  GHCR attendu et SHA-256 complet ; versions/labels/plateformes et liste des contrôles validés.
- Seul montage ajouté à Factures : volume documents-preprod RW, nocopy, subpath notes-frais,
  destination `/app/justificatifs`. Quatre paramètres documentaires aux valeurs revues ; aucun autre.
- Seuls binds : deux fichiers réguliers canoniques 0644 du répertoire candidat, propriétaires
  attendus et répertoires non modifiables par groupe/autres (répertoire temporaire sticky admis
  pour fixtures). Aucun symlink. Destinations exactes Nginx/commutateur, read-only et sans création
  automatique du chemin hôte. Mode fermé par défaut ; contenu du commutateur et fermeture vérifiés.
- Dépendances Shell healthy obligatoires vers Factures API, Factures Front, PWA, sans supprimer
  les dépendances existantes. Une dépendance ne remplace jamais le pilotage explicite du moteur.
- Après retrait des seules différences autorisées, égalité structurelle complète avec le rendu actif,
  puis validation active complète : services, réseaux, volumes, ports loopback, secrets privés,
  DB/Flyway, IA, cookies, CORS et isolation. Tout montage, service ou option supplémentaire est refusé.
- Les variables héritées PWA_RELEASE, chemin candidat et COMPOSE ne peuvent pas remplacer le plan.
  Les commandes CLI Compose supplémentaires et overrides `-f` arbitraires sont refusés.

### Commandes futures (documentation seulement, non exécutées)

Après revue, promotion Git distincte et autorisation sur la VM seulement, depuis la racine DevOps :

```bash
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh prepare \
  --execute-on-approved-host --evidence /chemin/prive/prerequisites.json
# Essais réels sur accès restreint et restauration isolée du backup produit ; preuve 0600.
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh validate \
  --execute-on-approved-host --evidence /chemin/prive/functional.json
# Décision explicite distincte :
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh activate \
  --execute-on-approved-host
# Si nécessaire, conserve les DB et documents, ferme le public :
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh rollback \
  --execute-on-approved-host
```

Le planHash est le SHA-256 du JSON du plan sérialisé par Python avec `sort_keys=True`
(voir fonction `fingerprint`). Ne pas ajouter de preuve réelle, backup ou dotenv au dépôt.
Utiliser le même plan et les mêmes sources pour toutes les transitions et conserver l’état privé.

### Tests exécutés pour cette correction et limites

- `test-orchestrator.py` : 16 tests, backend simulé ; verrou interprocessus et flock actif,
  héritage backup, ordre exact, échec aux étapes, preuve liée aux images/backup, fermeture,
  dérive runtime, rollback partiel/complet et reprise après interruption, secrets absents des traces.
- `test-compose-validator.py` : 7 tests, vrais rendus Compose avec dotenv fictif ; modes fermé/ouvert,
  binds autorisés/refusés, symlinks/permissions, digests, dépendances, HTTPS/cookies/CORS et gardes DB.
- `test-storage-runtime.py` : 4 tests, Docker/hostname/stat simulés, uniquement dossiers temporaires ;
  absence, mauvais propriétaire/mode, symlink, accès refusé et absence d’écriture des probes.
- `test-runtime-backend.py` : 5 tests, Docker simulé ; OCI/digests/plateforme, commandes sans build/pull,
  Shell rollback sans démarrage, arrêt/kill, image runtime et erreurs Flyway masquées.
- `test-candidate.py` : 9 tests d’archives/chiffrement/HMAC/Compose/fermeture et patch historique isolé.
- Suites actives : config 36, garde-fous 10, Nginx 5, build-image 14 ; toutes conformes.
  Historique : huit contrôles conformes. Total : **106 tests Python** plus historique.
- Quatre `nginx -t` conformes sur l’image locale exacte (réseau coupé), lot OCI/RepoDigests locaux,
  rendus Compose, syntaxe Bash de tous les scripts actifs/candidats et `git diff --check` conformes.

Restent non validés : VM réelle, droits du volume réel et capacité/restauration PostgreSQL,
certificat public et session HTTPS, parc mobiles réel, backend fonctionnel, tests de panne Docker
et comportement du déploiement/rollback sur la cible. Le backup doit tenir dans le timeout runtime
(15 min par commande) ou faire l’objet d’une adaptation revue pour la volumétrie réelle.
La fermeture de secours impose une indisponibilité ERP. Un daemon totalement indisponible peut
empêcher stop/kill : l’événement CLOSE_FAILED exige une fermeture réseau/edge par l’exploitation.
SIGKILL, coupure machine et panne après la fin d’activate ne sont pas supervisés par ce processus :
prévoir supervision externe et reprise sur état durable. Aucun résultat de mock ne vaut validation
opérationnelle de ces cas. Les preuves opérateur sont des attestations, pas une signature distante.


## Revue finale avant commit — 20 octobre 2026

Décision : **NO-GO POUR COMMIT ORCHESTRATEUR PWA PREPROD**.
Cette décision remplace le GO pour revue précédent. Le passage des suites existantes ne démontre
pas les garanties supplémentaires vérifiées ici. Revue locale seulement : aucun accès VM,
aucun déploiement, build, commit, push, changement PostgreSQL/Flyway ou manifeste actif.
Le seul fichier amendé pendant cette revue est ce README ; les corrections fonctionnelles
ci-dessous ne sont pas encore implémentées. FILES.txt a été contrôlé sans modification.

### Anomalies et corrections requises

1. **Exclusion incomplète des commandes mutantes** : le flock du moteur exclut bien un autre
   détenteur du même inode et les releases/backups/restores classiques qui le prennent.
   Cependant `scripts/stop-all.sh:25`, utilisé par `wavy stop preprod`, atteint Compose stop
   sans consulter le verrou. Reproduit dans une copie temporaire avec le verrou détenu et
   Docker/Compose simulés. Le CLI candidat `scripts/preprod_config.py:144` autorise aussi
   un `up` fermé sans verrou, état de lot ni garde hôte ; l'appel exec a été intercepté,
   aucun up réel effectué. Il faut imposer le même contrat de verrou/état à tous les chemins
   mutants supportés, ou rendre ces chemins inaccessibles pour PREPROD.
2. **Pas de réservation entre phases** : après `prepare` ou `validate`, le verrou est libéré.
   Acquisition par un autre processus confirmée en état validated. Les scripts classiques
   ne consultent pas `deployments/pwa-release/state.json` : ils peuvent intervenir pendant
   les validations humaines et utiliser notamment le backup actif Contrats seul. Le contrôle
   des IDs empêche normalement une activation ultérieure incohérente, mais il n'empêche pas
   ces mutations ni un backup DB/documents incomplet pour Notes de frais. Prévoir un état de
   réservation contrôlé par toutes les commandes ou un propriétaire de verrou durable pendant
   la session de release ; conserver les règles d'héritage pour le backup.
3. **Fraîcheur non revérifiée au point d'ouverture** : `Engine.activate` contrôle la preuve
   avant preflight/images/stockage/healthy, puis ouvre sans nouveau contrôle d'âge.
   Reproduit par horloge simulée : preuve à 23 h 59 au début, précontrôles de deux minutes,
   ouverture acceptée à 24 h 01. Revalider la preuve immédiatement avant l'effet d'ouverture,
   borner la fenêtre et tester cette frontière, y compris le temps de recréation du Shell.
4. **Fermeture effective non garantie en cas de panne Docker** : après ouverture, une erreur de
   contrôles suivie d'un échec stop/kill laisse le backend simulé ouvert ; le moteur consigne
   CLOSE_FAILED et failed, sans barrière externe automatique. Aucun contournement ni fuite réelle
   de justificatif n'a été exécuté. Il faut distinguer « fermeture demandée » de « fermeture
   prouvée » et disposer d'une fermeture indépendante, vérifiée, si la garantie de fermeture
   lors de chaque échec est exigée. Les échecs avant prise du verrou ou refus d'hôte ne doivent
   pas fermer le service d'une autre opération ; cette distinction doit rester explicite.

### Disponibilité ERP et justificatifs

L'arrêt du Shell coupe toutes les routes publiques ERP et API, pas seulement la PWA. Il dure
pendant les étapes de préparation et après un rollback complet ; ce dernier laisse expressément
le Shell ancien recréé et arrêté. Un arrêt de secours peut couper des requêtes en cours.
Le backup quiesce également les six backends : garder le Shell démarré ne supprimerait donc
pas toutes les interruptions ERP.

Préserver les autres routes ERP nécessite une barrière distincte sur un proxy/edge encore
opérationnel, avec fermeture ciblée /pwa et des accès Notes de frais concernés, et contrôle du
commutateur, sans exposer les routes API d'un lot partiel. Cette stratégie n'est pas implémentée
par le candidat. Pour le rollback, bloquer aussi les écritures Notes de frais avant toute remise
en service de vieux composants. Une politique explicite de maintenance reste nécessaire pour
la sauvegarde cohérente DB/documents ; ne pas annoncer une disponibilité ERP continue.

Aucun alias/root Nginx vers le volume de justificatifs n'a été trouvé ; le montage reste limité
à Factures API et le rendu Compose n'ajoute aucun port public documentaire. Les contrôleurs
passent par le contexte serveur et utilisent no-store. Ces constats statiques ne démontrent pas
le refus des accès non autorisés en environnement réel. Une PWA déjà installée peut garder ses
bundles : fermer /pwa seul ne révoque ni la session ni ses appels API. Les tests de droits,
isolation et cache privé restent requis avant toute activation réelle.

### Points conformes et vérifications exécutées

- README.md et FILES.txt lus et confrontés aux fichiers : aucun candidat ou changement DevOps
  hors inventaire, aucune entrée DevOps manquante. Aucun artefact .pem/.key/.dump/.enc ou dotenv
  ajouté au candidat ; aucune signature de clé privée, token GitHub ou clé AWS trouvée dans les
  fichiers modifiés/non suivis contrôlés. Ce contrôle statique n'est pas une preuve exhaustive
  d'absence de secrets. Aucun secret n'a été imprimé pendant la revue.
- Manifestes actifs PREPROD/RECETTE, scripts actifs, wavy, versions/digests/historiques : aucun
  diff indexé ou non indexé. Aucun fichier applicatif modifié. Fichiers préexistants conservés.
- 106 tests Python réussis : orchestrateur 16, backend 5, validateur Compose 7, candidat 9,
  stockage 4, configuration active 36, garde-fous 10, Nginx actif 5, build-image 14.
- Huit contrôles d'historique réussis. Quatre nginx -t réussis sur l'image locale exacte,
  sans réseau ni serveur, lot OCI/RepoDigests locaux conforme, rendus Compose avec fixtures,
  bash -n sur wavy et tous les scripts actifs/candidats, git diff --check conformes.
- Cinq constats ciblés supplémentaires confirmés avec fichiers temporaires, backend/horloge
  simulés ou exec intercepté : stop classique sans verrou, CLI Compose candidat sans verrou,
  libération entre phases, CLOSE_FAILED après ouverture, expiration avant ouverture.
  Ces reproductions ponctuelles ne sont pas encore des tests de non-régression persistants ;
  les corrections devront les intégrer aux suites avec les résultats de sécurité attendus.
- Le chemin rollback ne lance aucun pg_restore, Flyway ou script restore. Les tests couvrent
  le rollback complet/partiel, le snapshot conservé et la reprise après interruption. Les images
  sont contrôlées, le Shell final reste arrêté et le volume documentaire est conservé.
- Le chemin normal refuse une preuve absente, incomplète, périmée au début, étrangère au run,
  ou liée à d'autres IDs/backup. Le CLI refuse up en mode ouvert. Les attestations restent
  déclaratives et modifiables par leur propriétaire ; ce n'est pas une certification indépendante.

Restent non exécutés : tout contrôle sur VM, restauration PostgreSQL réelle, droits et persistance
réels des documents, HTTPS/session/clients mobiles réels, fermeture edge et reprise ERP en panne.
Avant commit : corriger les anomalies ci-dessus, ajouter les non-régressions, arrêter la stratégie
de disponibilité/fermeture et réexécuter la revue. Aucun GO de commit ou de déploiement à ce stade.


## Étape intermédiaire du 21 octobre 2026 (historique)

La demande reçue s'interrompt au point 3 (« Recontrôler la validité temporelle »).
La suite, notamment les exigences de fermeture indépendante du point 4, a été demandée.
Le NO-GO reste applicable ; aucun correctif global n'est déclaré terminé.

README.md et FILES.txt ont été relus ; les modifications préexistantes sont conservées.
L'audit des commandes classiques, du CLI Compose et de l'état entre phases est commencé.
La conception de la réservation et de l'abandon sécurisé doit être cohérente avec la fermeture
indépendante attendue : aucun mécanisme d'abandon reposant uniquement sur stop/kill n'est annoncé.

Correction ciblée déjà apportée au moteur : relecture de la fraîcheur après les précontrôles
et juste avant la demande d'ouverture, après la recréation, puis avant l'enregistrement du succès.
Deux non-régressions persistantes avec horloge simulée couvrent une preuve à 23 h 59 devenant
périmée après deux minutes de précontrôles (aucune ouverture), et son expiration pendant la
commande d'ouverture (fermeture tentée, aucun succès enregistré). Les 18 tests d'orchestrateur
passent, ainsi que git diff --check. Avant cette modification, les suites de référence
orchestrateur 16, validateur 7 et backend 5 ont aussi passé.

Cette correction ne fournit pas encore de barrière indépendante empêchant toute ouverture
transitoire si la commande dépasse la validité de la preuve ; elle ne résout pas CLOSE_FAILED.
Les points verrou/réservation/abandon et fermeture indépendante restent à implémenter après
réception de la suite des exigences. Aucun manifeste actif, environnement, base, dépôt applicatif,
commit ou push n'a été modifié pendant cette étape locale.


## Correctifs des quatre anomalies — 21 octobre 2026

Décision courante : **GO POUR REVUE CORRECTIFS ORCHESTRATEUR PWA**.
Ce GO porte sur le code et les tests locaux ci-dessous, pas sur un commit ni sur un déploiement.
Les sections précédentes conservent l'historique des revues et du message tronqué ; les règles
ci-dessous les remplacent pour l'exploitation future. Aucune commande runtime n'a été exécutée
sur une VM. Aucun manifeste actif, base, migration, dépôt applicatif, secret, commit ou push modifié.
Les scripts classiques du dépôt ont été adaptés localement : ces changements doivent être revus
et promus ensemble avec le candidat. La préparation ne les installe sur aucun environnement.

### 1. Protection commune de tous les chemins supportés

`scripts/preprod_operation.py` tient le flock exclusif `deployments/preprod.lock` pendant toute
la commande enveloppée, et vérifie la réservation privée avant de lancer le moindre enfant.
Les descripteurs sont hérités/dupliqués sur le même inode : un backup enfant ne rouvre pas un
verrou concurrent avec son parent. Une commande classique n'accepte jamais de propriétaire de
réservation par environnement ; seul l'adaptateur candidat vérifie explicitement son run et son
FD hérité. Ni un marqueur de wrapper hérité ni un FD partagé n'exemptent du contrôle de réservation.

Audit et protections :

- deploy/rollback classiques et redémarrages ciblés via wavy : release-preprod.sh enveloppé ;
- arrêt via wavy stop et stop-all.sh : enveloppe globale avant Docker, maintenue pendant la confirmation DB ;
- initialize-preprod.sh, validate-preprod-runtime.sh, backup-preprod.sh et restore-preprod.sh : même contrat ;
- CLI Compose classique : toute commande potentiellement mutante prend le contrat ; les commandes
  d'inspection config/ps/logs/images/version restent possibles. Le backup hérité reste sous le verrou parent ;
- CLI Compose candidat : uniquement config --quiet ou config --format json, modes fermé/ouvert pour revue.
  Aucun up indépendant n'est autorisé, même en mode fermé. Les mutations sont internes au moteur réservé ;
- wavy start/restart all/build PREPROD restent refusés comme auparavant ; le provisionnement initial est séparé ;
- backup-db.sh et restore-db.sh génériques refusent PREPROD avant Docker : seul le lot chiffré avec documents
  est supporté. Les commandes LOCAL/RECETTE conservent leur comportement.

Les anciennes sauvegardes classiques savent aussi archiver notes-frais si présent et le validateur
accepte les deux racines. Dès qu'un état PWA existe, un dossier notes-frais manquant fait refuser le
backup au lieu de publier un lot incomplet. La restauration explicite classique restaure les cinq bases
et les deux racines ; une archive Contrats seule crée une racine notes-frais vide. Aucun restore n'est
appelé par le moteur. Les confirmations mentionnent les deux racines. Le patch historique n'est pas
appliqué : son ancienne version ne représente plus les scripts actuels.

Le périmètre est celui des commandes supportées du dépôt, sur une copie canonique d'exploitation.
Un administrateur Docker/root ou un utilisateur capable de modifier ces scripts peut toujours employer
Docker directement ou une autre copie du dépôt ; le flock n'est pas une frontière contre cet administrateur.
Restreindre les droits opérationnels et interdire les chemins parallèles lors de la promotion.

### 2. Réservation durable, reprise et abandon

`deployments/preprod-reservation.json` contient run, hash du plan et date UTC, en 0600, écriture
atomique et fsync du fichier/répertoire. Ce fichier n'est jamais supprimé à la fin d'un processus,
au redémarrage, à la disponibilité du flock ou à l'expiration d'une preuve. L'état complémentaire
reste dans deployments/pwa-release (0700, fichiers 0600). Ces chemins privés sont ignorés par Git.

La réservation est créée sous le verrou AVANT la préparation, et reste présente entre prepare,
validate, activate, après succès active et après échec. Toute opération classique incompatible est
refusée ; les autres invocations candidates exigent le run exact. Une tentative concurrente ou avec
un autre run est refusée avant de fermer le service de l'opération propriétaire.
L'activation conserve volontairement la réservation pour empêcher un remplacement isolé d'une image
pendant que le lot PWA est ouvert. Aucun transfert automatique vers les scripts classiques n'existe.

Reprise autorisée, toujours avec le même plan/sources/configuration et le même run :

- `resume --run-id <run>` reprend preparing/failed, vérifie ou renouvelle les prérequis, ferme et prouve
  l'edge, conserve le snapshot initial puis refait backup et les quatre étapes. Une nouvelle preuve
  fonctionnelle liée aux nouveaux IDs et au nouveau backup est obligatoire ; aucune ancienne validation conservée ;
- `rollback --run-id <run>` restaure les quatre images du snapshot, peut reprendre rolling-back/rollback-failed,
  et conserve les DB/documents ; le Shell ancien est recréé sans démarrage. Les écritures Notes de frais sont
  bloquées à l'edge pour éviter qu'un ancien code écrase les métadonnées ndf: ;
- `abandon --run-id <run>` ferme et vérifie l'edge en mode readonly Notes de frais. S'il y a eu une tentative
  de mutation d'image, même avant un premier healthcheck réussi, le rollback complet est obligatoire.
  Sinon l'abandon d'une préparation refusée avant mutation est permis. L'état est archivé par run,
  l'abandon est journalisé, puis seulement la réservation est supprimée avec fsync ;
- si la fermeture ne peut pas être confirmée, aucune réservation n'est libérée et aucune activation
  supplémentaire n'est acceptée. Réparer/vérifier l'edge, puis reprendre avec le même run. Ne jamais
  effacer state.json ou la réservation pour « débloquer » une installation.

Le marqueur mutationStarted est sauvegardé AVANT le premier appel de déploiement, pas après le
premier healthy : il couvre le cas d'une première image changée avec healthcheck échoué.
Les états et journaux privés restent conservés, y compris après abandon. Le journal ne contient
que date UTC, code d'action, résultat et run ; jamais preuves, sorties enfants, cookies ou dotenv.

Exemples futurs sur hôte approuvé seulement, non exécutés ici :

```bash
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh prepare \
  --execute-on-approved-host --evidence /chemin/prive/prerequisites.json
# Lire run et les reçus dans l'état privé ; réaliser les contrôles physiques via accès restreint.
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh validate \
  --execute-on-approved-host --run-id <run> --evidence /chemin/prive/functional.json
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh activate \
  --execute-on-approved-host --run-id <run>
# En cas d'interruption :
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh resume \
  --execute-on-approved-host --run-id <run> --evidence /chemin/prive/prerequisites-renouveles.json
# Ou retour arrière puis abandon explicitement décidés :
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh rollback \
  --execute-on-approved-host --run-id <run>
bash preparation/pwa-notes-frais/scripts/release-pwa-preprod.sh abandon \
  --execute-on-approved-host --run-id <run>
```

Après rollback/abandon, l'ERP Shell ancien reste arrêté. Sa remise en service doit être une
opération classique explicitement autorisée et verrouillée, avec référence historique épinglée
et contrôles Nginx/health/smoke, pendant que la barrière edge maintient PWA fermée et Notes de
frais en lecture seule. Ce n'est pas une restauration automatique des données.

### 3. Preuves vérifiées jusqu'au véritable point d'ouverture

Les contrôles d'âge/run/images/backup restent obligatoires. Ils sont réexécutés après les
précontrôles et après la recréation du Shell, avant et après les contrôles d'ouverture et avant
le succès. Le Shell peut monter les fichiers enabled pendant que la barrière HTTPS est fermée :
ce montage n'ouvre donc plus l'accès public.

L'ouverture réseau intervient en dernier, par une autorisation native dont l'échéance est
exactement checkedAt de la preuve + 24 h. Le contrôleur revérifie la date au moment d'écrire
l'autorisation, puis à CHAQUE requête ; il ne met jamais la décision en cache. Une expiration
pendant la recréation ou pendant l'écriture ne crée pas de fenêtre de requêtes autorisées périmées.
Un recul d'horloge avant openedAt ferme également l'accès. Une horloge UTC correctement synchronisée
reste un prérequis d'exploitation.

Choix conservateur : l'autorisation PWA expire au plus tard avec la preuve, même après succès active.
L'expiration ferme les nouvelles requêtes, mais ne libère jamais la réservation. Il n'existe pas
encore de renouvellement automatique ; planifier la durée de l'essai PREPROD et une décision explicite
pour une activation ultérieure. Ne pas présenter ce candidat comme une ouverture PWA permanente.

### 4. Fermeture HTTPS indépendante de Docker et d'ERP Shell

`edge-pwa-gate.conf` est inclus dans la terminaison HTTPS native de l'hôte.
`edge_gate.py` fournit uniquement une autorisation HTTP en lecture sur 127.0.0.1:24444, hors Docker.
`wavy-pwa-gate.service.template` prépare son supervision systemd. Aucun endpoint HTTP ne peut ouvrir
la barrière ; seuls le moteur réservé et les fichiers locaux privés la modifient.
Les chemins/compte de l'unité doivent être revus/remplacés littéralement avant installation ; aucun
secret ni certificat n'est fourni. Le modèle edge exige ERP loopback 24443, désormais vérifié par
le validateur candidat. L'unité est une préparation, aucun service système n'a été installé ici.

À promouvoir/revoir avant toute future préparation : include edge, unité native, compte identique à
celui de l'orchestrateur, accès au dossier privé, DNS/certificat HTTPS et absence d'autre ingress
public contournant cet edge. Ne pas exposer le loopback ERP ou un tunnel HTTP aux utilisateurs.
Le test public de fermeture exige le marqueur X-Wavy-PWA-Gate: closed ; un simple 404 applicatif
ne suffit pas à faire croire que la barrière est installée.

Routes réseau couvertes : /pwa et tout /pwa/ (bundles, assets, ngsw-worker.js, ngsw.json, icônes,
manifestes), /pwa-integration.json et espace d'endpoints dédiés /api/pwa et /api/pwa/.
Les localisations internes ne sont pas accessibles directement. Les APIs communes /api/auth,
/api/tiers et les modules ERP ne sont pas bloqués par la fermeture PWA. Les données Notes de frais
restent servies par les APIs communes autorisées existantes : fermer PWA ne remplace jamais leurs droits.

Les lectures Notes de frais restent possibles à travers l'edge. Les écritures ont une politique
distincte : mode normal une fois la cohorte entièrement préparée ; mode readonly explicite pendant
rollback/abandon, ou si le contrôleur/son état est indisponible. Aucun POST d'une autre API ERP n'est
bloqué par cette règle. L'état initial inconnu bloque ces écritures par prudence ; la préparation
réussie reprend explicitement leur mode normal sans ouvrir la PWA.

État absent/corrompu/non privé, décision fermée, échéance dépassée ou service d'autorisation arrêté :
les routes PWA répondent 404 avant d'atteindre le Shell. Les accès protégés et leurs sous-requêtes
ne journalisent ni URI/query, ni cookies/Authorization ; le service natif n'a pas de log de requêtes.
`DockerBackend.close` écrit closed puis vérifie en HTTPS neuf chemins, sans aucune commande Docker.
La panne de stop/kill du Shell ne peut donc plus empêcher cette fermeture ciblée. L'arrêt du Shell
n'est plus le mécanisme de fermeture de secours lors d'une erreur de release.

Si une fermeture ne peut pas être confirmée : latch closureBlocked persistant, phase failed,
réservation conservée, alerte explicite « FERMETURE EDGE NON CONFIRMÉE ; ACTIVATION INTERDITE ».
Le moteur ne peut pas rouvrir sur ce latch ; une reprise explicite doit d'abord prouver la fermeture.
Si l'edge natif, le réseau, le disque ou l'hôte entier sont en panne, la confirmation peut rester
impossible : alerter l'exploitation et appliquer la fermeture réseau prévue. Le code ne prétend
pas contrôler un hôte totalement indisponible. Les limites SIGKILL/coupure restent à superviser ;
l'autorisation bornée ne constitue pas une détection immédiate de la mort de l'orchestrateur.

Les contenus déjà mis en cache peuvent encore être affichés/exécutés sur un appareil sans nouvelle
requête HTTP. Il n'est pas possible de les effacer depuis cet edge, ni de distinguer un ancien client
PWA d'un client ERP appelant la même API avec la même session. Les contrôles serveur d'identité,
tenant/société/utilisateur et no-store sur les justificatifs restent indispensables. Une réponse
ou un téléchargement déjà autorisé et en cours ne peut pas être révoqué rétroactivement par ce gate.
Aucun justificatif n'est monté ou servi statiquement par l'edge.

La fermeture ciblée permet de conserver les routes ERP tant que les services correspondants
fonctionnent. Elle ne garantit aucune disponibilité ERP continue : le backup arrête toujours les
six backends, et les remplacements/rollback de composants peuvent encore interrompre des requêtes.
La fenêtre de maintenance et le canal HTTPS de validation fonctionnelle restreint restent à préparer.

### Non-régressions et validation locale

Les cinq reproductions sont devenues des tests persistants :

- stop-all.sh et la matrice des commandes classiques sous verrou détenu : aucune mutation Docker ;
- CLI Compose candidat up fermé : refus avant rendu/exec ;
- fin de processus et réservation persistante : commandes classiques refusées, bon propriétaire requis,
  reprise/abandon explicites et aucune suppression sur fin de processus ou expiration ;
- preuve à 23 h 59 et précontrôles de deux minutes, expiration pendant ouverture : pas de public ouvert
  avec une preuve périmée, contrôle supplémentaire à chaque requête native ;
- stop/kill indisponibles : fermeture native ne lance pas Docker. Si le probe edge échoue, latch et alerte,
  réservation conservée et activation refusée ; les fixtures Nginx vérifient aussi le contrôleur arrêté.

Suites complètes réexécutées : orchestrateur 23, backend 5, gardes d'opérations 4, validateur Compose 7,
candidat 9, stockage/probes 5, contrôleur edge 5, Nginx edge HTTP 4 ; config active 36, garde-fous actifs 10,
Nginx actif 5, build-image 14. Total prévu de cette version : **127 tests Python**, plus les huit contrôles
historique et quatre nginx -t. Les résultats finaux et contrôles de syntaxe/inventaire sont consignés
après la dernière exécution ci-dessous ; aucun test sur VM ou sur base réelle n'est annoncé validé.

Les tests Nginx HTTP utilisent l'image locale exacte, sans pull/build, ports publiés, réseau externe
ou volume applicatif ; seuls des upstreams factices démarrent dans le conteneur jetable.
Les autres tests utilisent mocks, fichiers temporaires et serveur HTTP loopback éphémère.
Le test database-from-zero est explicitement désactivé dans le dépôt et n'est pas un exercice de
restauration réelle ; aucune commande destructrice de base n'est exécutée pendant ces validations.


## Provisionnement Notes de frais corrigé — 24 octobre 2026

La première version du provisionnement avait deux défauts confirmés : course entre création et
chown par chemin, et appel direct possible avec un état preparing et un FD sans précontrôles.
Cette section remplace les garanties de cette première version. Le correctif reste candidat,
PWA désactivée par défaut ; aucun manifeste actif ni environnement réel n'est modifié.

Ordre prepare/resume : garde hôte sous verrou global, réservation persistante créée/vérifiée,
attestation des prérequis, précontrôles HTTPS/configuration/disque, images vérifiées et snapshot
initial conservé, fermeture HTTPS confirmée, autorisation à usage unique, provisionnement,
`storage` RO avec montage subpath, sauvegarde complète, puis étapes applicatives. Le booléen
interne de l'invocation est armé uniquement après les précontrôles ; un état preparing sur disque
ne suffit jamais à entrer dans cette séquence. L'attestation historique `storage-provisioned`
désigne l'infrastructure documentaire existante et l'autorisation du provisionnement, pas
l'existence préalable obligatoire de notes-frais.

### Capacité à usage unique

Après le retour réussi de la fermeture HTTPS et une nouvelle vérification de la fraîcheur des
prérequis, l'orchestrateur inscrit une attestation dans l'état privé (run, précontrôles, snapshot,
fermeture, tentative aléatoire et date). `storage_authorization.py` émet alors un reçu privé 0600
lié à l'action exacte provision-storage, au run, au plan, au contenu et à l'identité inode/mtime
de l'état et de la réservation. Il expire après au plus 60 secondes, sans dépasser l'échéance des prérequis (24 h) ni celle
des précontrôles courants. Un jeton aléatoire de 256 bits est
transmis seulement par pipe hérité ; seul son hash figure dans le reçu. Aucun jeton n'est placé
dans argv, un fichier ou un journal. La variable d'environnement ne contient que le numéro du FD.

L'appel direct de runtime-action.sh exige ce jeton, le FD du verrou global, la réservation privée,
les empreintes courantes et un état edge fermé du même run sans latch closureBlocked. La réception
du jeton consomme le pipe et remplace durablement le reçu AVANT Docker ; il n'est jamais réarmé
en cas d'échec. Un reçu expiré, un état/réservation modifié, un plan différent, un autre run, une
autre action ou une barrière non confirmée provoquent un refus. Le finally de l'orchestrateur
invalide aussi tout reçu non consommé. La reprise réexécute les précontrôles et la fermeture,
puis crée une nouvelle tentative et un nouveau jeton. Un FD verrouillé n'est pas une capacité.
Le CLI Compose candidat reste limité à config ; il ne peut pas lancer le provisionnement.

L'échéance d'origine est transmise au helper qui la revérifie avant création, changements de
métadonnées, publication et contrôle final. Docker ne prolonge pas la validité de l'autorisation.
Un arrêt brutal peut laisser le reçu et l'état privés ; sans le pipe éphémère ils ne permettent
pas un nouvel appel. Une commande enfant déjà autorisée peut terminer dans sa fenêtre de 60 s ;
ce mécanisme ne prétend pas détecter immédiatement la mort du parent.

### Inodes et stockage

Les labels Compose projet wavy-preprod et volume documents-preprod, ainsi que le nom exact
wavy-preprod_documents-preprod, sont contrôlés avant montage. Le volume et sa racine contrats
doivent déjà exister. Le helper Python ouvre chaque composant de chemin avec O_DIRECTORY et
O_NOFOLLOW ; la racine doit appartenir au compte du helper et ne pas être inscriptible par le
groupe ou les autres utilisateurs. Contrats est ouvert en lecture, jamais modifié.

Si notes-frais existe, son FD doit déjà être 100:101:0700 : aucun fchown/fchmod de réparation.
Sinon le helper crée un nom aléatoire `.notes-frais.provision-<uuid>`, l'ouvre sans suivre de
liens et contrôle son identité, son propriétaire initial, son mode et son absence de contenu.
Les changements utilisent fchmod/fchown sur ce FD, jamais sur un chemin résolu à nouveau.
Après fsync et revérification d'identité, renameat2(RENAME_NOREPLACE) publie notes-frais sans
écraser une entrée concurrente, même vide. Les identités du FD final, de Contrats et de la
racine sont encore vérifiées. Une substitution après ouverture ne peut pas détourner le chown
vers le remplacement et fait refuser le succès. Aucun lien symbolique n'est suivi.

Le helper s'exécute sans réseau, rootfs RO, avec CHOWN et DAC_OVERRIDE uniquement, dans l'image
supplémentaire épinglée :
`python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d`.
Elle doit être approvisionnée explicitement avant préparation, comme l'image PostgreSQL utilitaire
existante ; l'adaptateur n'effectue aucun pull automatique. Le script est monté RO. Linux avec
renameat2 est requis ; son absence fait échouer le provisionnement. `storage` demeure RO et
éprouve réellement le montage volume-subpath=notes-frais sous l'utilisateur 100:101 avant backup.

### Interruption et limites de confiance

Une interruption avant publication peut laisser un répertoire provisoire, vide en 0700, appartenant
à root ou à 100:101 selon le point atteint. Après publication, notes-frais est déjà conforme ; un
échec ultérieur peut le laisser en place. Aucun répertoire ni document n'est supprimé ou réparé
automatiquement. Les traces provisoires sont conservées et une reprise utilise un nouveau nom,
sans les suivre ni les recycler. Une inspection explicite pourra décider de leur traitement ;
ne jamais supprimer des documents pour débloquer une reprise. La réservation reste persistante.

Le volume parent et les sources/états privés sont de confiance, administrés par l'identité
opérationnelle. Le compte qui peut modifier ces scripts ou forger les états privés, comme un
administrateur root/Docker complet, peut contourner les contrôles applicatifs. Les descripteurs
protègent contre les substitutions pendant les opérations ; ils n'isolent pas un administrateur
capable de modifier les inodes, les permissions ou les montages arbitrairement, notamment avant
l'ouverture initiale d'un répertoire privé. Restreindre les droits et les chemins d'exploitation.
La preuve est une autorisation de l'orchestrateur, pas une attestation indépendante de l'hôte.

### Non-régressions locales

Les fragments historiques reproduisent le succès indésirable du remplacement et de l'appel
direct sans précontrôles. Les régressions du correctif imposent le refus des mêmes scénarios,
avec substitutions par répertoire/lien au point de fchown, destination concurrente, permissions
incorrectes, interruption, préservation Contrats, idempotence et archive candidate. Les tests
couvrent aussi FD verrouillé sans capacité, run/plan/état/réservation invalidés, expiration,
autre action, mauvais jeton, réutilisation et révocation/reprise de l'orchestrateur.

`WAVY_TEST_LOCAL_DOCKER=1 python3 preparation/pwa-notes-frais/test-storage-security.py` ajoute
un test Linux réel sur un volume `wavy-storage-security-test-<uuid>` jetable, supprimé en finally :
propriétaires et permissions réels, substitutions et subpath RO sous 100:101. Il utilise seulement
un contexte Unix local et les images déjà présentes. Les autres cas emploient des répertoires
privés temporaires et des fixtures ; aucun accès au volume PREPROD, aucune base ni migration.


Validation finale locale : **146 tests Python réussis**, dont 18 de sécurité stockage,
5 de vérification runtime RO et 24 d'orchestrateur ; suites candidates et DevOps existantes,
rendus Compose de fixture, huit contrôles historique, quatre nginx -t, lot OCI/RepoDigests local,
syntaxe de 26 fichiers Python et 63 fichiers Bash, git diff --check conformes. Le scanner
`detect-secrets` 1.5.0 ne relève aucun secret dans le périmètre du correctif. FILES.txt référence
les deux helpers et la nouvelle suite. Aucun commit, push, accès VM ou base ; manifestes actifs,
versions/digests/historiques et fichiers locaux préexistants préservés. Ce résultat autorise une
revue du correctif ; il ne valide pas une préparation ou un déploiement PREPROD réel.


## V3 — consommation exclusive et horloge des tests — 24 octobre 2026

La revue V2 a confirmé deux consommateurs autorisés simultanément : ils partageaient la même
description du verrou global hérité et avaient chacun une copie du jeton dans un pipe distinct.
Un remplacement atomique de l'enveloppe courante ne réservait pas sa consommation. Le résultat
V2 de 146 tests ci-dessus est historique : il ne couvrait pas ce scénario concurrent.

### Reçu terminal par capacité

`storage_authorization.claim_once` crée désormais
`deployments/pwa-release/storage-consumed-<sha256-du-jeton>.json` avec
O_CREAT|O_EXCL|O_NOFOLLOW et mode 0600. La création exclusive du nom est le point de décision :
un seul gagnant, indépendamment des descriptions de fichiers du verrou global. Le contenu minimal
(run, plan et consumed:true) est écrit, flushé, fsyncé, puis le répertoire est fsyncé AVANT la mise
à jour de l'enveloppe courante et avant tout retour autorisant Docker. Le verrou global, les
contrôles d'état/réservation/edge et les échéances V2 restent obligatoires, sans être l'unique
protection contre le rejeu.

Un fichier terminal existant, même vide, incomplet ou symbolique, provoque un refus. Aucun code
ne le supprime, ne le tronque ou ne le remplace. Si le processus est interrompu après la création
exclusive, le jeton est définitivement brûlé même si l'enveloppe storage-authorization.json affiche
encore l'autorisation initiale. Un échec de flush/fsync n'autorise aucune opération documentaire.
Après un crash électrique, la garantie d'une autorisation déjà retournée repose sur les fsync
réussis et sur un système de fichiers respectant O_EXCL et la persistance POSIX. Ce n'est pas une
preuve matérielle de résistance à une panne disque.

Avant la création exclusive, aucun succès ni opération Docker n'a été autorisé. Après interruption
à ce point, une autre copie encore valide du jeton peut gagner la consommation, toujours au plus
une fois. Après la création exclusive, toute copie et tout nouveau processus sont refusés.
Une reprise explicitement orchestrée réexécute les précontrôles et crée une nouvelle capacité :
elle peut remplacer l'enveloppe courante, mais jamais le reçu terminal de l'ancienne capacité.
Les reçus terminaux restent privés et conservés ; aucune purge automatique n'est introduite.
Les traces documentaires provisoires, la réservation et les limites administrateur de V2 restent
inchangées. Un opérateur ne doit jamais effacer un reçu terminal pour réarmer son jeton.

### Concurrence et interruptions déterministes

`test-storage-authorization-concurrency.py` est obligatoire sans option Docker. Des barrières
alignent réellement 2 puis 10 processus forkés et, pour le FD global partagé, imposent qu'ils
aient tous lu le même reçu initial avant de poursuivre. Chaque processus reçoit une copie du
même jeton dans un pipe séparé. Les cas normaux exigent exactement un gagnant, les cas refusés
zéro, toujours au plus un. La matrice couvre les FD hérités partagés et les FD ouverts
indépendamment, les reçus modifiés/expirés/autre run et le rejeu par de nouveaux processus.
Des rendez-vous explicites permettent SIGKILL avant le claim, pendant son fsync, après le claim
durable et après le retour de consommation. Aucune attente temporelle supposée ne remplace ces
rendez-vous. Les bornes de join/barrière sont uniquement des watchdogs d'échec des tests.
Les horloges logiques sont identiques dans le parent et les consommateurs pour isoler la
concurrence des recalages de l'horloge hôte.

La reproduction commune à deux consommateurs a été exécutée sur une copie temporaire V2 :
deux succès, donc échec de la nouvelle assertion. Le même scénario passe en V3 avec un seul
succès. La copie historique utilisée pour ce contrôle ne fait pas partie du dépôt.

### Analyse de mutationStarted

Le diagnostic a reproduit un refus anticipé « Preuve expirée ou sans relecteur » alors que le
test attendait l'échec healthy-factures-api. Une observation instrumentée a mesuré un recul UTC
d'environ 1,7 seconde pendant que CLOCK_MONOTONIC avançait ; l'âge calculé de la preuve devenait
négatif (-1,527181 s). La mutation n'avait donc pas commencé, conformément au refus sécurisé du
moteur. Ce n'était pas une course sur mutationStarted, ni un état partagé entre les répertoires
temporaires ; l'assertion générique ValueError confondait deux points de refus. L'origine externe
du recalage UTC n'a pas été modifiée ni investiguée sur une VM.

Les tests d'orchestrateur synchronisent maintenant leurs preuves, dates du moteur et capacités
sur une horloge logique contrôlée. Le scénario vérifie explicitement le rendez-vous healthy,
le marqueur mutationStarted déjà persisté et une exception BackendFailure portant exactement
healthy-factures-api. Un refus antérieur différent fait échouer le test. Une régression distincte
fait reculer l'horloge de deux secondes et vérifie le refus AVANT mutation. Les contrôles de
production sur les preuves futures ou expirées ne sont pas assouplis ; aucun délai n'est augmenté.


Résultats V3 : **159 tests Python validés**, dont 12 de consommation concurrente et durable,
18 de sécurité stockage et 25 d'orchestrateur. La suite orchestrateur a réussi trois passages
complets, plus 100 répétitions isolées du scénario mutationStarted avec contrôle de l'étape
healthy attendue. Les cas à 2/10 consommateurs ont exactement un gagnant ; rejeux, reçus invalides,
claims interrompus et erreurs fsync n'autorisent aucun second gagnant. Une expiration pendant la
transition durable brûle le jeton sans retourner d'autorisation, même si l'horloge est ensuite
rétablie dans la simulation. Les refus sont persistants avec l'ancienne enveloppe réintroduite.

Rendus Compose, quatre nginx -t, huit contrôles historique, OCI/RepoDigests locaux, syntaxe de
27 fichiers Python et 63 fichiers Bash, git diff --check et scan detect-secrets 1.5.0 conformes.
FILES.txt couvre le nouveau test obligatoire ; aucun fichier hors périmètre, index Git vide.
Aucun accès VM, commit, push, build/publication Docker, changement de base ou manifeste actif.
La PWA reste désactivée par défaut. Ces validations autorisent une revue du correctif, pas une
préparation PREPROD réelle. L'horloge UTC correcte, les images utilitaires épinglées déjà présentes,
les permissions privées, la fiabilité du stockage/fsync et l'identité d'exploitation de confiance
restent des prérequis ; aucune collecte automatique des reçus terminaux n'est introduite.


## Variante privée finale — 24 octobre 2026

Le candidat `private-shell/` dispose désormais d'un orchestrateur distinct :
`release-private.py` (réservation globale persistante et machine à états),
`private-backend.py`, `private-runtime.sh`, `backup-private.sh` et
`restore-private.py`. Les commandes exactes et les modèles de preuves sont décrits
dans [ORCHESTRATEUR-PRIVE.txt](private-shell/ORCHESTRATEUR-PRIVE.txt). Les résultats
locaux et l'inventaire sont dans [RESULTATS-ORCHESTRATEUR.txt](private-shell/RESULTATS-ORCHESTRATEUR.txt).
Ces fichiers remplacent les instructions privées historiques indiquant un adaptateur manquant
ou une ouverture manuelle du service gate. Les exigences du candidat HTTPS public ci-dessus
restent inchangées ; aucune preuve privée ne certifie HTTPS, Android/iOS ou cookie Secure public.

Le profil privé conserve Nginx Docker, le tunnel `127.0.0.1:24443`, les quatre digests
existants et le provisionnement V3 exact (capacité héritée, reçu terminal exclusif, inodes
et échéances). La fenêtre de test, sous flock et réservation, est liée à une session,
limitée à 900 secondes et fermée par retrait du socket Unix, indépendamment de PWA/Docker.
Linux PDEATHSIG ferme l'enfant gate si l'orchestrateur est tué ; les preuves de fermeture
restent distinctes de l'intention. Le rollback garde le Shell démarré et le verrou Notes fermé.

Préparation locale seulement : aucune commande VM, migration, sauvegarde/restauration
réelle, modification de volume, build, commit ou push. Le GO porte sur la revue du code,
pas une installation ; les prérequis et tests métier réels restent obligatoires.


## Revue finale privée avant commit — 24 octobre 2026

**NO-GO POUR COMMIT ORCHESTRATEUR PRIVÉ PWA** : voir
[REVUE-COMMIT-ORCHESTRATEUR.txt](private-shell/REVUE-COMMIT-ORCHESTRATEUR.txt).
Quatre contre-exemples reproductibles concernent l'entrée directe restore sans
gardes complets, la fraîcheur des préconditions V3, l'expiration d'un prérequis
pendant l'ouverture et la suppression de l'environnement de reprise après échec
du nettoyage isolé. Les nouveaux tests `test-final-review.py` restent rouges.
Les tests existants verts ne valident pas ces cas. Aucun correctif runtime ou
changement de manifeste/base/volume/autre dépôt n'est appliqué par cette revue.


## Finalisation strictement limitée aux quatre blocages — 24 octobre 2026

Les quatre reproductions de revue sont désormais des non-régressions obligatoires
vertes : garde propre du runner restore (hôte/FD/configuration), préconditions V3
réellement renouvelées après baseline, revérification des trois preuves avant
ouverture avec échéance absolue dans le gate, conservation du staging/envFile
si le nettoyage isolé échoue. Aucun helper V3 ou mécanisme HTTPS public modifié.
Le compte rendu unique actuel est
[RESULTATS-ORCHESTRATEUR.txt](private-shell/RESULTATS-ORCHESTRATEUR.txt) ; les
commandes VM restent dans [ORCHESTRATEUR-PRIVE.txt](private-shell/ORCHESTRATEUR-PRIVE.txt).
Les avis NO-GO précédents sont historiques. Aucun commit ou accès VM n’est effectué.


## Abandon initial et prérequis PREPROD — finalisation ciblée

Le chemin d'abandon sans mutation ne requiert plus de marqueur Nginx inexistant ;
il ne valide aucune fermeture HTTP et ne relâche aucun garde après mutation.
Les preuves MSI, le plan synthétique d'isolation, la capacité à mesurer et les
commandes de reprise figurent dans
[PREUVES-MSI-REPRISE.txt](private-shell/PREUVES-MSI-REPRISE.txt) et les faits locaux
dans [msi-prerequisites-facts.json](private-shell/msi-prerequisites-facts.json).
Les trois attestations PREPROD demeurent fausses tant que le relecteur n'a pas
validé l'image réellement en place, les droits/comptes et les ressources de la VM.

Dossier de décision technique PREPROD privée :
[CONTROLES-PREPROD.txt](private-shell/CONTROLES-PREPROD.txt).
Commandes futures, critères GO/NO GO, preuves et corrections ; aucune validation
PREPROD ni autorisation de déploiement implicite.

Préparation des corrections après revue (aucune attestation PREPROD) :
[plan](private-shell/PLAN-CORRECTIONS-PREPROD.txt),
[protocole JPA/Flyway proposé](private-shell/PROTOCOLE-JPA-FLYWAY-ISOLE.txt),
[matrice de suivi et sessions](private-shell/MATRICE-CORRECTIONS-PREPROD.json),
[résultats locaux et blocages](private-shell/RESULTATS-CORRECTIONS-PREPROD.txt).
Le hook candidat JPA/Flyway est désormais intégré à la restauration isolée,
avant nettoyage des copies, sous verrou et réservation. Aucun déploiement effectué.

Implémentation candidate locale du validateur JPA/Flyway isolé :
[RESULTATS-VALIDATEUR-JPA.txt](private-shell/RESULTATS-VALIDATEUR-JPA.txt).
Les preuves MSI synthétiques et la worklist des247 cas ne valident aucune
attestation PREPROD et n’autorisent aucun déploiement.

Revue finale MSI et décision de commit :
[FINALISATION-COMMIT.txt](private-shell/FINALISATION-COMMIT.txt).
Les [résultats RECETTE réels](private-shell/RESULTATS-RECETTE-247.json) valident
247/247 cas en deux campagnes (144 puis103), dont19 expirations HTTP401 après
30 minutes réelles d’inactivité. Aucun rejeu lors de la revue finale.
Le rapport RESULTATS-ISOLATION-247.json conserve le blocage historique antérieur.
Les trois attestations PREPROD restent false ; aucun déploiement n’est autorisé.

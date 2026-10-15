# Livraison cohérente PWA + Notes de frais — préparation inactive

État : code applicatif préparé, aucun commit, aucune image construite/publiée et aucun déploiement.
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
commutateur et aux droits Notes de frais dans le Shell. Le candidat remplace seulement ces deux
fichiers quand tous les composants sont prêts. Le commutateur est une règle de présentation,
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

1. Revoir, commiter puis construire/publier ensemble **Factures API, PWA, Factures Front et Shell**.
   Compléter `release-plan.json.images` avec les versions et digests vérifiés des quatre images.
   `validate-bundle.py` refuse le lot incomplet actuel. Réutiliser ensuite les contrôles existants
   des RepoDigests, labels OCI version/revision/source et l'épinglage `image@sha256:...`.
2. Faire valider le domaine et le certificat HTTPS : PREPROD est actuellement décrite avec un tunnel
   HTTP, ce qui ne suffit pas pour un smartphone distant. `edge-https.conf.template` est un modèle
   inactif de terminaison TLS vers le port ERP loopback. Ne pas exposer ce port directement.
   La configuration machine devra utiliser `WAVY_ACCESS_MODE=https`, `WAVY_COOKIE_SECURE=true`,
   une origine HTTPS exacte pour `WAVY_PUBLIC_URL` et CORS. Préserver Anthropic, modèle et clé.
   Le cookie Socle doit garder Path=/, HttpOnly et SameSite existants. Aucun secret/certificat ici.
3. Provisionner `notes-frais` dans le volume documentaire existant avec le compte applicatif attendu
   (100:101, à confirmer sur les images finales), mode 0700, avant de monter son subpath. Ne jamais
   remplacer le volume ni changer les propriétaires du répertoire Contrats. La racine doit être
   réelle, préexistante et durable ; aucun fallback vers le disque éphémère n'est autorisé.
4. Revoir puis promouvoir les candidats `scripts/*` via `integration-scripts.patch`. Le validateur
   Compose accepte alors les deux propriétaires documentaires et exige le montage subpath.
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
   PWA et Factures Front, contrôles session/stockage/isolation, **Shell et activation publique en dernier**.
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

- `python3 preparation/pwa-notes-frais/test-candidate.py` : 8 tests, Compose fictif, archives sûres,
  chiffrement/déchiffrement, intégrité HMAC, restauration d'octets originaux, compatibilité ancien lot,
  scripts candidats et refus d'un lot d'images incomplet. Les dumps sont des fixtures, pas de vraies DB.
- `python3 preparation/pwa-notes-frais/test-nginx-local.py` : nginx -t sur une image déjà locale,
  réseau coupé, sans build/pull et sans démarrer de serveur, pour route fermée et candidate.
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
Ne déclarer ces contrôles réussis qu'après leur exécution. Les images nouvelles, le domaine/certificat,
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

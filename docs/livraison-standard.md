# Livraison Wavy — préparation du 28 octobre 2026

## Décision

**GO technique pour publication**, autorisée par l’utilisateur le 28 octobre
2026 après revue. Les 109 tests ont été rejoués avec succès avant commit/push ;
les 13 digests sont inchangés et aucun secret, temporaire ou historique privé
n’est inclus dans les fichiers à publier. **Installation distante non autorisée
et non exécutée**. Son GO sera calculé sur la VM par `./wavy install recette` ; ce rapport
ne certifie ni ses comptes, ni son stockage, ni son proxy. PREPROD reste inchangée.

L'environnement de travail accessible ne présente aucun conteneur Wavy actif.
La validation fonctionnelle MSI est celle fournie par l'utilisateur, pas une
campagne rejouée ici. Les comparaisons ci-dessous portent sur les fichiers de
release, leurs rendus Compose réels et les scripts ; l'état réel des deux VMs
reste à contrôler automatiquement lors de l'installation autorisée.

## Écarts utiles à la livraison

| Sujet | MSI local HTTPS | RECETTE distante | PREPROD | Cause / correction ou différence normale |
| --- | --- | --- | --- | --- |
| Images | Cycle local existant, pouvant inclure des builds ; état actif non observé | 13 références `version@sha256` via `release_images.py` | Mêmes 13 références dans les manifestes | Correction digests déjà présente ; parité vérifiée automatiquement, disponibilité GHCR contrôlée à l'installation |
| Spring | Configuration locale du cycle `./wavy local` | Profils `recette` exigés pour les cinq API et Gateway par l'installation | `preprod,secure`, gardes existantes | Différence normale ; profils local/dev/test refusés sur RECETTE |
| Priorité des variables | Cycle HTTPS MSI conservé | Dotenv privé machine, puis manifestes version/digest ; shell neutralisé pour les clés Compose | Parseur strict PREPROD conservé | Doublon ERP retiré de l'exemple ; l'installation refuse doublons et versions/digests dans le dotenv machine |
| CORS et HTTPS | Origine locale distincte | Une seule variable CORS partagée, contenant l'origine HTTPS ; stratégie Spring `framework` ajoutée | Politique CORS/secure existante | CORS déjà corrigé ; transmission des en-têtes proxy explicitée pour les API et Gateway RECETTE |
| Routes ERP/PWA | Intégration locale déjà validée par l'utilisateur | Montages Nginx/manifeste existants réutilisés | Workflow protégé inchangé | Routes déjà corrigées ; nouveau mode technique évite le prérequis circulaire d'une qualification des images déjà actives |
| Droits et écritures | Droits métier existants | PWA et mutations Notes persistantes après prérequis, sans fermeture automatique ; contrôles backend inchangés | Aucun droit supplémentaire | Aucune modification des rôles, du tenant ou des sociétés ; la validation humaine intervient après installation |
| Justificatifs Factures | Stockage propre au cycle MSI | Volume externe nommé, privé, UID/GID applicatifs non root, dossiers 0700/fichiers 0600 | Gardes documentaires existantes | Provision initial autorisé explicitement dans le dotenv ; seul un volume absent et vide peut recevoir ses permissions initiales |
| Conservation | Données locales séparées | Refus de changement de volume ou de sous-chemin ; refus de masquer un dossier préexistant non vide | Protections existantes | Aucun chown récursif, déplacement, suppression ou migration documentaire implicite |
| Réseau | Exposition locale historique conservée | Les 18 publications passent à loopback par défaut et sont contrôlées | Loopback / réseau privé existants | Repli historique `0.0.0.0` supprimé en RECETTE ; proxy HTTPS local à la VM requis par ce parcours |
| Démarrage | Cycle MSI inchangé | Factures/Trésorerie : grâce 120 s, 18 essais ; attente Compose 600 s par défaut | Délais et gardes existants conservés | Budget conservateur configurable ; aucun temps réel VM prétendument mesuré |
| Sauvegarde | Commandes historiques conservées | Backup existant : arrêt coordonné des writers, cinq dumps + archive justificatifs vérifiée, reprise | Backups chiffrés et gardes existants | Premier rattachement vide désormais sauvegardable avant remplacement |
| Restauration / migrations | Fixtures isolées testées | Détection des erreurs Flyway après remplacement, aucun rollback DB automatique | Orchestrateur migrations/restauration conservé | Exercice isolé corrigé pour attendre le serveur PostgreSQL final ; aucune restauration VM exécutée |
| Configuration VM / Git | Fichiers privés non suivis | `.env.recette` et journaux ignorés ; installation refuse les fichiers de livraison modifiés | `.env.preprod` et historiques runtime existants | Aucun `git pull`, stash, reset ou réécriture de manifeste par install ; historique append-only avec révision Git |

Les sauvegardes RECETTE réutilisées couvrent les cinq bases et les justificatifs
Factures. Elles ne constituent pas un archivage de tous les volumes possibles
(notamment les pièces jointes Contrats). Ces volumes restent attachés ; aucune
restauration globale de tous les documents n'est revendiquée ici.

## Configuration initiale RECETTE, une seule fois sur la VM autorisée

Conserver le dotenv existant et ses secrets ; ne pas le remplacer par l'exemple.
Y définir sans doublons :

```dotenv
WAVY_INSTALL_HOSTNAME=<hostname court exact de la VM RECETTE>
WAVY_RECETTE_VALIDATION_MODE=technical
WAVY_PWA_ENABLED=true
WAVY_NOTES_WRITES_ENABLED=true
WAVY_PWA_PUBLIC_ORIGIN=https://recette.wavyservices.fr
WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=https://recette.wavyservices.fr
WAVY_FACTURES_JUSTIFICATIFS_VOLUME=<nom privé propre à RECETTE>
WAVY_RECETTE_PRIVATE_BIND_ADDRESS=127.0.0.1
WAVY_INSTALL_WAIT_SECONDS=600
```

Le dotenv doit appartenir à l'opérateur et être privé (0600). Les mots de passe
DB et du compte interservices doivent être configurés, sans valeurs d'exemple.
Tous les profils doivent être `recette`. Le nom de projet reste `wavy-recette`.

Pour un volume absent uniquement, ajouter
`WAVY_RECETTE_PROVISION_JUSTIFICATIFS=true`. Le script relève UID/GID dans l'image
Factures épinglée, crée le volume local, vérifie sa provenance et son contenu
vide, puis initialise uniquement sa racine. Un volume existant est seulement
contrôlé ; ses droits ne sont jamais réparés automatiquement. Une initialisation
interrompue reste visible et exige une correction explicite, sans effacement.
Le paramètre peut repasser à false après la première installation.

Si un autre stockage existe déjà, si des fichiers occupent le futur point de
montage, si le proxy HTTPS est ailleurs que sur la VM ou si l'installation DB est
partielle, la commande refuse de continuer. Il faut alors traiter cet écart
identifié ; aucun déplacement de données ou bootstrap DB n'est implicite.

## Commandes réutilisables

Sur MSI : `./wavy local up` (cycle existant conservé).

Sur la VM RECETTE, après publication approuvée et synchronisation Git :

```bash
./wavy install recette
```

La commande garde le verrou RECETTE pendant le parcours : configuration rendue,
inventaire de l'installation et espace disque, vérification/téléchargement des
13 images, stockage privé, sauvegarde coordonnée, remplacement sans build,
attente de disponibilité, détection des erreurs de migration, test/reload Nginx,
vérification des 13 images actives, des API healthy et des ports privés, puis
contrôle TLS système de l'ERP, du manifeste PWA ouvert, des routes modules/PWA,
du service worker, du préflight CORS HTTPS et du refus de session non authentifiée. Les services restent
démarrés. Un échec n'entraîne ni suppression de volume ni restauration automatique.

Vous ouvrez ensuite **https://recette.wavyservices.fr** et effectuez vos tests
fonctionnels avec les écritures et les droits métier normaux. L'IA dépend des
secrets et du fournisseur configurés ; les contrôles techniques n'appellent pas
le fournisseur et ne certifient pas le parcours métier.

Après votre décision fonctionnelle :

```bash
./wavy validate recette
```

Cette commande revérifie le runtime et vous demande explicitement votre décision.
Elle enregistre uniquement votre validation humaine, liée aux 13 images, dans
`deployments/recette-validation.private.json` (0600, ignoré par Git). Elle ne
fabrique pas une liste de tests métier réussis. Transférer ce reçu privé sur la
VM PREPROD par le canal d'exploitation autorisé, au même chemin du dépôt.

Sur PREPROD :

```bash
./wavy install preprod
```

Le reçu doit correspondre aux manifestes RECETTE et PREPROD identiques. Le
wrapper conserve le verrou/réservation existant puis appelle `deploy.sh preprod`
pour chacun des 13 composants, avec ses backups chiffrés, vérifications OCI,
contrôles migrations, contexte smoke, contrôles Nginx et historiques existants.
Il cible une installation PREPROD existante ; le provisionnement vide demeure
la procédure explicite historique. Aucun Compose PREPROD n'a changé.

Les commandes historiques, les redémarrages individuels et `./wavy local` restent
disponibles. Le mode RECETTE historique `qualification` reste utilisable ; le
nouveau parcours standard sélectionne explicitement `technical`. Aucune preuve
fonctionnelle périmée n'est nécessaire à chaque installation RECETTE.

## Modifications réalisées et validation

- `wavy`, `scripts/install.sh` : installation intégrée et validation humaine.
- `scripts/delivery_check.py` : rendu, contrôles locaux/runtime, parité de promotion.
- `scripts/recette_storage.py` : provision initial contrôlé et inspection privée.
- `scripts/recette_pwa.py`, `scripts/release_images.py` : mode technique RECETTE et capture du rendu réel par le chemin existant.
- `scripts/_recette-documents.sh` : backup initial avant premier rattachement vide.
- `docker-compose.recette.yml`, `.env.recette.example`, `.gitignore` : réseau, en-têtes HTTPS, délais, paramètres privés et historique.
- `scripts/test-delivery.py`, tests PWA/restauration et workflow CI existants : non-régression ciblée.

Tests exécutés avec succès : livraison (12), images (5), CORS (3), PWA (25),
documents (11), configuration PREPROD (36), gardes PREPROD (10), Nginx RECETTE
réel (1), Nginx PREPROD réel (5), restauration isolée cinq bases + documents (1),
historique versions/digests, syntaxe Bash et `git diff --check`.
L'exercice de restauration a d'abord échoué sur une course du serveur temporaire
PostgreSQL ; après correction de l'attente TCP, il passe. Les tests Nginx et
restauration utilisent des ressources jetables distinctes des ressources Wavy.
Aucune campagne fonctionnelle des composants n'a été relancée.

La CI existante appelle désormais le contrôle de livraison sur des rendus réels
RECETTE/PREPROD et des secrets fictifs isolés. Les cas d'échec de prérequis,
stockage, backup et démarrage vérifient l'arrêt du parcours avant l'étape suivante.
Les contrôles spécifiques à la VM sont exécutés par l'installation, pas attestés
ici. Les 13 images ne sont pas reconstruites ni republiées par ce correctif.

## Conditions du GO installation RECETTE

1. Publication du correctif autorisée le 28 octobre 2026 ; synchroniser ensuite ce commit sur la cible dans le cadre de l’intervention VM autorisée.
2. Votre accord d'accès/déploiement VM ; aucun accès distant réalisé pendant cette préparation.
3. Configuration initiale privée cohérente, proxy local et prérequis locaux satisfaits ; le script donne les refus concrets.
4. Installation et vérifications runtime réellement réussies sur la cible.

La validation fonctionnelle et le GO PREPROD restent votre décision après vos tests.

## Cohorte immuable commune RECETTE / PREPROD

Ces références proviennent des manifestes locaux ; leur présence effective sur les VMs n’est pas attestée.

| Composant | Version | Digest commun |
| --- | --- | --- |
| socle-api | `0.1.0-8b7a3f0` | `sha256:640253c045feabd0be90a81e29b46af28b2c3c5e19d0fb81c0e89b7da45bdf31` |
| tiers-api | `0.1.0-7642a09` | `sha256:6c91e16bd3f5211c892273031f5ab1f1d56d6007e4003e0dd382fef845f2400e` |
| contrats-api | `0.1.0-527874b` | `sha256:f60edb42690fa005748cdf6bbf9f2b9fdeb956ce3001c1e3ae0655dc2ad72ff0` |
| factures-api | `0.1.0-09fcd98` | `sha256:a414a866c910bd20a4c8af4018fc0e31db513ffff1cca76b15c913807f75d0e5` |
| tresorerie-api | `0.1.0-45fd268` | `sha256:e45d7063a3715d8dc370458960d6dcda7fa731582ceb902ea42e2f8b3dd33f56` |
| gateway | `0.1.0-3ff5c3b` | `sha256:6bb0ff5ea147fd5b51a6dbb00f8333d84220b6160696a64186f53f512b53587e` |
| socle-front | `0.1.0-d4c76c5` | `sha256:1d32cb2cc8cbb5c334800d6fa13df2dff9e1293988179f0df8138b77958fbdaa` |
| tiers-front | `0.2.0-05594f9` | `sha256:45cd1ad15e450946e360347ae76738b28f20e69517e82313c5061f15dbc457ef` |
| contrats-front | `0.2.0-e05aabc` | `sha256:5562ba2cf480630aa66cc1ced8484f61b24c1dbf619966464f27a9df0d7484a6` |
| factures-front | `0.2.0-0663a99` | `sha256:e116a8eaf8141684b9ce27e056c8e21eadd30e42c2215c67a0c678ee4dca3726` |
| tresorerie-front | `0.2.0-9c2bea6` | `sha256:061a1b61488313f07c5f57b84b53f20b83f6ccdd4da03f484bacaf69fa76c7b6` |
| pwa | `0.2.0-9bfd217` | `sha256:9f10a7e8716b1fe4a09a91653e7591a00f8f5c64b1b1dc667cae685f5a375938` |
| erp-shell | `0.2.0-f6ee944` | `sha256:450328d7bea84b1c9e11616daa03067f6fe6da8dcc2d5bf929a46c909940ae96` |

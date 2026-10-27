# Qualification et restauration PWA RECETTE

Préparation MSI uniquement. Ce document et `./wavy pwa recette check --plan`
n'autorisent ni accès VM, ni déploiement, ni écriture dans les données existantes.

## Diagnostic centralisé

- `./wavy pwa recette check` : paramètres, qualification approuvée, images,
  origine, volume, contrôles et lien SHA256 sauvegarde/restauration. Aucun Docker.
- Ajouter `--plan` : comptes, clients et cas fonctionnels attendus, sans exécution.
- Ajouter `--runtime` : daemon Docker local sur socket Unix uniquement,
  métadonnées des services, digests actifs, santé, montage documentaire,
  UID/GID effectifs, modes 0700/0600, absence de liens, espace libre (1 Gio),
  et publications de ports. Aucun chmod/chown, lecture de justificatif ou SQL.
- Ajouter `--backup-dir /chemin/du/lot` : vérifier les cinq dumps et l'archive
  existante, leur empreinte, leur provenance et la structure privée des documents.
  Vérifier un lot ne prouve pas sa restauration : `restorationVerified=false`.

L'option runtime ne contacte aucun serveur distant. Sur la VM, son exécution
locale devra être autorisée séparément. Sur MSI, elle décrit uniquement MSI.
Les droits insuffisants, services manquants ou volumes non conformes donnent
NO-GO, sans provisionnement ni changement de données.

## Contrôles avant ouverture

Le correctif Gateway ajoute les droits Notes et les seules routes Tiers de la PWA
au profil RECETTE, en excluant PREPROD et production, y compris les profils mixtes.
Les tests locaux vérifient les refus et le contexte ; une nouvelle image Gateway
reste à commiter, construire et publier après accord. Le Gateway publié `38330ce`
ne contient pas encore ces corrections et ne permet pas de qualifier un compte
ordinaire. Ne pas remplacer ce compte par un administrateur pour masquer le défaut.

La visibilité et les écritures sont deux paramètres persistants. Ne mettre aucun
paramètre à true avant la qualification correspondante. Garder le volume existant
même si la visibilité est fermée. Un compte rendu privé approuvé lie les sept
images concernées, l'origine et le volume ; son objet `backup` doit contenir le
même SHA256 dans `manifestSha256` et `restoredManifestSha256`. C'est une attestation
revue d'un exercice réel, pas un simple résultat de checksum ni un fichier de test.

Les accès directs doivent être privés. Le paramètre RECETTE
`WAVY_RECETTE_PRIVATE_BIND_ADDRESS=127.0.0.1` réserve les 18 ports Docker (API,
DB, fronts, PWA et Shell) à l'hôte ; le proxy HTTPS existant doit pouvoir joindre
le Shell local. Le repli Compose historique reste `0.0.0.0` pour ne pas changer
silencieusement une installation existante. Ce repli n'est pas un GO réseau.
Aucun port PREPROD n'est modifié.

Si le proxy HTTPS est sur un autre hôte, ne pas appliquer loopback à l'aveugle :
qualifier son chemin réseau et le filtrage existant avant toute modification.
Le diagnostic automatique reste conservateur et refuse une publication Docker
hors loopback ; une topologie différente nécessite une validation spécifique.
Un bind loopback ne prouve pas à lui seul l'absence d'un autre proxy exposant une
API. Un essai depuis un poste extérieur reste requis.

## Campagne ERP et smartphone après autorisation

Préparer des comptes et des données de test explicitement autorisés : deux
tenants, deux sociétés du tenant A, deux utilisateurs ordinaires, un rôle sans
Notes et un super utilisateur Notes. Associer chaque utilisateur à son porteur
Tiers dans sa société ; ne pas réutiliser des documents clients pour les tests.
La création des fixtures et leur éventuelle suppression nécessitent un accord.
Aucun scénario de ce document ne s'exécute automatiquement.

| Cas | Manipulation | Résultat attendu |
| --- | --- | --- |
| AUTH | Session absente, expirée, mot de passe incorrect, puis connexion valide | 401 ou 200 selon le cas ; cookie Secure/HttpOnly ; aucun contexte falsifié accepté |
| ROLE | Compte NOTE_DE_FRAIS sur Notes, `/tiers/me`, recherche/reconnaissance et création rapide marchand | Accès limité au contexte, création seulement sur le compte de test autorisé |
| REFUS | Rôle sans Notes ; PUT/DELETE tiers/marchands ou alias | Menu/guard refusés et API 403 ; aucun changement |
| ERP | Ouvrir Mobile PWA dans la zone de droite | Iframe sous `/pwa/`, navigation et paramètres conservés ; pas de fenêtre autonome imposée |
| MOBILE | Android et iOS : `/pwa/connexion`, connexion, installation puis réouverture | HTTPS valide, session réelle, service worker de scope `/pwa/`, usage autonome |
| VISIBILITÉ | Visibilité=true, écritures=false | Application disponible ; mutations Notes ERP/mobile à 403 |
| NOTES | Avec écritures autorisées : créer/modifier note avec JPEG, PNG et PDF | Succès pour les seules opérations permises ; fichier/hash identiques après reconnexion |
| ISO tenant | Session B sur URL de note/document du tenant A | 403/404, aucun octet privé ni modification |
| ISO société | Changer A1 vers A2, réutiliser URL et cache A1 | Nouveau contexte, données A1 inaccessibles ; retour A1 maîtrisé |
| ISO utilisateur | Utilisateur ordinaire sur note/document d'un autre porteur | Refus conforme aux règles backend ; super rôle limité au tenant/société |
| CONCURRENCE | Deux remplacements approuvés d'un justificatif de test | Cohérence DB/fichier et refus étrangers ; aucun document orphelin livré |
| RÉSEAU | Depuis Wi-Fi externe puis 4G, tester les ports Docker connus | API/DB/fronts directs inaccessibles ; seul l'accès HTTPS prévu fonctionne |
| PERMANENCE | Redémarrage standard autorisé et fin de campagne | Réglages conservés ; pas de bail, fermeture automatique ou suppression des données |

Conserver les résultats datés, les empreintes des images et des lots, les statuts
et les preuves nécessaires hors Git, sans cookie ou mot de passe. Le module ne
se referme pas en fin de campagne. Le nettoyage éventuel porte uniquement sur
les IDs de fixtures approuvés et fait l'objet d'une autorisation distincte.

## Sauvegarde standard préparée

`./wavy backup recette` reste l'entrée existante. Quand un volume de justificatifs
est configuré, le backup vérifie le montage et les permissions avec l'utilisateur
Factures, puis arrête proprement Gateway et les cinq APIs writers, dans cet ordre.
Un arrêt forcé à 137 est refusé. Le verrou RECETTE existant est partagé avec
le cycle local et les commandes de sauvegarde, démarrage, déploiement et rollback
standard pour empêcher une reprise concurrente des writers. La fenêtre approuvée
doit également exclure tout writer SQL extérieur à ces commandes. Les bases restent démarrées pour produire les
cinq dumps custom ; chaque dump est relu par `pg_restore --list`.

La même fenêtre d'arrêt inclut `justificatifs.tar`, produit en lecture seule par
l'image Factures active, sans réseau et sans copie dans le volume. Le validateur
refuse les liens, entrées spéciales, chemins non conformes à
`tenant/société/note/UUID`, doublons, propriétaires/modes incorrects et fichiers
excessifs. Les fichiers sont privés 0600 dans un répertoire 0700.

`recette-pwa.json` lie les six fichiers par SHA256 et renseigne volume et UID/GID.
Ce sont des contrôles d'intégrité dans un répertoire privé, pas une signature
contre un administrateur hostile. Le lot n'est renommé en sauvegarde complète
qu'après la reprise des services initialement arrêtés. En cas d'échec, les
services arrêtés sont repris et le dossier `.incomplete-*` reste disponible pour
analyse ; il n'est jamais accepté comme lot complet ni supprimé automatiquement.
Un échec de reprise indique explicitement les services à reprendre.

Le rollback applicatif RECETTE réutilise aussi les montages et les digests du
chemin commun : seule une cible de l’historique validé est acceptée ; une PWA
ouverte ne peut pas basculer sur une cohorte non qualifiée.

Le flux local historique sans justificatifs reste disponible. PREPROD utilise
toujours sa chaîne chiffrée, ses verrous et sa procédure propres, sans modification.

## Procédure de restauration à valider en maintenance

1. Faire approuver le périmètre de restauration et l'interruption d'écritures.
   Produire et conserver une sauvegarde de l'état courant avant toute opération.
2. Vérifier le lot avec le diagnostic centralisé ou
   `python3 scripts/recette_documents.py verify /chemin/du/lot`.
   Refuser une origine autre que RECETTE, un fichier absent/altéré ou un lot incomplet.
3. Répéter la restauration dans des ressources **neuves et isolées** : cinq bases
   PostgreSQL compatibles avec les dumps et un volume documentaire neuf, sans
   port publié, réseau applicatif, volume externe ou nom de conteneur actif.
4. Restaurer les cinq dumps avec `pg_restore --exit-on-error --no-owner`, puis
   l'archive documentaire prévalidée dans un volume vide, en préservant UID/GID
   et modes. Ne jamais extraire une archive non validée sur un chemin actif.
5. Comparer les données attendues et les documents. Pour les notes dont
   `piece_chemin_stockage` commence par `ndf:`, vérifier la correspondance
   `tenant_id/societe_interne_id/id/UUID`, le SHA256 et la taille avec
   `piece_hash_sha256` et `piece_taille_octets`. Vérifier les modes et les refus
   d'accès avec les tests métier du même lot logiciel. Ne pas lancer de migration
   ou de chargement de fixtures sur les bases existantes pour faire passer le test.
6. Consigner le SHA256 de `recette-pwa.json` réellement restauré dans le compte
   rendu. La valeur doit correspondre à celle du lot sauvegardé. Ne pas marquer
   une simple vérification d'archive comme exercice de restauration réussi.
7. La restauration active nécessite ensuite un plan approuvé distinct : writers
   arrêtés, restitution cohérente des cinq DB et des documents, ancien volume et
   sauvegarde de retour conservés, contrôles de schéma et fonctionnels, puis reprise.
   Ne pas continuer avec une cohorte partiellement restaurée. Le script historique
   `restore-db.sh` refuse une DB seule pour un lot documentaire ou un stockage
   documentaire configuré ; aucun chemin destructif automatique ne contourne ce refus.

`python3 scripts/test-recette-restore.py` exécute le mécanisme sur fixtures MSI :
cinq dumps/restaurations réels, document privé et hash, UID/GID/modes, puis refus
d'un fichier volontairement rendu trop permissif. Conteneurs sans réseau et
volume de test à nom aléatoire uniquement ; ces fixtures jetables sont supprimées.
Ce résultat ne vaut pas restauration d'un lot de données RECETTE réel.

## Bilan de cette préparation

Publication : GO technique après tests. Les commits, push GitHub et publication
GHCR sont autorisés. Les manifestes RECETTE et PREPROD peuvent référencer la
nouvelle image sans modifier les règles PREPROD, explicitement exclues des
nouvelles autorisations. Cela n’autorise ni déploiement ni activation.

Activation RECETTE : NO-GO tant que la nouvelle image n'est pas publiée et épinglée,
que volume, ports, sauvegarde/restauration réelle et parcours ERP/smartphone ne
sont pas qualifiés sur la configuration cible. L'accès VM et les éventuelles
écritures de qualification doivent être autorisés séparément.

## Résultats exécutés sur MSI pour cette finalisation

| Périmètre | Résultat |
| --- | --- |
| Gateway, dont droits RECETTE et refus PREPROD/profils mixtes | 159 tests réussis |
| Tiers : contrôleur et configurations de sécurité ciblés | 47 tests réussis |
| Factures : Notes, justificatifs, isolation, concurrence et stockage | 36 tests réussis |
| DevOps/HTTPS : politiques, lots, verrous, rollback, Nginx réel et restauration isolée | 149 tests Python réussis |
| PWA et Shell : sessions, contexte, rôles et intégration | 55 + 22 tests réussis |
| Historique des versions, syntaxe Bash, whitespace Git | Validés |

Les tests DB utilisent leurs bases Testcontainers et leurs fixtures. L'exercice
isolé vérifie réellement les cinq dumps/restaurations, le document et ses droits ;
il ne lit pas un lot de données existantes. Les tests du backup standard simulent
Docker pour vérifier l'ordre des opérations et les échecs sans arrêter de service
existant. Aucun compte rendu RECETTE approuvé n'est créé à partir de ces fixtures.

Le diagnostic en lecture seule exécuté sur MSI reste en NO-GO : aucun compte
rendu cible/volume n'est configuré dans le dotenv RECETTE standard et un stockage
applicatif existant est détecté ; il ne sera pas remplacé implicitement. Le cycle
local permanent conserve son propre montage et ses données. Cela n'indique rien
sur les permissions ou le volume de la VM distante, qui n'a pas été consultée.

État à la fin de la préparation, avant autorisation de publication : les commits
étaient `cbcc098` DevOps et `38330ce` Gateway, sans push, build de release ni
déploiement. Le rapport de publication consignera les nouveaux commits et le
vrai digest GHCR ; les autres composants restent inchangés.

# Synchronisation ponctuelle PREPROD → RECETTE

Depuis le checkout DevOps de la **VM RECETTE distante** :

```bash
./wavy sync preprod recette
```

La commande est locale à RECETTE et ne déploie aucun code sur les VM. Les scripts
correspondants doivent avoir été installés sur les deux VM par le parcours
habituel, après approbation. Aucun autre sens, argument `--yes` ou exécution non
interactive n'est accepté.

## Configuration initiale

Conserver `.env.recette`, ses secrets et les prérequis du parcours standard
(`WAVY_INSTALL_HOSTNAME`, mode `technical`, volume privé de justificatifs déjà
monté). Ajouter une seule fois dans ce fichier privé 0600 :

```dotenv
WAVY_SYNC_PREPROD_SSH=operateur@wavy-preprod
WAVY_SYNC_PREPROD_ROOT=/chemin/absolu/wavy-devops
```

La passphrase existante `WAVY_BACKUP_ENCRYPTION_PASSPHRASE` est lue automatiquement
dans le `.env.preprod` privé via SSH, avec le parseur PREPROD existant. Aucune saisie
ni copie du secret dans `.env.recette` n'est requise ; l'ancienne variable
`WAVY_SYNC_PREPROD_BACKUP_PASSPHRASE` n'est plus consultée. Le secret reste en mémoire,
sans affichage ni enregistrement dans les fichiers de synchronisation. Le dotenv
PREPROD n'est ni copié ni modifié. Ce secret chiffre aussi le secours RECETTE ;
le conserver tant que ces lots sont utiles. SSH utilise la configuration existante, une clé déjà autorisée et
une clé d'hôte déjà approuvée (`BatchMode`, `StrictHostKeyChecking`). Aucun secret
n'est transmis en argument de commande ou journalisé.

Les deux VM doivent utiliser PostgreSQL 16, les cinq bases dans le schéma public
et des tenants sans routage vers des bases dédiées. Un routage dédié est refusé
pour éviter de recopier des destinations techniques PREPROD. Les images actives
doivent correspondre aux manifestes versionnés, et être disponibles par digest
pour la même architecture. Les deux volumes documentaires RECETTE doivent déjà
exister, être locaux et distincts. Aucun stockage n'est provisionné.

## Mise en service et premier essai sans remplacement

Après autorisation du commit et du push sur `master`, mettre à jour le checkout
DevOps existant sur **chacune des deux VM**, depuis sa branche `master` propre :

```bash
git pull --ff-only origin master
```

Ne pas écraser de modifications locales si Git refuse. Cette mise à jour suffit
à rendre les scripts disponibles : `wavy` est déjà exécutable et appelle Python.
Il n'est pas nécessaire de lancer `./wavy install`, de reconstruire des images
ou de redémarrer les applications pour installer cette commande.

Sur RECETTE seulement, éditer le `.env.recette` existant avec un éditeur local :
`WAVY_SYNC_PREPROD_SSH` est le compte et le nom/adresse SSH de PREPROD ;
`WAVY_SYNC_PREPROD_ROOT` est le chemin absolu de son checkout DevOps.
Si ces deux paramètres sont déjà renseignés, aucune nouvelle configuration n'est
nécessaire. La passphrase est récupérée automatiquement avant toute sauvegarde,
sans interruption de PREPROD pour cette lecture. Le compte SSH doit être le
propriétaire habilité à lire le `.env.preprod` privé, comme pour son backup habituel.
Conserver le fichier RECETTE privé (0600), sans doublons ni changement des autres
paramètres. La liaison SSH doit fonctionner depuis RECETTE vers PREPROD avec les
clés et droits Docker de l'opérateur habituel.

Le correctif de chargement de la passphrase ne nécessite de mettre à jour que le
code de RECETTE : il utilise le parseur déjà installé sur PREPROD, sans nouveau
script ni changement de secret sur cette dernière.

Pour le premier essai **après autorisation distincte**, vérifier l'absence d'état
`deployments/recette-sync.json` sur RECETTE : un état incomplet déclencherait une
reprise automatique avant la confirmation. Puis lancer la commande habituelle
et saisir **`non`** à la demande `ECRASER RECETTE`.

Cet essai réalise une vraie sauvegarde PREPROD (avec courte interruption), son
transfert chiffré et ses vérifications ; des images peuvent être téléchargées.
Il ne remplace ni les données, ni les images actives RECETTE, et n'arrête pas ses
applications. Il se termine volontairement par `Annulé` et un code non nul.
Ce n'est pas un mode sans effets : sauvegardes et cache d'images occupent de
l'espace. Il ne qualifie pas encore la restauration ni le rollback réels.

## Déroulement

1. Verrou RECETTE existant. Sur PREPROD, verrou/réservations existants et commande
   `backup-preprod.sh` inchangée : arrêt propre des six backends, cinq dumps et
   documents chiffrés, puis reprise. Un lot frais et les références des treize
   images sont reçus via SSH. Aucun dotenv PREPROD n'est copié.
   La reprise dispose d'un budget commun de 600 secondes pour les six backends :
   les états transitoires sont tolérés tant que les conteneurs fonctionnent, mais
   tous doivent être `healthy` avant la finalisation du lot. Ce délai concerne
   uniquement la sauvegarde ; les autres parcours PREPROD restent inchangés.
2. Authentification HMAC du lot, déchiffrement privé, validation des archives et
   catalogues PostgreSQL, vérification des images. PREPROD est déjà repartie.
3. **Une confirmation** `ECRASER RECETTE`, indiquant la date source et l'hôte cible.
   Annuler n'écrase pas RECETTE ; la sauvegarde PREPROD a toutefois déjà eu lieu.
4. `backup-db.sh --sync-hold` réutilise le backup coordonné RECETTE, ajoute les
   pièces Contrats et laisse les writers arrêtés après succès. Le lot de secours
   complet est chiffré et authentifié avant suppression de sa copie claire.
5. Arrêt de tous les composants applicatifs RECETTE et désactivation de leur
   redémarrage automatique. Restauration des cinq bases et des deux stockages.
   Le schéma public antérieur est remplacé, afin de ne pas conserver de tables
   spécifiques à l'ancienne version. Aucun nouveau schéma métier n'est introduit.
6. Mise à jour des seuls manifestes d'images RECETTE ; configuration et identités
   techniques restent celles de RECETTE. Les rôles/ACL PostgreSQL source ne sont
   pas importés. Les comptes interservices restent configurés par RECETTE ; les
   utilisateurs métier et leurs identifiants sont copiés avec les bases.
7. Recréation via `release_images.py` et le Compose RECETTE existant, attente de
   santé et smoke tests existants. Aucun build, installation ou second moteur.
   Lorsque la politique de synchronisation est active, les contrôles HTTP passent
   par `docker exec` sur le réseau interne, sans dépendre des ports publiés sur la
   VM. Les mêmes réponses applicatives sont exigées ; les autres modes conservent
   leur transport habituel. Le Shell est vérifié par son proxy interne : cinq
   modules, chaîne Shell → Gateway → Tiers, refus de session anonyme et routes
   PWA si activées. Ce contrôle interne ne qualifie pas l'accès HTTPS via Caddy.
   L'entrée `127.0.0.1:24207` et son routage vers Tiers sont également vérifiés
   depuis la VM avant d'activer le redémarrage automatique.

Contrats conserve des chemins absolus en base. Un alias du volume RECETTE sous
`/app/data/contrats` permet de lire ces chemins PREPROD tout en conservant le
montage RECETTE historique. Les justificatifs sont extraits sans la racine
`notes-frais`, vers le volume Factures. Identifiants, contenu et propriétaires
archivés sont conservés.

## Protection persistante de RECETTE

`deployments/recette-sync-policy.json` est un état local privé, ignoré par Git,
lu par le chemin Compose habituel. Le réseau applicatif devient le réseau Docker
**interne** `wavy-recette-sync`, sans routage externe et sans connexion PREPROD.
Les cinq API, cinq bases, cinq fronts, Gateway et PWA y restent exclusivement.
Seul l'ERP Shell, reverse proxy existant, rejoint également le réseau d'entrée
existant `wavy-recette` (déclaré externe, jamais provisionné par la synchronisation).
Seul son port `127.0.0.1:24207` est rendu accessible à l'hôte, pour le tunnel SSH
Windows existant. Le port 28080 de Socle reste inaccessible depuis l'hôte.
Le Shell ne route aucun paquet entre ses interfaces (forwarding IPv4/IPv6 à 0),
perd NET_ADMIN/NET_RAW et conserve exclusivement les destinations Nginx internes
imposées par le code. Les contrôles refusent un proxy arbitraire, un port public,
un service métier sur le réseau d'entrée ou un conteneur supplémentaire sur celui-ci.
Les clés applicatives RECETTE restent configurées, mais les appels aux fournisseurs
externes (IA comprise), emails, paiements et webhooks sont inaccessibles par ce
réseau. SMTP pointe aussi sur un port local fermé ; la création automatique IA
est désactivée. L'accès entrant continue d'utiliser les domaines et ports RECETTE.
Un proxy ou service local capable de relayer des appels externes ne doit pas être
raccordé à ce réseau de reproduction. L’exception Anthropic est désactivée par
défaut. Si l’envoi de justificatifs RECETTE est autorisé, l’option
`WAVY_RECETTE_ANTHROPIC_PROXY=true` dans `.env.recette` ajoute un réseau de transit
interne réservé à Factures API et au proxy. Le proxy seul rejoint son réseau
sortant. Il accepte uniquement les tunnels CONNECT de Factures API vers
`api.anthropic.com:443`, sans terminaison TLS ni journal d’accès. Les appels
HTTPS aux services Wavy utilisent les exclusions JVM. La livraison reste
`./wavy install recette` et utilise la configuration Compose de la VM.

Les migrations Flyway, initialisations SQL et bootstrap sont désactivés pendant
la reproduction ; Hibernate valide les schémas restaurés. Le mode reste actif
lors des redémarrages/recréations ordinaires. Pendant les restaurations et les
contrôles, les 18 conteneurs restent sans redémarrage automatique ; les bases
continuent de tourner pendant la restauration. Après validation complète,
les 18 politiques passent à `unless-stopped`, sans recréation des services.
Le même état `complete` produit les mêmes réseaux, ports privés, sysctls et
protections lors des futurs passages par Compose. Un échec garde ou rétablit
les protections ; le rollback restaure aussi les politiques des bases capturées
avant la copie. Une politique d'isolation absente après succès bloque Compose.
La politique n'est jamais supprimée automatiquement après succès : RECETTE
contient toujours des données PREPROD. Sa levée requiert une intervention dédiée.

Les scripts existants de sauvegarde restent utilisables, mais le backup standard
hors `sync` n'acquiert pas automatiquement ce nouveau périmètre Contrats. Le
secours de synchronisation est un lot spécifique complet.

## Application ciblée du correctif HTTPS après une copie déjà réussie

À effectuer seulement après autorisation de publication et d'intervention RECETTE.
Ne pas relancer `sync`, ne pas utiliser `install` et ne pas intervenir sur PREPROD.
Sous le verrou RECETTE existant, vérifier la phase `complete`, les deux réseaux
existants et relever les IDs, dates de démarrage et politiques des 17 autres
conteneurs. Utiliser le même moteur Compose, avec une cible unique :

```bash
python3 -B scripts/release_images.py up -d --no-deps --force-recreate --pull never wavy-erp-shell-recette
```

Le processus d'application doit conserver le verrou pendant la recréation et les
contrôles. Seul le Shell est recréé, avec l'image épinglée déjà présente. Vérifier
sa frontière réseau et Nginx, l'entrée HTTP locale, puis HTTPS depuis Windows via
Caddy existant (TLS normal, sans `-k`). Comparer les 17 autres conteneurs aux
relevés pour confirmer qu'ils n'ont été ni modifiés ni redémarrés. Aucun dump,
restore, changement de volumes ou migration n'est nécessaire.

L'activation immédiate du redémarrage automatique des 17 autres conteneurs déjà
présents exige une mise à jour de leurs politiques Docker, sans recréation ni
redémarrage. Cette modification de métadonnées est distincte de l'application
strictement limitée au Shell et doit être incluse explicitement dans l'accord.
Sans elle, leurs anciennes politiques `no` restent en place ; un simple reboot
ne peut pas les convertir automatiquement en `unless-stopped`. Les futures
synchronisations complètes et validées activent les 18 politiques automatiquement.

## Échecs et reprise

L'état durable est `deployments/recette-sync.json`, privé et ignoré par Git.
En cas d'échec, `failure.check` et `failure.code` sont enregistrés avant le retour
arrière et conservés avec la phase finale `rolled-back` ou `recovery-failed`.
Aucune sortie brute, réponse métier ni valeur de secret n'est ajoutée au journal.
Si l'écriture du diagnostic échoue, le retour arrière est quand même tenté.
Le secours est `backups/sync/<date UTC>/recette.tar.enc`, avec son manifeste HMAC ;
le sous-dossier `source/` conserve le lot source chiffré. Les fichiers temporaires
déchiffrés restent privés et sont supprimés à la sortie normale. Un arrêt brutal
peut laisser des temporaires privés à nettoyer après diagnostic. Aucun nettoyage
ou expiration automatique de ces lots n'est ajouté.

- Avant remplacement : aucun contenu métier RECETTE n'est écrasé. Une erreur du
  backup peut laisser des services arrêtés ou un lot clair incomplet, privé ;
  vérifier l'arrêt propre avant toute reprise opérateur.
- Après début du remplacement : le secours est revérifié/déchiffré avant toute
  restauration. Tous les writers sont arrêtés proprement ; bases, documents,
  manifestes et ancienne politique sont restaurés ensemble. Les anciennes images
  sont redémarrées via le même Compose et leur santé est contrôlée.
- Arrêt forcé d'un writer, secours invalide ou rollback échoué : maintien en
  maintenance ; aucun succès n'est annoncé. L'état durable bloque les nouvelles
  recréations Wavy tant que la reprise n'est pas terminée.
- Après interruption, **relancer la même commande** retente d'abord le rollback
  si un secours a été validé, puis termine sans lancer une nouvelle copie. Une
  autre invocation pourra ensuite lancer une nouvelle synchronisation. Sans
  secours validé, une intervention opérateur est exigée ; ne pas effacer l'état
  avant d'avoir vérifié que les données sont intactes et les writers sûrs.

Un échec reste un code de sortie non nul même si le rollback réussit. Les erreurs
distantes indiquent une phase connue et des codes numériques, sans restituer
les sorties brutes, par exemple
`phase=preprod-resume, code=1, ssh_code=1`.

Il n'existe pas de transaction distribuée : la sûreté repose sur l'arrêt des writers, le
secours complet et le maintien en maintenance en cas d'incertitude. Un `SIGKILL`
ou une panne machine ne peuvent pas déclencher un rollback dans le processus
mort ; l'état durable permet la reprise à l'invocation suivante.

## Validation locale sans données réelles

```bash
python3 -B scripts/test-sync-recette.py
python3 -B scripts/test-release-images.py
python3 -B scripts/test-recette-pwa-nginx.py
python3 -B scripts/test-preprod-backup-transition.py
bash -n wavy scripts/backup-db.sh
```

Les tests de synchronisation utilisent des fixtures, Docker/SSH simulés, le rendu
Compose sans daemon et le chiffrement réel de données synthétiques. Ils ne
qualifient pas une synchronisation réelle ni le filtrage réseau des VM. Une
qualification sur environnement jetable reste nécessaire avant première
utilisation sur les données métier ; elle n'est pas exécutée par ces tests.

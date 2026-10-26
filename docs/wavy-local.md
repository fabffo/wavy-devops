# Wavy quotidien sur MSI

La RECETTE locale est maintenant un environnement permanent : **https://recettelocal.wavyservices.fr**. Connexion habituelle depuis Chrome, puis lien **Wavy PWA** dans le tableau de bord pour les rôles `NOTE_DE_FRAIS` ou `SUPER_NOTE_DE_FRAIS`.

```bash
./wavy local up                         # tous les modules, PWA comprise
./wavy local up pwa                     # PWA + dépendances indispensables
./wavy local up pwa --build-frontends   # reconstruire et activer Shell/PWA locaux
./wavy local up tiers factures          # sélection multiple
./wavy local status
./wavy local logs factures --tail 100
./wavy local test                       # santé et HTTPS, sans écriture métier
./wavy local test pwa --chrome          # contrôle Chrome avec compte de test déjà configuré
./wavy local restart pwa
./wavy local down pwa                   # conserve les dépendances utilisées ailleurs
./wavy local down                       # arrête toutes les applications ; bases conservées actives
./wavy local down --databases           # arrête aussi les bases inutilisées, sans suppression
./wavy local down --dry-run
```

Aucun `pwa-open`, `pwa-close`, bail de 15 minutes, fichier d’autorisation ou réservation de release n’est nécessaire. Les sessions d’authentification conservent leur expiration applicative normale. Les services restent actifs après les tests. Aucun nettoyage métier ou retour à une ancienne image n’est exécuté automatiquement.

Les commandes historiques, par exemple `./wavy start local`, conservent leur sens SOURCE. Pour cette RECETTE HTTPS permanente, utiliser la syntaxe `./wavy local …`. Les anciennes commandes mutantes visant le même projet RECETTE sont bloquées pour éviter d’écraser sa configuration HTTPS.

## Données et documents

Les cinq bases existantes sont réutilisées, sans reset ni suppression de volume. Les justificatifs sont dans le volume Docker privé `wavy-recettelocal-justificatifs`, monté uniquement dans Factures sur `/app/justificatifs`, accessible au compte non privilégié de l’application. Une configuration documentaire existante n’est pas remplacée silencieusement. Les arrêts/redémarrages conservent les données ; les suppressions demandées dans l’application suivent ses règles métier habituelles.

Les écritures Notes, JPEG/PNG/PDF et extraction IA passent par les API existantes. Leurs contrôles restent actifs : rôles, société courante, tenant, propriétaire, validation des fichiers et limite documentaire de 10 Mio. Les bénéficiaires/porteurs requis doivent être renseignés selon le parcours métier : le mode local ne crée pas automatiquement leurs fiches ou associations.

La configuration IA de `.env.recette` est réutilisée sans afficher la clé ; un appel réel peut être facturé. Modifier cette configuration puis exécuter `./wavy local up pwa` applique les paramètres à Factures. La création **automatique** de facture achat reste désactivée ; aucun appel IA n’a été lancé par la conversion.

## Configuration et limites locales

Le point d’entrée reste `./wavy`. Il réutilise les Compose, images par digest et graphe de dépendances existants. La configuration effective privée est dans `~/.local/state/wavy/recettelocal`, sans modifier les manifestes actifs. Les fichiers `.env.recette` et de versions restent les sources de configuration. Les images doivent être disponibles localement : pas de rebuild/pull implicite. Les schémas existants sont validés, pas recréés.

Le profil permanent exige WSL MSI, un moteur Docker local, le projet `wavy-recette` et le seul domaine `recettelocal.wavyservices.fr`. Ses générateurs refusent les domaines RECETTE distante, PREPROD et production. Le manifeste public décrit seulement la disponibilité du module, afin que le lien apparaisse dès la connexion sans rechargement. Le tableau de bord vérifie les rôles ; l’accès effectif à la PWA est autorisé par l’API Notes elle-même. Le proxy conserve CORS, les cookies sécurisés et l’authentification, sans session locale spéciale. Les blocs Caddy distants sont comparés avant toute activation et restent inchangés. Les protections renforcées de déploiement distant restent en place.

Les anciennes preuves et sauvegardes de la session temporaire sont conservées. Son ancienne commande `fermer.sh` refuse désormais de restaurer cette session convertie : utiliser `./wavy local down`.

## Vérification

Le démarrage complet, `up pwa` et le parcours réel Chrome ont été exécutés. Les tests automatiques ne créent aucune donnée métier ; la qualification complète création/modification/validation/suppression/import/IA n’est pas déclarée exécutée. L’environnement reste disponible pour ces essais manuels, sans demande d’autorisation supplémentaire à chaque opération locale.

Les commandes `./wavy promotion-plan recette` et `./wavy promotion-plan preprod` restent des préparations locales sans accès VM. Elles n’activent jamais le profil permanent sur un environnement distant.

## Mobile PWA dans le Shell ERP

Le bouton **Mobile PWA**, dans le menu et les accès rapides, ouvre désormais la même application dans la zone de travail ERP. Le Shell conserve sa barre latérale et ses mécanismes `open`, URL `/module?module=pwa&path=…`, iframe et fil d’Ariane. Les routes du contenu restent sous `/pwa/` ; les déplacements internes synchronisent l’URL du Shell et un rechargement restaure le bon écran. Les changements de société sont relus auprès de Socle, dans les deux sens, sans accepter une identité fournie par message navigateur.

L’accès direct **https://recettelocal.wavyservices.fr/pwa/notes-frais** reste autonome en format mobile. Il s’agit du même build, du même manifeste et de la même session. Le service worker est limité à `/pwa/`, ses navigations aussi ; il ne contrôle pas le Shell, les modules ERP ou les API. L’iframe autorise la caméra de même origine ; les contrôles existants des imports et de l’extraction IA restent inchangés.

Après modification des sources frontales :

```bash
./wavy local up pwa --build-frontends
./wavy local test pwa --chrome
```

Les builds de production des fronts sont montés en lecture seule depuis le dossier privé local `frontend-builds`. Ils restent actifs lors des prochains `up` sans rebuild implicite. Les images API et les manifestes actifs ne changent pas. Ces montages sont propres au profil MSI ; ils ne sont pas inclus dans les plans de promotion d’images distantes. Une éventuelle publication nécessitera des images intégrant ces sources, dans le processus existant.

Les tests Chrome utilisent les API réelles sans écriture métier et ouvrent une fenêtre isolée. Ils vérifient les deux boutons, les routes internes, le rechargement, les sociétés dans les deux sens, Factures, le format mobile, le manifeste et le service worker. Chrome signale seulement `in-incognito` pour l’installation dans cette fenêtre isolée : l’installation réelle et la prise de vue sur appareil physique ne sont pas déclarées testées. Les tests ne déposent aucun fichier et n’appellent pas le fournisseur IA.

Qualification de cette intégration : 22 tests unitaires Shell, 55 PWA, 25 DevOps, 27 assertions Chrome HTTPS réelles et 4 scénarios navigateur simulés réussis. Les empreintes des 58 tables actuelles sont stables pendant les contrôles finaux. Rapport : `preparation/https-msi/MOBILE-PWA-INTEGRATION-RESULTATS.json`.

## Largeur et captures responsive

Le Shell occupe le viewport ; la zone de travail utilise la largeur restante après le menu, dont les dimensions sont conservées. Le tableau de bord dispose de marges de 24 à 32 px, d’une grille KPI à quatre ou deux colonnes selon l’écran et de panneaux qui se réorganisent en tablette. Les modules remplissent leur iframe, avec des marges internes de 24 px ; les tables larges défilent dans leur propre conteneur. La PWA autonome garde son gabarit mobile ; seule sa présentation intégrée s’élargit.

```bash
./wavy local test --layout before       # état courant avant une future modification
./wavy local up --build-frontends       # compiler/activer les six fronts concernés
./wavy local test --layout after        # mesures et captures à 1366×768, 1600×900 et 1920×1080
./wavy local test pwa --chrome           # navigation et non-régression
```

Les builds locaux reprennent dans une copie privée les URL relatives déjà utilisées par les Dockerfiles Contrats, Factures et Trésorerie. Les fichiers d’environnement sources, API et manifestes actifs ne sont pas modifiés. Ces commandes ne restaurent pas d’ancienne version et ne nettoient aucune donnée métier. Les captures de test masquent les coordonnées du compte dans le Shell et sont conservées dans le dossier privé local.

Rapport des 35 vues validées : `preparation/https-msi/LAYOUT-LOCAL-RESULTATS.json`. Comparatif visuel interactif : `~/.local/state/wavy/recettelocal/layout-review/index.html`. Le Shell était déjà plein écran lors de la mesure initiale ; les plafonds PWA (640 px) et Factures (1480 px) ainsi que les débordements de tables ont été corrigés. Les API n’ont pas redémarré pendant ces travaux.

## Surface complète sous l’en-tête

La correction suivante prolonge la mise en largeur jusqu’aux conteneurs Angular routés. Le minimum `calc(100vh - 57px)` conservé alors que le bandeau autonome était masqué a été supprimé. Les racines des modules ancrent leur document à son propre viewport ; `app-root`, `.app-main` et l’hôte routé transmettent la place disponible par flex, avec `min-width:0` et `min-height:0`. Les pages en grille alignent leurs pistes au début pour ne pas étirer les composants métier. Une page longue garde un défilement documentaire dans son iframe ; le Shell ne lui ajoute pas de barre verticale. Le menu défile indépendamment.

Le Shell conserve un seul ancrage à `100dvh`. Son iframe grandit par flex plutôt que par une cascade de `height:100%` ou une soustraction d’en-têtes. En 1920×1080, Trésorerie occupe désormais les 954 px disponibles : son conteneur principal mesurait 897 px et son hôte routé 731 px avant correction. Les espaces naturels des pages courtes restent à l’intérieur du module.

Validation : 21 vues avant/après (7 vues × 3 résolutions exactes), limites racines et hôtes routés mesurées, puis 27 contrôles de navigation réels réussis. Le rapport `preparation/https-msi/SURFACE-LOCAL-RESULTATS.json` et le comparatif `~/.local/state/wavy/recettelocal/surface-review/index.html` conservent les preuves. Les limites des conteneurs peuvent être superposées aux captures originales dans le comparatif.

Le menu interactif accessible avec `./wavy` réutilise ces commandes. Voir [le guide du menu](wavy-menu.md) pour la sélection multiple, les aperçus et les limites des capacités distantes et de sauvegarde/restauration.

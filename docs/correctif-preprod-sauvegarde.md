# Correction du faux refus documentaire sur une tentative PWA abandonnée

## Cause confirmée sur PREPROD

Le contrôle ciblé autorisé en lecture seule a confirmé :

- État PWA présent, phase `abandoned`, `mutationStarted=false`.
- `previous` explicitement nul, `completed=[]`, `observed={}`.
- Aucune entrée `storagePreconditions` ni `backup` ; fichier privé accepté par le lecteur existant.
- Le volume attendu `wavy-preprod_documents-preprod` est bien monté dans Contrats sur `/app/data`.
- La racine est accessible (`0:0:755`) et le répertoire Contrats est présent, accessible et sans lien (`100:101:700`).
- `notes-frais` est absent, sans lien symbolique.

Il s'agit d'une tentative abandonnée avant instantané, provisionnement ou déploiement. L'absence de Notes est cohérente avec cet état. Le script de sauvegarde déclenche pourtant l'exigence d'un répertoire Notes sur la seule présence de `state.json`. C'est ce faux refus qui arrête l'installation.

Le code d'origine a été reproduit depuis `./wavy install preprod` sur MSI : Compose réussit, puis le test `test -d /documents/notes-frais` retourne 1, sans sortie, avant le premier message de sauvegarde et avant son trap de nettoyage. `set -e` arrête le script ; le code 1 traverse correctement les wrappers Python et le trap de release, sans contextualisation. Aucune image n'est remplacée et les services restent démarrés. L'hypothèse `exec` est écartée.

## Correction ciblée

`backup-preprod.sh` lit l'état avec le lecteur privé déjà existant. L'absence de Notes n'est admise que si **toutes** les conditions observées sont explicites : abandon, aucune mutation, aucun instantané, listes et observations vides, aucune préparation de stockage et aucune sauvegarde. Tout état engagé, modifié, partiel, ambigu ou illisible conserve le contrôle strict d'origine.

Même dans ce cas d'abandon, la racine doit être accessible et un objet Notes existant doit être un répertoire réel : un lien, même cassé, ou un fichier inattendu est refusé. Un répertoire présent reste inclus dans l'archive et soumis aux contrôles d'intégrité habituels. Aucun dossier n'est créé et aucun état historique n'est effacé.

Un échec documentaire affiche le code et la politique effective. `release-preprod.sh` précise le composant dont la sauvegarde échoue et conserve le code original jusqu'à la CLI. Le cache et le remplacement de son image restent après la sauvegarde réussie.

Deux scripts de production seulement sont modifiés. Aucun changement des verrous, du wrapper Python, de Compose, des images ou digests, des migrations, du chiffrement, des signatures, de la rétention, des contrôles Nginx/health/smoke ou des protections des états PWA préparés et actifs. Aucun nouveau mode de livraison ni instrumentation installée.

## Vérification MSI

Le test de non-régression `scripts/test-preprod-backup-transition.py` restaure dans une fixture les deux fragments d'origine de `3ecf3c9` pour reproduire le refus silencieux. Il ne dépend pas de l'accès à un ancien commit en CI.

Il vérifie les cas suivants :

- Reproduction du faux blocage original avec l'état abandonné constaté.
- Refus explicite pour un état préparé dont le stockage manque ; refus des états abandonnés présentant une trace de mutation, d'instantané, de préparation de stockage ou de sauvegarde.
- Refus d'un lien ou d'un fichier à la place de Notes, même pour un abandon sans mutation.
- Sauvegarde normale d'un état préparé avec un répertoire Notes conforme.
- Propagation d'un code 125 d'utilitaire jusqu'à `./wavy install preprod`.
- Cycle complet des 13 composants, dans l'ordre, avec l'état abandonné et Notes absent : l'état reste inchangé et aucun répertoire Notes n'est créé.

Les scripts d'installation, sauvegarde, chiffrement, validation d'archive, signature, Nginx, health et smoke sont réels. Docker, PostgreSQL et HTTP sont simulés dans une fixture isolée ; le Docker natif n'est utilisé que pour `compose config`, en lecture seule. Le cycle couvre 65 dumps fictifs chiffrés, 13 archives documentaires validées, 13 lots signés et 13 succès de déploiement de fixture. Ce test vérifie l'orchestration et ne constitue pas une nouvelle qualification fonctionnelle des applications.

Résultat : **27 tests réussis** — 8 tests ciblés de transition/sauvegarde (196,7 secondes), 12 tests existants de garde-fous et 7 tests existants Nginx/release. Syntaxe Bash et espaces vérifiés. Le cycle de fixture des 13 composants aboutit sans créer Notes ni modifier l’état abandonné.

## Périmètre distant et suite

Les vérifications distantes n'ont utilisé que les métadonnées de l'état, l'inspection du montage et des commandes `test`/`stat` dans le conteneur Contrats existant. Aucun contenu documentaire ou secret n'a été affiché. Aucun conteneur existant, volume, base, image ou configuration PREPROD n'a été modifié. Aucun arrêt de service, sauvegarde ou déploiement n'a été lancé.

L'action minimale est de publier ce correctif DevOps après accord, puis de reprendre le parcours habituel `git pull --ff-only` et `./wavy install preprod` après autorisation de l'installation. Aucune création manuelle de stockage ou suppression de `state.json` n'est nécessaire pour le cas constaté. Aucun commit ni push effectué pendant cette préparation ; historiques et stash conservés.

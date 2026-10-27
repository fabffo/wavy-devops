# Publication PWA RECETTE permanente — 27 octobre 2026

## Commits publiés et image

- Gateway, branche `master` : `3ff5c3b86d49c030ee9abde2471b9dc5664b4814`.
- DevOps, préparation et contrôles, branche `master` : `994dcc1621c8d150f27149c34ec5746211efed72`.
- Le commit de suivi contenant ce rapport épingle l'image dans les deux manifestes.

Image publiée depuis un dépôt Gateway propre et le script de build standard MSI :

```text
ghcr.io/fabffo/wavy-gateway:0.1.0-3ff5c3b@sha256:6bb0ff5ea147fd5b51a6dbb00f8333d84220b6160696a64186f53f512b53587e
```

Le tag était absent de GHCR avant le push. Le digest du manifeste distant,
le RepoDigest et le téléchargement par référence immuable concordent.
Le digest de configuration du manifeste correspond à l'image candidate construite :
`sha256:5910e5eca206358c27b632794a22a54fdfb283f6d58ce0c444b5c150bd35e573`.
Cet Image ID local n'est pas utilisé comme digest de manifeste.

Labels OCI : version `0.1.0`, révision `3ff5c3b`, source
`https://github.com/fabffo/wavy-gateway`. Plateforme : `linux/amd64`.

Seuls `GATEWAY_VERSION` et `GATEWAY_DIGEST` changent dans RECETTE et PREPROD.
Les douze autres versions et digests sont strictement inchangés. Le modèle de
qualification RECETTE référence la nouvelle image, tout en conservant
`approved=false`, tous les contrôles à false et aucune preuve fabriquée.

## Protections et absence d'activation

Les nouvelles autorisations Notes/Tiers Gateway sont conditionnées au profil
RECETTE et excluent explicitement PREPROD et production, même en profils mixtes.
La nouvelle image référencée en PREPROD ne change ni cette exclusion, ni ses
profils, ni son orchestrateur, ses réservations, ses contrôles ou son activation PWA.
Les fichiers de configuration et d'orchestration PREPROD sont inchangés.

Les paramètres d'exemple restent `WAVY_PWA_ENABLED=false` et
`WAVY_NOTES_WRITES_ENABLED=false`. Les paramètres machine existants ne sont pas
modifiés. Aucune configuration n'a été montée sur un service opérationnel.

Aucun accès VM, déploiement, activation PWA ou écriture dans les bases, volumes
et documents existants n'a été effectué. Aucun historique de déploiement validé
n'a été ajouté : une publication ne prouve pas l'exécution sur la cible.
Les sauvegardes/restaurations des tests utilisent exclusivement leurs fixtures.

## Vérifications

- 159 tests Gateway réussis, dont droits RECETTE, refus PREPROD/profils mixtes,
  authentification, contexte, CORS et TLS local ; relancés par le build standard.
- 149 tests Python réussis avec les nouveaux manifestes : politiques PWA, lots
  documentaires, verrous, rollback, 13 images immuables, configuration CORS,
  contrôles PREPROD et commandes historiques.
- 26 contrôles réussis sur l’image publiée : 13 en RECETTE et 13 en
  PREPROD/secure ; les nouveaux accès NOTE_DE_FRAIS restent refusés en PREPROD.
- Nginx réel et restauration des cinq dumps/documents testés uniquement dans
  des conteneurs et volumes jetables ; les fixtures ont été supprimées.
- Historique des versions, syntaxe Bash et `git diff --check` validés.
- Périmètres de commit explicites : aucun dotenv privé, secret, cache, backup,
  fichier temporaire ou historique runtime inclus.

Le contrôle additionnel de l'image publiée utilise un backend synthétique dans
un conteneur sans réseau, port publié ou volume métier. Le client HTTP de test
attend la fin du démarrage Spring et conserve la connexion jusqu'à la réponse
asynchrone. Ces contrôles ne constituent pas une connexion Socle réelle ni une
qualification des droits sur les données RECETTE.

## GO / NO-GO

**GO publication** : sources et image publiées, digest distant vérifié, manifeste
RECETTE et PREPROD cohérents, protections PREPROD conservées.

**NO-GO activation RECETTE** : il reste à autoriser et qualifier sur la cible le
stockage privé, les permissions, les accès directs, le lot réellement restauré,
les comptes/porteurs, l'isolation tenant/société et les parcours ERP/smartphone.
La publication n'active rien et n'autorise pas un déploiement.

Le diagnostic `./wavy pwa recette check` et ses options `--plan`, `--runtime` et
`--backup-dir` centralisent ces étapes. Voir le
[dossier de qualification](pwa-recette-qualification.md). Le fonctionnement
permanent, une fois autorisé et qualifié, ne dépend d'aucun bail temporaire et
ne déclenche pas de fermeture ou nettoyage automatique des données existantes.

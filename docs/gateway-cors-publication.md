# Correctif CORS HTTPS Gateway — préparation MSI

## Résultat

Le profil Gateway `recette` ignorait `WAVY_CORS_ALLOWED_ORIGIN_PATTERNS` :
il fixait les origines localhost et vidait les patterns. L'ancien test HTTPS
surchargeait la map Spring directement, masquant ce défaut. Sans cette surcharge,
le défaut est reproduit : OPTIONS 403 au lieu de 200, POST 403 au lieu du 401
retourné par le backend synthétique.

Le profil corrigé lit la variable commune, comme PREPROD, sans changer les routes,
le filtre d'authentification ou les contrôles des backends. Les valeurs explicites
remplacent les origines localhost de repli. Les propriétés Spring explicites
(JSON applicatif, ligne de commande) gardent leur priorité normale.

DevOps transmet la même variable aux cinq APIs et à Gateway. Le paramètre
spécifique Gateway a été retiré du manifeste de versions. La référence RECETTE
inclut l'origine HTTPS et les sept ports localhost historiques, sans wildcard.
Le lanceur historique `start-docker-recette.sh` rejoint `./wavy start recette` :
plus de build Maven/Docker indépendant et même configuration effective.
PREPROD conserve son validateur, son origine unique, ses verrous et son
orchestrateur de release.

## Qualification

- Gateway : 81 tests Maven réussis, dont 13 en TLS réel sur loopback avec un
  certificat éphémère explicitement approuvé ; aucun trust-all.
- Les profils RECETTE et PREPROD couvrent les origines autorisées/interdites,
  OPTIONS, POST, les en-têtes et méthodes interdits, l'authentification du backend
  synthétique, les cookies Secure et la reconstruction du contexte authentifié.
- Les refus de mutation de session du backend sont transmis sans modification.
- Image empaquetée : 8 préflights vérifiés dans des conteneurs jetables
  RECETTE/PREPROD sans réseau, ports publiés ou volumes ; conteneurs supprimés.
- DevOps : 111 tests Python réussis, tests d'historique et syntaxe Bash validés.
- Rendu Compose réel : les six backends reçoivent la même origine, le shell ne la
  remplace pas et les 13 images restent épinglées en `version@sha256`.

Ces vérifications ne sont pas une connexion réelle à Socle sur les données
RECETTE/PREPROD, ni un test de la terminaison TLS Windows. Aucun accès aux VMs,
aucun déploiement et aucune modification des données existantes.

## Candidat local, non publié

- Dépôt source : `wavy-gateway`, commit `38330ce`.
- Image locale : `ghcr.io/fabffo/wavy-gateway:0.1.0-38330ce`.
- Plateforme : `linux/amd64` ; taille : 233787481 octets.
- Image ID local : `sha256:c5c6823c3a603f5ab2de864c2d9954c45cae32f7e232636f04d0d07d65f90427`.
- Labels OCI : version `0.1.0`, révision `38330ce`, source
  `https://github.com/fabffo/wavy-gateway`.

L'Image ID local n'est pas un digest de manifeste GHCR. Les manifestes actifs
RECETTE/PREPROD conservent leurs versions et digests publiés actuels.

## Publication proposée après validation

1. Publier les commits locaux Gateway et DevOps sur leurs branches `master`.
2. Vérifier les labels du candidat, l'authentification GHCR et l'absence du tag
   distant. Toute erreur d'accès ou tag existant bloque la publication immuable.
3. Pousser l'image candidate déjà construite, sans reconstruire ni remplacer un
   tag existant. Le script de build refuse de reconstruire un tag local existant :
   il ne faut pas le relancer avec `--push` sur ce candidat déjà construit.
4. Relever et vérifier le vrai digest de manifeste publié, puis modifier seulement
   `GATEWAY_VERSION` et `GATEWAY_DIGEST` dans les deux environnements. Conserver
   les douze autres couples et le format final `version@sha256`.
5. Relancer les tests DevOps et publier ce commit de manifestes séparé.

Ces étapes de publication n'autorisent aucun déploiement. Une récupération Git
seule ne remplace pas l'image Gateway déjà en cours d'exécution. Le déploiement
RECETTE/PREPROD devra être autorisé séparément ; PREPROD passe obligatoirement
par l'orchestrateur sécurisé existant.

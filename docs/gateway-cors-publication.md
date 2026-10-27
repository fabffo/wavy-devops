# Correctif CORS HTTPS Gateway — publication MSI

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

## Publication du 27 octobre 2026

- Gateway publié sur `master` : `38330cef6a29a93e0056fe443807899499ea7ca4`.
- Configuration DevOps publiée sur `master` : `2916b66e94eac6a0d5d2277e08c457515b2e435d`.
- Image GHCR : `ghcr.io/fabffo/wavy-gateway:0.1.0-38330ce`.
- Digest distant vérifié : `sha256:68d421619b1020d45e7195b38e9aa4ad94bcfffbddd424b66eda7d182d39c217`.
- Référence immuable active RECETTE et PREPROD :
  `ghcr.io/fabffo/wavy-gateway:0.1.0-38330ce@sha256:68d421619b1020d45e7195b38e9aa4ad94bcfffbddd424b66eda7d182d39c217`.
- Plateforme : `linux/amd64` ; taille : 233787481 octets.
- Image ID local : `sha256:c5c6823c3a603f5ab2de864c2d9954c45cae32f7e232636f04d0d07d65f90427`.
- Labels OCI : version `0.1.0`, révision `38330ce`, source
  `https://github.com/fabffo/wavy-gateway`.

Le tag était absent de GHCR avant publication. L'image locale testée a été
poussée sans reconstruction. Le digest du manifeste distant concorde avec le
RepoDigest ; son digest de configuration correspond à l'Image ID testé. Le pull
par la référence immuable a réussi et conserve cet Image ID. L'Image ID local
n'a pas été utilisé comme digest de manifeste.

Seuls `GATEWAY_VERSION` et `GATEWAY_DIGEST` changent dans les deux environnements.
Les douze autres versions et digests sont strictement inchangés. Aucun historique
de déploiement validé n'est ajouté : publier une image ne prouve pas son exécution.
La configuration CORS de référence RECETTE autorise
`https://recette.wavyservices.fr` et respecte une valeur machine explicite ;
PREPROD conserve son origine propre et son validateur.

## Décision d'installation

GO technique pour une installation contrôlée de Gateway sur RECETTE distante :
image publiée et vérifiée, correctif CORS qualifié sur MSI, références immuables
et tests DevOps cohérents. Aucune qualification de session réelle sur les bases
distantes ni contrôle de l'état de la VM n'a été effectué.

Cette publication n'effectue et n'autorise aucun déploiement. Une récupération
Git seule ne remplace pas l'image Gateway en cours d'exécution. Le déploiement
RECETTE/PREPROD reste une étape distincte ; PREPROD passe obligatoirement par
l'orchestrateur sécurisé existant. Aucun accès VM ou changement de données.

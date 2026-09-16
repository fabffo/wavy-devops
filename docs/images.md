# Construction des images Wavy

## Build once, deploy many

Une image Wavy est testée et construite une seule fois depuis un commit Git
propre. Après publication dans GitHub Container Registry, cette même image doit
être utilisée en recette, préproduction puis production. Elle ne doit jamais
être reconstruite entre les environnements.

## Nommage et version

Le registre cible est `ghcr.io/fabffo`. Chaque dépôt produit une image portant
le même nom :

```text
ghcr.io/fabffo/wavy-<composant>:<version>-<sha_git_court>
```

Exemple :

```text
ghcr.io/fabffo/wavy-factures-api:2.5.0-a8f31c2
```

La version fonctionnelle est toujours fournie explicitement. Le script ajoute
le SHA court du commit courant. `latest` n'est jamais produit.

## Tag et digest

Le tag est un nom lisible associant version et commit. Le digest `sha256` est
l'identité cryptographique forte du manifeste publié. Deux déploiements qui
référencent le même digest utilisent exactement la même image.

Un tag GHCR existant est considéré comme immuable : le script refuse de le
remplacer. Si la vérification distante est ambiguë ou échoue, le push est refusé.

## Construction locale

```bash
./scripts/build-image.sh erp-shell 1.0.0
./scripts/build-image.sh factures-api 2.5.0
```

Le script vérifie le dépôt Git, exécute les tests, réalise le build applicatif,
construit l'image et affiche son identifiant et sa taille. Il ne pousse rien par
défaut.

Les backends exécutent leur suite Maven avec `mvn test` ou le wrapper Maven. Les
fronts exécutent `npm ci`, les tests Angular/Vitest non interactifs, puis un
build de production. Un échec interrompt la fabrication ; aucun test n'est
ignoré ou supprimé.

## Métadonnées OCI

Chaque image contient :

```text
org.opencontainers.image.revision=<sha Git>
org.opencontainers.image.version=<version fonctionnelle>
org.opencontainers.image.source=https://github.com/fabffo/wavy-<composant>
```

## Publication GHCR

Le push est une action explicite :

```bash
export GHCR_USERNAME=...
export GHCR_TOKEN=...
./scripts/build-image.sh factures-api 2.5.0 --push
```

Le token doit être fourni par l'environnement local ou, plus tard, par les
secrets GitHub Actions. Il ne doit jamais être écrit dans Git. Le script utilise
`docker login ghcr.io --password-stdin` et n'affiche pas le token.

Après authentification, `docker manifest inspect` vérifie le tag. Un manifeste
existant bloque l'écrasement. Seules les réponses explicites `manifest unknown`
ou `no such manifest` autorisent le push ; toute erreur ambiguë bloque également
par sécurité. Après le push, le digest distant est affiché.

## Contextes Docker

Les `.dockerignore` excluent au minimum les artefacts reconstruisibles et les
données locales : `node_modules`, `target`, `dist`, `.git`, `.angular`, rapports
de tests, fichiers IDE et `.env`. Le contexte doit contenir uniquement les
sources nécessaires au Dockerfile.

## Relation avec les manifests

Un build, même réussi, ne modifie jamais `versions/recette.env` ou
`versions/preprod.env`. Après un push réussi, le script affiche uniquement la
ligne suggérée, par exemple :

```text
FACTURES_API_VERSION=2.5.0-a8f31c2
```

L'enregistrement dans le manifest et la promotion restent des opérations
distinctes et contrôlées. RECETTE utilise déjà ses treize images GHCR. PREPROD reprend les images
validées et le Socle 0.1.0-6570deb spécifique au bootstrap, sans aucun rebuild.

## Contrôle PREPROD

Le tag distant doit exister ; après pull, le RepoDigest et les labels OCI
revision/version/source doivent correspondre. Le conteneur est ensuite créé
avec `repository@sha256:…` et son ID est contrôlé après health/smoke. Les preuves
locales et limites de compatibilité sont dans [la revue PREPROD](preprod-review.md).
L’ancien override de build PREPROD est neutralisé.

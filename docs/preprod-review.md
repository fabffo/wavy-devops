# Revue PREPROD — 14 septembre 2026

La [revue finale bloquante](preprod-final-review.md) complète cette analyse et
fait foi pour les décisions cookies, PWA et sauvegarde documentaire.

Revue locale sur MSI. Aucun contact avec la VM ; aucune image construite,
poussée ou tirée, aucun conteneur créé/démarré, aucune base/volume touché.
Les RepoDigests et labels OCI ont été vérifiés avec `docker image inspect`
uniquement. La disponibilité GHCR au moment du futur déploiement sera revérifiée
par `docker manifest inspect`, puis pull et contrôle RepoDigest/OCI. La revue
locale ne constitue pas une attestation actuelle de disponibilité distante.

## Inventaire des images autorisées

Socle : référence fournie par l’opérateur, puis recoupée avec le cache MSI.
Autres images : manifestes `versions/recette.env`, `versions/recette.digests`,
historiques RECETTE et cache MSI concordants. Chaque label source correspond à
`https://github.com/fabffo/wavy-<composant>`, version à `0.1.0`, revision au suffixe Git.

| Composant | Version | Digest vérifié localement |
|---|---|---|
| socle-api | 0.1.0-6570deb | `sha256:77c66ff49cbc14e6b4b1e91d0ce687b6e9dc0063b1f8c3055f9bc37c208c9662` |
| tiers-api | 0.1.0-7642a09 | `sha256:6c91e16bd3f5211c892273031f5ab1f1d56d6007e4003e0dd382fef845f2400e` |
| contrats-api | 0.1.0-527874b | `sha256:f60edb42690fa005748cdf6bbf9f2b9fdeb956ce3001c1e3ae0655dc2ad72ff0` |
| factures-api | 0.1.0-4e5a390 | `sha256:1a3b69ddd64ea2fc1cfbea53a63b17277b79bc8d49662d4252e48aea6047b48c` |
| tresorerie-api | 0.1.0-45fd268 | `sha256:e45d7063a3715d8dc370458960d6dcda7fa731582ceb902ea42e2f8b3dd33f56` |
| gateway | 0.1.0-98e2ced | `sha256:25279339824458d3247f05764fe48a8af3f892da4627fccac8dff58380d6c547` |
| socle-front | 0.1.0-d4c76c5 | `sha256:1d32cb2cc8cbb5c334800d6fa13df2dff9e1293988179f0df8138b77958fbdaa` |
| tiers-front | 0.1.0-5f5d1b5 | `sha256:5e6d0b47f49fbcb2f672b6fd2205adced03fab8cfbc7b3f3aee8b378ac68ac6a` |
| contrats-front | 0.1.0-de6e957 | `sha256:96c9b486c098e13d0aae5f3c6d1eee741d9b936db645c5ddc3f53141b4454273` |
| factures-front | 0.1.0-5547b5d | `sha256:f8029de5491bcbc1795d1d063582a4218ed512263bef502c4dad96e3a9b12045` |
| tresorerie-front | 0.1.0-4bda80b | `sha256:ed091c0e81700ddef21f1b37764ec3f13a5b70df0a5666189f2d3b3adb26bb2c` |
| pwa | 0.1.0-e8990f9 | `sha256:079f56c8c4a0ecdf74f5858922d69f718c20f4ddd378f56e63f2d3377757e950` |
| erp-shell | 0.1.0-5f08d59 | `sha256:a6b58c18e4340464a0afb046a7919a43012f7f838dcaa7a04593e39ad57b5099` |

PostgreSQL : `postgres:16-alpine`, RepoDigest local observé et épinglé :
`sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f`.
Ce digest concerne l’image tierce ; pas de labels OCI Wavy exigés.

## Compatibilité relue aux commits des images

Les dépôts applicatifs ont été lus avec `git show <revision>:<fichier>` et
n’ont pas été modifiés. Les fichiers de travail courants ne sont pas utilisés
comme preuve du contenu des versions publiées.

| API | Profil preprod explicite | Constat |
|---|---|---|
| Socle 6570deb | Oui, properties | Bootstrap configurable, secure, Flyway et health public ; curl installé |
| Tiers 7642a09 | **Non** | Base + secure ; datasource injectée, ddl validate ; garde-fous Flyway et URL Socle ajoutés dans Compose |
| Contrats 527874b | **Non** | Base + secure ; mêmes compensations Compose ; health public ; authentification déléguée au Socle |
| Factures 4e5a390 | Oui, properties | Flyway/validate, secure en Java ; URLs interservices injectées |
| Trésorerie 45fd268 | Oui, YAML | Flyway/validate et secure en Java ; URL Socle manquante corrigée |
| Gateway 98e2ced | Oui, properties | Routes injectées et CORS préprod ; application WebFlux |

Les cinq APIs et Gateway ont explicitement `preprod,secure`. Le socle commun
Compose force ddl validate, SQL init never, Flyway enabled/validate/clean-disabled,
health/info seuls, sans détails. Tiers et Contrats peuvent consommer ces valeurs
sans image nouvelle ; leur compatibilité complète reste à éprouver en runtime.

Le test TCP `/proc/net/tcp` prouvait seulement une écoute. Les modifications
HTTP déjà présentes à l’arrivée ont été conservées : `/actuator/health` public
avec curl pour Socle, wget BusyBox sur les images Alpine. Les Dockerfiles aux
commits publiés sont cohérents avec ces outils ; aucun conteneur n’a été exécuté
pour tester leur présence. Les healthchecks ne nécessitent aucun port API hôte.

## Interfaces et routes

Les Dockerfiles publiés de Tiers/Contrats/Trésorerie injectent une base API vide,
Factures `/api`, Socle passe par un template Nginx ; les mêmes images sont
réutilisables pour le montage sous ERP Shell. Les arguments réellement utilisés
lors d’un ancien build ne sont pas attestés par le seul Dockerfile : les bundles
et parcours navigateur doivent encore être validés dans l’environnement cible.
Les upstreams de modules ERP Shell ont reçu le `/` final pour retirer le préfixe
`/modules/<nom>/` lors du proxy ; le filtre envsubst limite le remplacement aux
variables `_UPSTREAM`, sans substituer les variables internes Nginx.

PWA reste sur le réseau interne : l’ERP Shell 5f08d59 n’a pas de route `/pwa/`.
Son healthcheck et son déploiement sont disponibles, mais **aucun accès navigateur
PWA via le seul point d’entrée** n’est fourni dans cette version. Une intégration
PWA et une validation de son bundle sont à prévoir ; aucun port supplémentaire
n’est ouvert pour contourner cette limite.

## Décisions de la revue finale

Les profils Tiers/Contrats sont compatibles par configuration générique + secure
et valeurs Compose ; l’absence de fichier preprod n’est pas un blocage.
OpenAPI/Swagger sont désormais désactivés explicitement dans Compose. Le mode
tunnel temporaire impose Cookie Secure=false ; le mode HTTPS impose true.
Le cookie applicatif est émis par Socle, le Gateway transmet l’authentification.

Le volume documents est maintenant réservé à Contrats, préparé avec UID/GID
100:101 et inclus dans les lots chiffrés/authentifiés format 2. La restauration
exige --with-documents. Voir le guide pour la fenêtre de maintenance et les
limites de transaction globale. Le bundle PWA publié contient effectivement
apiBaseUrl="/api" ; la PWA reste optionnelle et sans accès public au premier jalon.

Le proxy HTTPS externe, son domaine et son certificat restent à installer lors
de la sortie du mode HTTP temporaire. SMTP reste hors premier jalon. Les tests
métier sur VM et navigateur demeurent une étape de déploiement, pas une preuve
fabriquée pour autoriser le commit DevOps. Aucun dépôt applicatif modifié.

# Audit transversal des dépendances PREPROD

Audit statique du 20 septembre 2026. Périmètre : les six dépôts Java frères du MSI et `docker-compose.preprod.yml`. Aucun déploiement, accès aux bases ou changement de données. Le fichier machine `.env.preprod` n'est pas présent dans ce checkout ; l'état des valeurs actives est celui communiqué dans la demande, et non une nouvelle mesure runtime.

Constats runtime transmis par l'équipe PREPROD avant cet audit : Socle et Tiers healthy après correction manuelle du couple technique, healthcheck 6/6 et création utilisateur réussie. Ils n'ont pas été reproduits pendant cet audit. Les tests applicatifs cités plus bas sont des tests locaux ciblés ; les autres parcours runtime du plan de smoke restent à exécuter.

## A. Matrice des appels

Les URL ci-dessous sont celles du Compose PREPROD. « Session » signifie propagation du Cookie ou de l'Authorization de la requête entrante, avec validation du profil par le destinataire auprès du Socle. Les en-têtes `X-Tenant-Id`, `X-Utilisateur-Id` et `X-Societe-Courante-Id` accompagnent les appels métier. Ils ne constituent pas à eux seuls une authentification.

| Source | Destination | Fonction | URL / variable | Auth | Obligatoire |
|---|---|---|---|---|---|
| Socle | Tiers | Recherche, lecture et création de personne lors de l'association utilisateur | `http://wavy-tiers-api-preprod:8081` / `WAVY_TIERS_API_URL` | Basic technique ; `WAVY_TIERS_SERVICE_USERNAME`, `WAVY_TIERS_SERVICE_PASSWORD` identiques aux deux extrémités | Oui pour l'association/création utilisateur |
| Tiers | Socle | Validation du profil | `http://wavy-socle-api-preprod:8080` / `WAVY_SOCLE_API_URL` | Cookie ou Authorization entrants | Oui pour les endpoints protégés |
| Contrats | Socle | Validation du profil | idem / `WAVY_SOCLE_API_URL` | Cookie ou Authorization entrants | Oui pour les endpoints protégés |
| Factures | Socle | Validation profil, compteurs | idem / `WAVY_SOCLE_API_URL` | Session ou Authorization propagée, contexte | Oui pour les endpoints protégés et la numérotation |
| Factures | Tiers | Fournisseurs, salariés, dashboard | `http://wavy-tiers-api-preprod:8081` / `WAVY_TIERS_API_URL` | Session ou Authorization propagée, contexte | Selon fonctionnalité |
| Factures | Contrats | Budgets, références de contrats | `http://wavy-contrats-api-preprod:8082` / `WAVY_CONTRATS_API_URL` | Session ou Authorization propagée, contexte | Selon fonctionnalité |
| Trésorerie | Socle | Validation du profil | `http://wavy-socle-api-preprod:8080` / `WAVY_SOCLE_API_URL` | Cookie ou Authorization entrants | Oui pour les endpoints protégés |
| Trésorerie | Factures | Rapprochement / lecture de factures | `http://wavy-factures-api-preprod:8083` / `WAVY_FACTURES_API_URL` | Session ou Authorization propagée, contexte | Selon fonctionnalité |
| Trésorerie | Tiers | Lecture de tiers | `http://wavy-tiers-api-preprod:8081` / `WAVY_TIERS_API_URL` | Session ou Authorization propagée, contexte | Selon fonctionnalité |
| Gateway | Socle, Tiers, Contrats, Factures, Trésorerie | Routage HTTP et validation du profil auprès du Socle | cinq `WAVY_*_API_URI/URL` et `WAVY_ROUTES_SOCLE_URI` | Cookie/Authorization ; filtre Gateway enrichit les en-têtes de contexte | Oui |
| Factures | Anthropic | Extraction IA de facture | URL du client Anthropic dans le code ; `WAVY_AI_API_KEY`, `WAVY_AI_MODEL` | Clé API | Seulement si la fonction IA est activée/configurée |

Contrats → Tiers n'a pas été trouvé dans les clients HTTP du dépôt. La création de références de tiers dans Contrats ne prouve donc pas un appel à Tiers. Socle → Tiers est le seul couple qui emploie les credentials techniques dédiés ; les autres appels utilisent l'identité de la requête. Le filtre Tiers limite cette identité technique aux GET `/api/tiers/personnes`, `/api/tiers/{id}` et POST `/api/tiers/personnes`.

Sources principales : `TiersApiClient`, `ContexteAuthentificationFilter` et `ProfilSocleClient` dans Socle/Tiers ; `HttpCompteurSocleClient`, `HttpTiersFournisseurClient`, `HttpTiersSalarieClient`, `HttpTiersDashboardClient`, `HttpContratsClient` dans Factures ; `HttpFacturesTresorerieClient`, `HttpTiersTresorerieClient` dans Trésorerie ; `AuthentificationGatewayFilter` et `application.properties` dans Gateway. Recherche effectuée sur `RestClient`, `RestTemplate`, `WebClient`, `Feign`, `HttpClient`, `URLConnection`, `@Value`, `@ConfigurationProperties`, `${...}` et `System.getenv` dans `src/main`.

## B. Variables obligatoires et couverture

« Oui » sous Exemple signifie que la clé est documentée, même si sa valeur est `CHANGE_ME`. Le validateur rejette tous les placeholders. Les URL codées dans Compose sont contrôlées par rendu Compose, les autres par la validation du dotenv.

| Composant | Variable / groupe | Compose | Exemple | Validateur | Obligation réelle | État |
|---|---|---|---|---|---|---|
| Socle + Tiers | `WAVY_TIERS_SERVICE_USERNAME`, `WAVY_TIERS_SERVICE_PASSWORD` | Oui, requis aux deux bouts | Oui | Oui, non vides, password ≥ 12, même valeur rendue | Création/association utilisateur ↔ personne Tiers | Corrigé |
| Cinq APIs | `WAVY_*_DB_NAME`, `WAVY_*_DB_USER/USERNAME`, `WAVY_*_DB_PASSWORD`, `SPRING_DATASOURCE_*` | Oui | Oui pour `WAVY_*` | Passwords requis/distincts ; rendu DB vérifié | Démarrage | OK |
| Cinq APIs | `SPRING_PROFILES_ACTIVE=preprod,secure`, Flyway, JPA validate, SQL init never | Oui | Sans objet | Oui | Démarrage sûr | OK |
| Cinq APIs + Gateway | `WAVY_CORS_ALLOWED_ORIGIN_PATTERNS`, `SERVER_SERVLET_SESSION_COOKIE_*` | Oui | Oui pour l'origine | Oui | Navigation authentifiée | OK |
| Socle | `WAVY_BOOTSTRAP_*` | Oui | Oui | Oui | Bootstrap initial / configuration de démarrage | OK ; même si bootstrap désactivé, contrat MSI actuel les exige |
| Gateway | `WAVY_SESSION_SECRET` | Oui | Oui | Oui, ≥ 32 | Contrat de configuration MSI ; aucune lecture explicite trouvée dans Gateway | OK côté MSI ; usage applicatif non démontré |
| Socle/Tiers/Contrats/Factures/Trésorerie/Gateway | Toutes les URL interservices de la matrice | Oui, valeurs internes fixes | Sans objet | Oui, hôte et port exacts | Fonctionnalités dépendantes | Corrigé : contrôle ajouté |
| MSI | `WAVY_PUBLIC_URL`, `WAVY_ACCESS_MODE`, `WAVY_COOKIE_SECURE`, `COMPOSE_PROJECT_NAME` | Oui / contrat machine | Oui | Oui | Accès tunnel/HTTPS et isolation | OK |
| MSI | `WAVY_BACKUP_ENCRYPTION_PASSPHRASE`, `WAVY_BACKUP_RETENTION_DAYS` | Hors APIs | Oui | Oui | Backup PREPROD | OK |

Les variables `SPRING_*` et `SERVER_*` de Compose fixent les profils, la source PostgreSQL, la session, Flyway, les ports et les contrôles de sécurité. Les applications ont des valeurs locales par défaut dans leurs fichiers de configuration ; le Compose PREPROD fournit explicitement les URL et la base, et le validateur vérifie le rendu. Aucun `System.getenv` direct supplémentaire n'a été relevé dans les sources Java principales examinées.

## C. Variables optionnelles / métier

| Variables | Rôle et condition |
|---|---|
| `WAVY_AI_PROVIDER`, `WAVY_AI_MODEL`, `WAVY_AI_API_KEY` | Extraction IA Factures ; `ExtractionIaProperties.configured()` demande clé et modèle. Vides acceptés tant que le parcours IA n'est pas utilisé. |
| `WAVY_AI_TIMEOUT_SECONDS`, `WAVY_AI_MAX_FILE_SIZE_MB`, `WAVY_AI_ACHAT_AUTO_CREATION_ENABLED`, `WAVY_AI_ACHAT_MINIMUM_CONFIDENCE` | Réglages IA métier ; valeurs par défaut dans Factures, explicités en RECETTE, absents de Compose PREPROD. |
| `WAVY_EMAIL_HOST`, `WAVY_EMAIL_PORT`, `WAVY_EMAIL_USERNAME`, `WAVY_EMAIL_PASSWORD`, `WAVY_LOG_LEVEL` | Présents dans l'exemple PREPROD, mais non injectés par Compose et aucune consommation `MAIL_*`/`WAVY_EMAIL_*` trouvée dans les six sources principales. Pas d'obligation runtime démontrée. |
| `WAVY_CONTRATS_STOCKAGE_PIECES_JOINTES` | Répertoire documentaire fixe `/app/data/contrats`, monté sur volume réservé à Contrats. Obligatoire pour les pièces jointes, contrôlé par MSI. |
| `WAVY_AUTH_FILTER_ENABLED`, `WAVY_GATEWAY_PORT`, `WAVY_*_API_PORT` | Valeurs applicatives par défaut ; Compose fixe le port serveur et laisse le filtre Gateway actif. |

Les modules exposent aussi des options locales de `WAVY_*_DB_HOST/PORT` et `SPRING_PROFILES_ACTIVE`; elles sont propres aux profils local/RECETTE. En PREPROD, `SPRING_DATASOURCE_*` et `SERVER_PORT` du Compose prennent la priorité. `@ConfigurationProperties` a été trouvé pour `wavy.securite` dans Socle et `wavy.ai` dans Factures ; aucun autre préfixe de ce type n'a été trouvé dans `src/main/java` des six dépôts.

## D. Secrets et comparaison RECETTE

Secrets requis : cinq mots de passe DB distincts, mot de passe bootstrap, secret de session MSI, passphrase de backup, mot de passe interservice Tiers. La clé IA est facultative. Les valeurs effectives de `.env.recette` ont été inspectées uniquement par noms de clés ; aucune n'est reproduite ici. RECETTE possède les clés du couple technique dans Compose et son exemple, ainsi que les réglages IA détaillés. PREPROD possède désormais le couple requis dans Compose et son exemple. Les ports hôte, profils et URL publiques RECETTE sont spécifiques à son architecture ; les recopier en PREPROD casserait l'isolation. Les secrets PREPROD doivent être distincts de RECETTE.

## E. Routes

| Route Gateway | Destination PREPROD |
|---|---|
| `/api/socle/compteurs`, `/api/socle/**`, compatibilité `/api/**` | Socle :8080 |
| `/api/tiers/**` | Tiers :8081 |
| `/api/contrats/**` | Contrats :8082 |
| `/api/factures/**`, `/api/devis/**`, `/api/abonnements/**`, `/api/salaires/**`, `/api/notes-frais/**`, `/api/budgets/**`, `/api/dashboard-financier/**` | Factures :8083 |
| `/api/tresorerie/**` | Trésorerie :8086 |

Les 13 définitions de route Gateway sont sans prédicat de méthode : GET, POST, PUT, PATCH et DELETE suivent la même destination. Le filtre Gateway traite OPTIONS séparément. Chaque URI est remplacée par la variable PREPROD du Compose ; le validateur rejette désormais `localhost`, RECETTE, mauvais hôte ou mauvais port dans toutes les dépendances configurées.

## F. CORS

Pour les six backends, le Compose injecte `WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=http://localhost:24443` en mode tunnel, et le validateur impose l'égalité à `WAVY_PUBLIC_URL`. Les cinq configurations de sécurité Servlet et la configuration WebFlux Gateway déclarent GET, POST, PUT, PATCH, DELETE, OPTIONS, `allowCredentials=true`, et `Set-Cookie` exposé. Aucun écart statique. Les OPTIONS POST Socle et Gateway ont été observés à 200 selon le contexte fourni ; les quatre autres preflights restent à vérifier en runtime après une mise à jour contrôlée.

## G. Parcours fonctionnels et risques

Le smoke actuel (`scripts/smoke-test.sh`) réalise six GET, dont deux healthchecks et un référentiel public. Il ne couvre ni création utilisateur → Tiers, ni appels Factures → Tiers/Contrats, ni Trésorerie → Factures/Tiers. Un healthcheck sain ne prouve donc pas ces parcours.

Plan de smoke fonctionnel complémentaire, à exécuter avec une session de test PREPROD dédiée et des identifiants non enregistrés dans Git :

1. Authentification Socle : login, lecture session/profil, sélection de société, logout ; vérifier tenant, société, utilisateur, rôles et cookie.
2. Lecture protégée par Gateway de chaque module avec la même session : Socle tenant/société/utilisateur/rôles/compteurs ; Tiers personnes physiques/morales, clients/fournisseurs/contacts/référentiels ; Contrats clients/fournisseurs/références/pièces jointes ; Factures ventes/achats/numérotation ; Trésorerie comptes/imports/opérations/rapprochements.
3. Déclencher, sur des données de test préexistantes, les lectures métier qui traversent Factures → Tiers/Contrats et Trésorerie → Factures/Tiers ; vérifier une réponse métier attendue, pas seulement HTTP 200.
4. Tester les écritures et la création utilisateur → Tiers uniquement dans un tenant de test réservé, avec données fictives, identifiants suivis, nettoyage par procédure métier approuvée et vérification des deux applications. Sans cette stratégie, ne pas lancer d'écriture sur PREPROD.
5. Tester les preflights de chaque backend par chemin exposé avec l'origine du tunnel, les six méthodes et `Access-Control-Allow-Credentials` ; vérifier `Access-Control-Expose-Headers` sur une réponse authentifiée.

Risque restant : les clients qui propagent Cookie/Authorization dépendent d'une requête entrante ; un appel depuis une tâche asynchrone sans contexte ne portera pas cette identité. Aucun credential technique supplémentaire ne doit être exigé sans démonstration d'un tel parcours. Les fonctionnalités IA requièrent leur clé/modèle seulement lorsqu'elles sont activées. La couverture runtime enrichie reste à exécuter ; aucune donnée métier n'a été créée pour cet audit.

## H. Corrections DevOps et tests

- Compose : les deux credentials techniques passent de `:-` à `:?required` sur Socle et Tiers.
- Exemple : les deux champs portent `CHANGE_ME`, rejeté par le parseur dotenv.
- Validateur : présence, longueur minimale 12 du password, égalité des valeurs injectées aux deux extrémités ; contrôle exact de toutes les URL interservices et Gateway.
- Tests : cas vide, placeholder, mot de passe court, couple valide, divergence entre services et destination RECETTE.

Vérifications exécutées : `python3 scripts/test-preprod-config.py -q` (19 tests OK), `python3 scripts/test-preprod-guards.py -q` (10 tests OK), `bash scripts/test-version-history.sh` (OK), et tests Maven ciblés `TiersApiClientTest`, `GatewaySecurityConfigTests`, `AuthentificationGatewayFilterTest` (tous OK). Le smoke runtime PREPROD n'a pas été relancé : il exige une session et un environnement actif non disponibles dans ce checkout ; le résultat 6/6 cité dans la demande précède ces changements de fichiers.

## I. Anomalies applicatives

Aucune correction applicative effectuée. Aucun décalage de nom de variable entre client Socle et filtre Tiers : les deux lisent `WAVY_TIERS_SERVICE_USERNAME/PASSWORD`. Les parcours fonctionnels non exécutés ne permettent pas de conclure à l'absence de bug applicatif dans les modules métier. Le comportement qui a motivé l'audit est une lacune de validation MSI, corrigée ici.

| MODULE | CONFIG | CORS | ROUTAGE | INTERSERVICE | SMOKE | ÉTAT |
|---|---|---|---|---|---|---|
| Socle | OK | OK statique | OK statique | Credentials Tiers corrigés | GET seul ; écriture contrôlée à faire | WARNING |
| Tiers | OK | OK statique | OK statique | Basic technique + profil Socle | Référentiel public seul | WARNING |
| Contrats | OK | OK statique | OK statique | Profil Socle | GET contrats seul | WARNING |
| Factures | OK | OK statique | OK statique | Socle, Tiers, Contrats | Healthcheck seul | WARNING |
| Trésorerie | OK | OK statique | OK statique | Socle, Factures, Tiers | GET comptes seul | WARNING |
| Gateway | OK | OK statique | OK statique | Cinq routes + profil Socle | GET Tiers health seul | WARNING |

`INTERSERVICE_DEPENDENCIES=15` (10 liens applicatifs, dont l'appel externe IA conditionnel, et cinq destinations de Gateway). `MISSING_REQUIRED_CONFIG=0` après correction dans les fichiers MSI. `CORS_ISSUES=0` et `ROUTING_ISSUES=0` dans l'audit statique. Ces comptes n'attestent pas de l'état des valeurs runtime actives.

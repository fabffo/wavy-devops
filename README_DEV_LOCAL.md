# Wavy - organisation dev local, Docker local et recette

Ce document consolide l'etat observe le 2026-05-12 dans les projets Wavy sous `~/projets`.
Il separe volontairement trois modes :

- local manuel : une seule instance PostgreSQL WSL sur `localhost:5432`, APIs via `./mvnw spring-boot:run`, fronts via `npm start`.
- Docker local : bases, APIs et fronts conteneurises sur ports dedies `18xxx/14xxx/15xxx`.
- Docker recette : compose et `.env.recette` dedies sur ports `28xxx/24xxx/25xxx`.

## Cartographie cible

| Service | Type | Local manuel | Docker local | Docker recette | Base | User | Password | Profil Spring | Source cible |
|---|---:|---:|---:|---:|---|---|---|---|---|
| wavy-socle-api | API | 8080 | 18080 | 28080 | wavy_socle_db | socle_user | motdepassefort | local | `application-local.properties` |
| wavy-tiers-api | API | 8081 | 18081 | 28081 | wavy_tiers_db | tiers_user | tiers_password | local | `application-local.yml` |
| wavy-contrats-api | API | 8082 | 18082 | 28082 | wavy_contrats_db | contrats_user | contrats_password | local | `application-local.yml` |
| wavy-factures-api | API | 8083 | 18083 | 28083 | wavy_factures_db | factures_user | factures_password | local | `application-local.properties` |
| wavy-gateway | gateway | 8088 | 18088 | 28088 | n/a | n/a | n/a | local/docker/recette | `application*.properties` |
| wavy-socle-front | front | 4200 | 14200 | 24200 | n/a | n/a | n/a | n/a | `package.json`, `proxy.conf.json` |
| wavy-tiers-front | front | 4201 | 14201 | 24201 | n/a | n/a | n/a | n/a | a creer/normaliser |
| wavy-contrats-front | front | 4202 | 14202 | 24202 | n/a | n/a | n/a | n/a | `environment*.ts` |
| wavy-factures-front | front | 4203 | 14203 | 24203 | n/a | n/a | n/a | n/a | `environment.ts` |
| postgres socle | database | 5432 | 15432 | 25432 | wavy_socle_db | socle_user | motdepassefort | n/a | `.env.*`, compose |
| postgres tiers | database | 5432 | 15433 | 25433 | wavy_tiers_db | tiers_user | tiers_password | n/a | `.env.*`, compose |
| postgres contrats | database | 5432 | 15434 | 25434 | wavy_contrats_db | contrats_user | contrats_password | n/a | `.env.*`, compose |
| postgres factures | database | 5432 | 15435 | 25435 | wavy_factures_db | factures_user | factures_password | n/a | `.env.*`, compose |

Note PostgreSQL local manuel : une seule installation PostgreSQL WSL ecoute sur `localhost:5432`. Les APIs partagent ce port et sont separees par nom de base et utilisateur : `wavy_socle_db`, `wavy_tiers_db`, `wavy_contrats_db`, `wavy_factures_db`. Les ports `5433`, `5434` et `5435` ne sont pas utilises en local manuel.


## Strategie PostgreSQL

Local manuel :

- une seule instance PostgreSQL WSL sur `localhost:5432` ;
- une base par domaine : `wavy_socle_db`, `wavy_tiers_db`, `wavy_contrats_db`, `wavy_factures_db` ;
- un utilisateur par domaine : `socle_user`, `tiers_user`, `contrats_user`, `factures_user` ;
- aucun port `5433`, `5434` ou `5435` en local manuel.

Docker local :

- ports PostgreSQL hotes reserves : `15432`, `15433`, `15434`, `15435`.

Docker recette :

- ports PostgreSQL hotes reserves : `25432`, `25433`, `25434`, `25435`.

## Etat observe

| Projet | Faits importants |
|---|---|
| `wavy-socle-api` | `application.properties` utilise deja `localhost:5432`, mais le nom observe est `socle_multitenant`; cible locale : `wavy_socle_db`. Compose actuel expose encore des ports a normaliser. Pas de Flyway, donnees via `donnees-reference.sql` et JPA `ddl-auto=update`. |
| `wavy-tiers-api` | Flyway OK (`V1` a `V5`); configuration locale observee avec DB `5434`, a corriger vers `localhost:5432`. Compose local doit reserver `15433`, recette `25433`. |
| `wavy-contrats-api` | Flyway OK (`V1`); configuration locale observee avec DB `5435`, a corriger vers `localhost:5432`. Compose local doit reserver `15434`, recette `25434`. |
| `wavy-factures-api` | Pas de Flyway; local utilise H2, a corriger vers PostgreSQL `localhost:5432/wavy_factures_db`; recette PostgreSQL + `data-recette.sql`; compose recette doit reserver `25435`. |
| `wavy-gateway` | Local manuel coherent sur `8088`, routes vers `8080/8081/8082/8083`; recette expose `18088`; route factures OK dans `application-recette.properties`. |
| fronts | `socle-front` sert `4200` avec proxy `8088`; `contrats-front` local `4202` vers gateway `8088`, recette `18088`; `factures-front` local `4203` vers `http://localhost:8088/api`. |

## Corrections proposees

### APIs Spring

- `wavy-socle-api`
  - Ajouter `src/main/resources/application-local.properties`.
  - Remplacer le nom par defaut `socle_multitenant` par `wavy_socle_db` et garder le port PostgreSQL local `5432`.
  - Garder `server.port=8080`.
  - Ajouter Flyway si l'on veut un vrai `V100__donnees_demo_socle.sql`; sinon garder `donnees-reference.sql` comme mecanisme socle existant.

- `wavy-tiers-api`
  - Garder `application-local.yml` avec `server.port=8081`.
  - Pour local manuel, utiliser `WAVY_TIERS_DB_PORT=5432`.
  - Pour Docker local, exposer l'API sur `18081` et PostgreSQL sur `15433`.
  - Pour recette, exposer l'API sur `28081` et PostgreSQL sur `25433`.

- `wavy-contrats-api`
  - Garder `application-local.yml` avec `server.port=8082`.
  - Pour local manuel, utiliser `WAVY_CONTRATS_DB_PORT=5432`.
  - Pour Docker local, exposer l'API sur `18082` et PostgreSQL sur `15434`.
  - Pour recette, exposer l'API sur `28082` et PostgreSQL sur `25434`.

- `wavy-factures-api`
  - Changer `application-local.properties` de H2 vers PostgreSQL local :
    `jdbc:postgresql://${WAVY_FACTURES_DB_HOST:localhost}:${WAVY_FACTURES_DB_PORT:5432}/${WAVY_FACTURES_DB_NAME:wavy_factures_db}`.
  - Ajouter `spring-boot-starter-flyway` et `flyway-database-postgresql`.
  - Creer `src/main/resources/db/migration/V1__creation_schema_factures.sql` a partir du schema JPA actuel ou d'un export valide.
  - Deplacer `data-recette.sql` vers une migration demo optionnelle ou un profil `demo`.

### Gateway

- Local manuel : `WAVY_GATEWAY_PORT=8088`, routes vers `http://localhost:8080/8081/8082/8083`.
- Docker local : port hote `18088`, routes conteneurs vers `http://wavy-*-api-local:808x`.
- Docker recette : port hote `28088`, routes conteneurs vers `http://wavy-*-api-recette:808x`.
- Ajouter dans CORS les fronts `24200..24203` pour recette.

### Fronts

- Local manuel : `npm start` sur `4200/4201/4202/4203`, tous via gateway `http://localhost:8088`.
- Docker local : fronts exposes sur `14200/14201/14202/14203`, build avec gateway `http://localhost:18088`.
- Docker recette : fronts exposes sur `24200/24201/24202/24203`, build avec gateway `http://localhost:28088`.

## Variables `.env.local` recommandees

### socle

```dotenv
COMPOSE_PROJECT_NAME=wavy-socle-local
WAVY_DOCKER_NETWORK=wavy-local
WAVY_SOCLE_DB_HOST_PORT=15432
WAVY_SOCLE_DB_NAME=wavy_socle_db
WAVY_SOCLE_DB_USERNAME=socle_user
WAVY_SOCLE_DB_PASSWORD=motdepassefort
WAVY_SOCLE_API_HOST_PORT=18080
WAVY_SOCLE_API_PORT=8080
WAVY_SOCLE_FRONT_HOST_PORT=14200
SPRING_PROFILES_ACTIVE=local
```

### tiers / contrats / factures

```dotenv
WAVY_TIERS_DB_PORT_HOST=15433
WAVY_TIERS_API_HOST_PORT=18081
WAVY_CONTRATS_DB_PORT_HOST=15434
WAVY_CONTRATS_API_HOST_PORT=18082
WAVY_FACTURES_DB_PORT_HOST=15435
WAVY_FACTURES_API_HOST_PORT=18083
WAVY_GATEWAY_HOST_PORT=18088
```

## Variables `.env.recette` recommandees

Utiliser le meme contenu logique que `.env.local`, mais avec :

```dotenv
WAVY_DOCKER_NETWORK=wavy-recette
WAVY_SOCLE_DB_HOST_PORT=25432
WAVY_TIERS_DB_PORT_HOST=25433
WAVY_CONTRATS_DB_PORT_HOST=25434
WAVY_FACTURES_DB_PORT_HOST=25435
WAVY_SOCLE_API_HOST_PORT=28080
WAVY_TIERS_API_HOST_PORT=28081
WAVY_CONTRATS_API_HOST_PORT=28082
WAVY_FACTURES_API_HOST_PORT=28083
WAVY_GATEWAY_HOST_PORT=28088
WAVY_SOCLE_FRONT_HOST_PORT=24200
WAVY_TIERS_FRONT_HOST_PORT=24201
WAVY_CONTRATS_FRONT_HOST_PORT=24202
WAVY_FACTURES_FRONT_HOST_PORT=24203
SPRING_PROFILES_ACTIVE=recette
```

## Commandes PostgreSQL local manuel

Les scripts utilisent `PSQL_ADMIN_URL`, par defaut `postgresql://postgres@localhost:5432/postgres`.

```bash
./scripts/create-local-dbs.sh
./scripts/reset-local-dbs.sh
```

Equivalent SQL :

```sql
CREATE ROLE socle_user LOGIN PASSWORD 'motdepassefort';
CREATE ROLE tiers_user LOGIN PASSWORD 'tiers_password';
CREATE ROLE contrats_user LOGIN PASSWORD 'contrats_password';
CREATE ROLE factures_user LOGIN PASSWORD 'factures_password';
CREATE DATABASE wavy_socle_db OWNER socle_user;
CREATE DATABASE wavy_tiers_db OWNER tiers_user;
CREATE DATABASE wavy_contrats_db OWNER contrats_user;
CREATE DATABASE wavy_factures_db OWNER factures_user;
```

## Procedures

### Procedure validee local manuel

Cette procedure correspond a l'etat valide avec PostgreSQL WSL unique sur `localhost:5432`, les quatre APIs lancees en local manuel et le gateway sur `8088`.

Bases PostgreSQL validees :

| Base | User | Password |
|---|---|---|
| `wavy_socle_db` | `socle_user` | `motdepassefort` |
| `wavy_tiers_db` | `tiers_user` | `tiers_password` |
| `wavy_contrats_db` | `contrats_user` | `contrats_password` |
| `wavy_factures_db` | `factures_user` | `factures_password` |

Demarrage des APIs et du gateway, dans cinq terminaux separes :

```bash
cd ~/projets/wavy-socle-api
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

```bash
cd ~/projets/wavy-tiers-api
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

```bash
cd ~/projets/wavy-contrats-api
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

```bash
cd ~/projets/wavy-factures-api
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

```bash
cd ~/projets/wavy-gateway
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

Ports valides :

| Service | Port |
|---|---:|
| `wavy-socle-api` | 8080 |
| `wavy-tiers-api` | 8081 |
| `wavy-contrats-api` | 8082 |
| `wavy-factures-api` | 8083 |
| `wavy-gateway` | 8088 |

Chargement des donnees demo locales :

```bash
cd ~/projets/wavy-devops/dev/demo-local
./load-demo-local.sh
```

Tests Linux / WSL via gateway :

```bash
curl -i -H 'X-Tenant-Id: 100' -H 'X-Utilisateur-Id: 100' -H 'X-Societe-Courante-Id: 100' http://localhost:8088/api/tiers
curl -i -H 'X-Tenant-Id: 100' -H 'X-Utilisateur-Id: 100' -H 'X-Societe-Courante-Id: 100' http://localhost:8088/api/contrats
curl -i -H 'X-Tenant-Id: 100' -H 'X-Utilisateur-Id: 100' -H 'X-Societe-Courante-Id: 100' http://localhost:8088/api/factures
```

Tests Windows CMD via gateway :

```cmd
curl -i -H "X-Tenant-Id: 100" -H "X-Utilisateur-Id: 100" -H "X-Societe-Courante-Id: 100" http://localhost:8088/api/tiers
curl -i -H "X-Tenant-Id: 100" -H "X-Utilisateur-Id: 100" -H "X-Societe-Courante-Id: 100" http://localhost:8088/api/contrats
curl -i -H "X-Tenant-Id: 100" -H "X-Utilisateur-Id: 100" -H "X-Societe-Courante-Id: 100" http://localhost:8088/api/factures
```

#### Resultat attendu

- `GET /api/tiers` retourne notamment `Client Demo SAS` et `Prestataire Demo SAS`.
- `GET /api/contrats` retourne notamment `CTR-DEMO-2026-001`.
- `GET /api/factures` retourne notamment `FAC-DEMO-2026-001`, avec sa ligne `Prestation journaliere` et sa ventilation TVA a `20`.

### Local manuel

```bash
./scripts/create-local-dbs.sh
./scripts/start-local-tmux.sh
```

Puis ouvrir :

```text
http://localhost:4200
http://localhost:4202
http://localhost:4203
http://localhost:8088/actuator/health
```

Arret :

```bash
./scripts/stop-local.sh
```

### Docker local

Prealable : creer/normaliser les `docker-compose.local.yml` et `.env.local` dans chaque projet avec les ports `180xx/142xx/154xx`.

```bash
./scripts/start-docker-local.sh
./scripts/logs-docker-local.sh
./scripts/stop-docker-local.sh
```

### Docker recette

Prealable : creer le reseau si absent, ou laisser le script le faire.

```bash
./scripts/start-docker-recette.sh
./scripts/logs-docker-recette.sh
./scripts/stop-docker-recette.sh
```

## Donnees demo Flyway

Les fichiers proposes sont dans `dev/flyway-demo/` :

- `V100__donnees_demo_socle.sql`
- `V100__donnees_demo_tiers.sql`
- `V100__donnees_demo_contrats.sql`
- `V100__donnees_demo_factures.sql`

Placement cible :

```text
wavy-socle-api/src/main/resources/db/migration/V100__donnees_demo_socle.sql
wavy-tiers-api/src/main/resources/db/migration/V100__donnees_demo_tiers.sql
wavy-contrats-api/src/main/resources/db/migration/V100__donnees_demo_contrats.sql
wavy-factures-api/src/main/resources/db/migration/V100__donnees_demo_factures.sql
```

Attention : `wavy-socle-api` et `wavy-factures-api` n'ont pas encore Flyway en source. Les migrations demo sont pretes, mais il faut d'abord ajouter Flyway et les migrations schema de base.

Jeu coherent :

- tenant `100` : `DEMO_WAVY_LOCAL`
- societe interne `100` : `Wavy Demo Services`
- utilisateurs `100` et `101`
- tiers `100`, `101`, `102`
- contrats `100`, `101`
- factures `100`, `101`

## Tests curl

Local manuel :

```bash
curl -i http://localhost:8088/actuator/health
curl -i http://localhost:8088/api/profil
curl -i http://localhost:8088/api/tiers
curl -i http://localhost:8088/api/contrats
curl -i http://localhost:8088/api/factures
```

Docker local :

```bash
curl -i http://localhost:18088/actuator/health
curl -i http://localhost:18088/api/tiers
curl -i http://localhost:18088/api/contrats
curl -i http://localhost:18088/api/factures
```

Docker recette :

```bash
curl -i http://localhost:28088/actuator/health
curl -i http://localhost:28088/api/tiers
curl -i http://localhost:28088/api/contrats
curl -i http://localhost:28088/api/factures
```

Pour les endpoints metier securises, ajouter apres connexion les headers :

```bash
-H 'X-Tenant-Id: 100' -H 'X-Utilisateur-Id: 100' -H 'X-Societe-Courante-Id: 100'
```

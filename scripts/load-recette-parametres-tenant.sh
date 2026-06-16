#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.recette"
COMPOSE_FILE="$ROOT_DIR/docker-compose.recette.yml"
SOCLE_SQL_FILE="$ROOT_DIR/dev/recette/01_socle_recette.sql"

if [ ! -f "$ENV_FILE" ]; then
  echo "Fichier .env.recette introuvable. Creez-le a partir de .env.recette.example avant de lancer ce script." >&2
  exit 1
fi

if [ ! -f "$SOCLE_SQL_FILE" ]; then
  echo "Fichier SQL introuvable : $SOCLE_SQL_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

check_service_up() {
  local service="$1"
  if ! compose ps -q "$service" >/dev/null 2>&1; then
    echo "Le service $service n'est pas demarre. Lancez ./scripts/start-docker-recette.sh avant de charger les parametres." >&2
    exit 1
  fi
}

run_query() {
  local sql="$1"
  compose exec -T socle-postgres env PGPASSWORD="$WAVY_SOCLE_DB_PASSWORD" \
    psql -U "$WAVY_SOCLE_DB_USERNAME" -d "$WAVY_SOCLE_DB_NAME" -t -A -c "$sql"
}

cd "$ROOT_DIR"

check_service_up socle-postgres

echo "Chargement des parametres tenant recette dans $WAVY_SOCLE_DB_NAME..."

sed -n "/^create table if not exists parametre_tenant /,/^select setval(pg_get_serial_sequence('parametre_tenant'/p" "$SOCLE_SQL_FILE" \
  | compose exec -T socle-postgres env PGPASSWORD="$WAVY_SOCLE_DB_PASSWORD" \
      psql -U "$WAVY_SOCLE_DB_USERNAME" -d "$WAVY_SOCLE_DB_NAME" -v ON_ERROR_STOP=1

echo
echo "Controles apres chargement :"
echo "Parametres tenant : $(run_query 'select count(*) from parametre_tenant;')"
echo "Detail par tenant et categorie :"
compose exec -T socle-postgres env PGPASSWORD="$WAVY_SOCLE_DB_PASSWORD" \
  psql -U "$WAVY_SOCLE_DB_USERNAME" -d "$WAVY_SOCLE_DB_NAME" \
  -c "select tenant_id, categorie, count(*) from parametre_tenant group by tenant_id, categorie order by tenant_id, categorie;"

echo
echo "Chargement des parametres tenant termine."

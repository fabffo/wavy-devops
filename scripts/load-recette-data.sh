#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.recette"
COMPOSE_FILE="$ROOT_DIR/docker-compose.recette.yml"
RECIPE_DIR="$ROOT_DIR/dev/recette"

if [ ! -f "$ENV_FILE" ]; then
  echo "Fichier .env.recette introuvable. Créez-le à partir de .env.recette.example avant de lancer ce script." >&2
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
    echo "Le service $service n'est pas démarré. Lancez ./scripts/start-docker-recette.sh avant de charger les données." >&2
    exit 1
  fi
}

run_sql() {
  local service="$1"
  local user="$2"
  local db="$3"
  local file="$4"

  echo "Chargement de $file dans $db..."
  compose exec -T "$service" env PGPASSWORD="${!user}" psql -U "${!user}" -d "$db" -v ON_ERROR_STOP=1 < "$file"
}

run_query() {
  local service="$1"
  local user="$2"
  local db="$3"
  local sql="$4"
  compose exec -T "$service" env PGPASSWORD="${!user}" psql -U "${!user}" -d "$db" -t -A -c "$sql"
}

cd "$ROOT_DIR"

check_service_up socle-postgres
check_service_up tiers-postgres
check_service_up contrats-postgres
check_service_up factures-postgres

run_sql socle-postgres WAVY_SOCLE_DB_USERNAME "$WAVY_SOCLE_DB_NAME" "$RECIPE_DIR/01_socle_recette.sql"
run_sql tiers-postgres WAVY_TIERS_DB_USER "$WAVY_TIERS_DB_NAME" "$RECIPE_DIR/02_tiers_recette.sql"
run_sql contrats-postgres WAVY_CONTRATS_DB_USER "$WAVY_CONTRATS_DB_NAME" "$RECIPE_DIR/03_contrats_recette.sql"
run_sql factures-postgres WAVY_FACTURES_DB_USER "$WAVY_FACTURES_DB_NAME" "$RECIPE_DIR/04_factures_recette.sql"

cat <<EOF

Contrôles après chargement :
EOF

echo "Tenants socle : $(run_query socle-postgres WAVY_SOCLE_DB_USERNAME "$WAVY_SOCLE_DB_NAME" 'select count(*) from tenant;')"
echo "Utilisateurs socle tenant 3 : $(run_query socle-postgres WAVY_SOCLE_DB_USERNAME "$WAVY_SOCLE_DB_NAME" 'select count(*) from utilisateur where tenant_id = 3;')"
echo "Rôles utilisateurs tenant 3 :"
compose exec -T socle-postgres env PGPASSWORD="${WAVY_SOCLE_DB_PASSWORD}" psql -U "$WAVY_SOCLE_DB_USERNAME" -d "$WAVY_SOCLE_DB_NAME" -t -A -c "select u.email, string_agg(r.code, ',') from utilisateur u join utilisateur_role ur on u.id = ur.utilisateur_id join role r on ur.role_id = r.id where u.tenant_id = 3 group by u.email order by u.email;"
echo "Nombre de tiers société 4 : $(run_query tiers-postgres WAVY_TIERS_DB_USER "$WAVY_TIERS_DB_NAME" 'select count(*) from tiers where societe_interne_id = 4;')"
echo "Nombre de tiers société 5 : $(run_query tiers-postgres WAVY_TIERS_DB_USER "$WAVY_TIERS_DB_NAME" 'select count(*) from tiers where societe_interne_id = 5;')"
echo "Nombre de contrats tenant 3 : $(run_query contrats-postgres WAVY_CONTRATS_DB_USER "$WAVY_CONTRATS_DB_NAME" 'select count(*) from contrat where tenant_id = 3;')"
echo "Nombre de factures tenant 3 : $(run_query factures-postgres WAVY_FACTURES_DB_USER "$WAVY_FACTURES_DB_NAME" 'select count(*) from facture where tenant_id = 3;')"

echo
 echo "Chargement terminé."

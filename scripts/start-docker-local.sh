#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.local.yml"
ENV_FILE="$ROOT_DIR/.env.local"
DEMO_DIR="$ROOT_DIR/dev/demo-local"

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

wait_http() {
  local url="$1"
  local label="$2"
  local max_attempts="${3:-60}"

  echo "Attente de $label ($url)..."
  for attempt in $(seq 1 "$max_attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label est disponible."
      return 0
    fi
    sleep 2
  done

  echo "Timeout en attendant $label." >&2
  return 1
}

load_demo_sql() {
  local service="$1"
  local user="$2"
  local database="$3"
  local file="$4"

  echo "Chargement $file dans $database..."
  compose exec -T "$service" psql -U "$user" -d "$database" -v ON_ERROR_STOP=1 < "$DEMO_DIR/$file"
}

cd "$ROOT_DIR"

echo "Construction du jar wavy-gateway utilise par son Dockerfile..."
(cd "$ROOT_DIR/../wavy-gateway" && ./mvnw -q -DskipTests package)

compose up -d --build

wait_http "http://localhost:18080/actuator/health" "socle-api"
wait_http "http://localhost:18081/api/tiers/health" "tiers-api"
wait_http "http://localhost:18082/api/contrats/health" "contrats-api"
wait_http "http://localhost:18083/api/factures/health" "factures-api"
wait_http "http://localhost:18088/actuator/health" "gateway"

load_demo_sql socle-postgres socle_user wavy_socle_db 01_socle_demo.sql
load_demo_sql tiers-postgres tiers_user wavy_tiers_db 02_tiers_demo.sql
load_demo_sql contrats-postgres contrats_user wavy_contrats_db 03_contrats_demo.sql
load_demo_sql factures-postgres factures_user wavy_factures_db 04_factures_demo.sql
load_demo_sql factures-postgres factures_user wavy_factures_db 06_factures_achats_demo.sql
load_demo_sql factures-postgres factures_user wavy_factures_db 07_salaires_demo.sql

echo
echo "Environnement Docker local Wavy demarre."
echo "Gateway : http://localhost:18088"
echo "Fronts  : http://localhost:14200 http://localhost:14201 http://localhost:14202 http://localhost:14203"

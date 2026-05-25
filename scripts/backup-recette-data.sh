#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.recette"
COMPOSE_FILE="$ROOT_DIR/docker-compose.recette.yml"
BACKUP_ROOT="$ROOT_DIR/backups/recette"

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

mkdir -p "$BACKUP_ROOT"
backup_dir="$BACKUP_ROOT/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$backup_dir"

echo "Création du dossier de sauvegarde : $backup_dir"

backup_db() {
  local service="$1"
  local user_var="$2"
  local db_var="$3"
  local password_var="$4"
  local filename="$5"
  local user="${!user_var}"
  local db="${!db_var}"
  local password="${!password_var}"

  echo "Sauvegarde de la base $db depuis $service..."
  compose exec -T "$service" env PGPASSWORD="$password" pg_dump -U "$user" -d "$db" | gzip > "$filename"
}

backup_db socle-postgres WAVY_SOCLE_DB_USERNAME WAVY_SOCLE_DB_NAME WAVY_SOCLE_DB_PASSWORD "$backup_dir/socle.sql.gz"
backup_db tiers-postgres WAVY_TIERS_DB_USER WAVY_TIERS_DB_NAME WAVY_TIERS_DB_PASSWORD "$backup_dir/tiers.sql.gz"
backup_db contrats-postgres WAVY_CONTRATS_DB_USER WAVY_CONTRATS_DB_NAME WAVY_CONTRATS_DB_PASSWORD "$backup_dir/contrats.sql.gz"
backup_db factures-postgres WAVY_FACTURES_DB_USER WAVY_FACTURES_DB_NAME WAVY_FACTURES_DB_PASSWORD "$backup_dir/factures.sql.gz"

echo "Sauvegarde terminée dans : $backup_dir"

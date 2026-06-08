#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Chargement des donnees demo locales Wavy..."

SOCLE_DB_HOST_PORT="${WAVY_SOCLE_DB_HOST_PORT:-15432}"
TIERS_DB_HOST_PORT="${WAVY_TIERS_DB_HOST_PORT:-15433}"
CONTRATS_DB_HOST_PORT="${WAVY_CONTRATS_DB_HOST_PORT:-15434}"
FACTURES_DB_HOST_PORT="${WAVY_FACTURES_DB_HOST_PORT:-15435}"

PGPASSWORD="${WAVY_SOCLE_DB_PASSWORD:-motdepassefort}" psql -h localhost -p "$SOCLE_DB_HOST_PORT" -U "${WAVY_SOCLE_DB_USERNAME:-socle_user}" -d "${WAVY_SOCLE_DB_NAME:-wavy_socle_db}" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/01_socle_demo.sql"
PGPASSWORD="${WAVY_TIERS_DB_PASSWORD:-tiers_password}" psql -h localhost -p "$TIERS_DB_HOST_PORT" -U "${WAVY_TIERS_DB_USER:-tiers_user}" -d "${WAVY_TIERS_DB_NAME:-wavy_tiers_db}" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/02_tiers_demo.sql"
PGPASSWORD="${WAVY_CONTRATS_DB_PASSWORD:-contrats_password}" psql -h localhost -p "$CONTRATS_DB_HOST_PORT" -U "${WAVY_CONTRATS_DB_USER:-contrats_user}" -d "${WAVY_CONTRATS_DB_NAME:-wavy_contrats_db}" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/03_contrats_demo.sql"
PGPASSWORD="${WAVY_FACTURES_DB_PASSWORD:-factures_password}" psql -h localhost -p "$FACTURES_DB_HOST_PORT" -U "${WAVY_FACTURES_DB_USER:-factures_user}" -d "${WAVY_FACTURES_DB_NAME:-wavy_factures_db}" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/04_factures_demo.sql"
PGPASSWORD="${WAVY_FACTURES_DB_PASSWORD:-factures_password}" psql -h localhost -p "$FACTURES_DB_HOST_PORT" -U "${WAVY_FACTURES_DB_USER:-factures_user}" -d "${WAVY_FACTURES_DB_NAME:-wavy_factures_db}" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/06_factures_achats_demo.sql"
PGPASSWORD="${WAVY_FACTURES_DB_PASSWORD:-factures_password}" psql -h localhost -p "$FACTURES_DB_HOST_PORT" -U "${WAVY_FACTURES_DB_USER:-factures_user}" -d "${WAVY_FACTURES_DB_NAME:-wavy_factures_db}" -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/07_salaires_demo.sql"

echo "Donnees demo locales chargees."

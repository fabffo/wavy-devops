#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Chargement des donnees demo locales Wavy..."

PGPASSWORD=motdepassefort psql -h localhost -p 5432 -U socle_user -d wavy_socle_db -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/01_socle_demo.sql"
PGPASSWORD=tiers_password psql -h localhost -p 5432 -U tiers_user -d wavy_tiers_db -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/02_tiers_demo.sql"
PGPASSWORD=contrats_password psql -h localhost -p 5432 -U contrats_user -d wavy_contrats_db -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/03_contrats_demo.sql"
PGPASSWORD=factures_password psql -h localhost -p 5432 -U factures_user -d wavy_factures_db -v ON_ERROR_STOP=1 -f "$SCRIPT_DIR/04_factures_demo.sql"

echo "Donnees demo locales chargees."

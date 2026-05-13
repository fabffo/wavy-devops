#!/usr/bin/env bash
set -euo pipefail

psql_admin="${PSQL_ADMIN_URL:-postgresql://postgres@localhost:5432/postgres}"

psql "$psql_admin" <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname IN ('wavy_socle_db', 'wavy_tiers_db', 'wavy_contrats_db', 'wavy_factures_db')
  AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS wavy_factures_db;
DROP DATABASE IF EXISTS wavy_contrats_db;
DROP DATABASE IF EXISTS wavy_tiers_db;
DROP DATABASE IF EXISTS wavy_socle_db;
SQL

"$(dirname "$0")/create-local-dbs.sh"

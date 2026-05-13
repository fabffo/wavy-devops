#!/usr/bin/env bash
set -euo pipefail

psql_admin="${PSQL_ADMIN_URL:-postgresql://postgres@localhost:5432/postgres}"

psql "$psql_admin" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'socle_user') THEN
    CREATE ROLE socle_user LOGIN PASSWORD 'motdepassefort';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tiers_user') THEN
    CREATE ROLE tiers_user LOGIN PASSWORD 'tiers_password';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'contrats_user') THEN
    CREATE ROLE contrats_user LOGIN PASSWORD 'contrats_password';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'factures_user') THEN
    CREATE ROLE factures_user LOGIN PASSWORD 'factures_password';
  END IF;
END $$;

SELECT 'CREATE DATABASE wavy_socle_db OWNER socle_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wavy_socle_db')\gexec
SELECT 'CREATE DATABASE wavy_tiers_db OWNER tiers_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wavy_tiers_db')\gexec
SELECT 'CREATE DATABASE wavy_contrats_db OWNER contrats_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wavy_contrats_db')\gexec
SELECT 'CREATE DATABASE wavy_factures_db OWNER factures_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'wavy_factures_db')\gexec
SQL

echo "Bases locales Wavy creees ou deja presentes."

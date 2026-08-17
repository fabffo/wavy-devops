#!/usr/bin/env bash
# Sauvegarde les bases PostgreSQL Wavy dans backups/AAAA-MM-JJ_HHMM/.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
env="$(env_name)"
timestamp="$(date +%F_%H%M)"
backup_dir="$ROOT_DIR/backups/$timestamp"
mkdir -p "$backup_dir"

info "Sauvegarde des bases $env dans $backup_dir"
for db in socle tiers contrats factures tresorerie; do
  container="$(db_container "$db" "$env")"
  user="$(db_user "$db" "$env")"
  name="$(db_name "$db" "$env")"
  ensure_container_running "$container"
  info "Sauvegarde $db ($container/$name)..."
  docker exec "$container" pg_dump -U "$user" -d "$name" -Fc > "$backup_dir/${db}.dump"
  success " $db sauvegardée : $backup_dir/${db}.dump"
done

cat > "$backup_dir/MANIFEST.txt" <<EOF
Wavy backup
Date: $(date -Is)
Environment: $env
Format: pg_dump custom (-Fc)
Databases: socle tiers contrats factures tresorerie
EOF

success " Sauvegarde complète : $backup_dir"

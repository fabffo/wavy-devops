#!/usr/bin/env bash
# Produit cinq dumps chiffrés et applique la rétention configurée.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
require_docker
require_command openssl
env=preprod
passphrase="$(env_value "$env" WAVY_BACKUP_ENCRYPTION_PASSPHRASE '')"
[[ -n "$passphrase" && "$passphrase" != CHANGE_ME ]] || die "WAVY_BACKUP_ENCRYPTION_PASSPHRASE doit être défini dans .env.preprod."
timestamp="$(date +%F_%H%M%S)"
backup_dir="$ROOT_DIR/backups/preprod/$timestamp"
mkdir -p "$backup_dir"
for db in socle tiers contrats factures tresorerie; do
  container="$(db_container "$db" "$env")"
  ensure_container_running "$container"
  info "Sauvegarde chiffrée de $db..."
  docker exec "$container" pg_dump -U "$(db_user "$db" "$env")" -d "$(db_name "$db" "$env")" -Fc \
    | WAVY_BACKUP_PASSPHRASE="$passphrase" openssl enc -aes-256-cbc -salt -pbkdf2 \
        -pass env:WAVY_BACKUP_PASSPHRASE -out "$backup_dir/$db.dump.enc"
done
retention="$(env_value "$env" WAVY_BACKUP_RETENTION_DAYS 30)"
find "$ROOT_DIR/backups/preprod" -mindepth 1 -maxdepth 1 -type d -mtime "+$retention" -print -exec rm -rf -- {} +
success " Sauvegarde préproduction chiffrée : $backup_dir"

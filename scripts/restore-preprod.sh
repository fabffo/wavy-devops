#!/usr/bin/env bash
# Restaure un lot complet de cinq dumps préproduction chiffrés.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
require_docker
require_command openssl
backup="${1:-}"
[[ -n "$backup" && -d "$backup" ]] || die "Usage : $0 /chemin/vers/backups/preprod/<date>"
passphrase="$(env_value preprod WAVY_BACKUP_ENCRYPTION_PASSPHRASE '')"
[[ -n "$passphrase" && "$passphrase" != CHANGE_ME ]] || die "Passphrase de sauvegarde absente."
for db in socle tiers contrats factures tresorerie; do
  [[ -f "$backup/$db.dump.enc" ]] || die "Dump absent : $backup/$db.dump.enc"
done
warn "Cette opération remplace les cinq bases de préproduction."
confirm "Confirmer la restauration complète ?" || die "Restauration annulée."
for db in socle tiers contrats factures tresorerie; do
  container="$(db_container "$db" preprod)"
  ensure_container_running "$container"
  info "Restauration de $db..."
  WAVY_BACKUP_PASSPHRASE="$passphrase" openssl enc -d -aes-256-cbc -pbkdf2 -pass env:WAVY_BACKUP_PASSPHRASE -in "$backup/$db.dump.enc" \
    | docker exec -i "$container" pg_restore -U "$(db_user "$db" preprod)" -d "$(db_name "$db" preprod)" --clean --if-exists --no-owner
done
"$ROOT_DIR/wavy" health preprod
success " Restauration complète validée par les healthchecks."

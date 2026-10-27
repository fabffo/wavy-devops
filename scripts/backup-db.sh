#!/usr/bin/env bash
# Sauvegarde les bases PostgreSQL Wavy dans un répertoire horodaté unique.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

env="$(env_name)"
[[ "$env" != preprod ]] || die 'PREPROD : utiliser la chaîne chiffrée backup-preprod.sh/restore-preprod.sh avec documents.'
require_docker
umask 077
DOCUMENT_VOLUME=''
if [[ "$env" == recette ]]; then
  recette_operation_lock
  source "$SCRIPT_DIR/_recette-documents.sh"
  recette_documents_setup
fi
require_command flock
mkdir -p "$ROOT_DIR/backups"
exec {recette_backup_lock_fd}>"$ROOT_DIR/backups/.${env}-backup.lock"
flock -n "$recette_backup_lock_fd" || die 'Une sauvegarde est déjà en cours.'
timestamp="$(date +%F_%H%M%S)"
backup_dir="$ROOT_DIR/backups/$timestamp"
suffix=0
while [[ -e "$backup_dir" ]]; do
  suffix=$((suffix + 1))
  backup_dir="$ROOT_DIR/backups/${timestamp}-$(printf '%02d' "$suffix")"
done
final_backup_dir="$backup_dir"
[[ -z "$DOCUMENT_VOLUME" ]] || backup_dir="$ROOT_DIR/backups/.incomplete-$timestamp-$$"
mkdir -m 700 "$backup_dir"
QUIESCED_SERVICES=()
finish_backup() {
  local code=$?
  trap - EXIT
  if [[ -n "$DOCUMENT_VOLUME" ]]; then
    recette_resume || { code=1; error "Services RECETTE à reprendre : ${QUIESCED_SERVICES[*]}"; }
  fi
  if ((code != 0)); then error "Sauvegarde incomplète conservée : $backup_dir"; fi
  exit "$code"
}
trap finish_backup EXIT
[[ -z "$DOCUMENT_VOLUME" ]] || recette_quiesce

info "Sauvegarde des bases $env dans $backup_dir"
for db in socle tiers contrats factures tresorerie; do
  container="$(db_container "$db" "$env")"
  user="$(db_user "$db" "$env")"
  name="$(db_name "$db" "$env")"
  ensure_container_running "$container"
  info "Sauvegarde $db ($container/$name)..."
  docker exec "$container" pg_dump -U "$user" -d "$name" -Fc > "$backup_dir/${db}.dump"
  [[ -z "$DOCUMENT_VOLUME" ]] || docker exec -i "$container" pg_restore --list < "$backup_dir/${db}.dump" >/dev/null
  success " $db sauvegardée : $backup_dir/${db}.dump"
done

cat > "$backup_dir/MANIFEST.txt" <<EOF
Wavy backup
Date: $(date -Is)
Environment: $env
Format: pg_dump custom (-Fc)
Databases: socle tiers contrats factures tresorerie
EOF

cat > "$backup_dir/metadata.txt" <<EOF
date=$(date -Is)
environnement=$env
composant=${WAVY_BACKUP_COMPONENT:-indisponible}
version=${WAVY_BACKUP_VERSION:-indisponible}
utilisateur=$(id -un)
bases=socle tiers contrats factures tresorerie
EOF

if [[ -n "$DOCUMENT_VOLUME" ]]; then
  recette_archive_documents
  recette_resume || die 'Reprise des backends RECETTE en échec ; lot non publié.'
  mv "$backup_dir" "$final_backup_dir"
  backup_dir="$final_backup_dir"
fi
success " Sauvegarde complète : $backup_dir"

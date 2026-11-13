#!/usr/bin/env bash
# Sauvegarde les bases PostgreSQL Wavy dans un répertoire horodaté unique.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

env="$(env_name)"
sync_hold=false
if [[ $# != 0 ]]; then
  [[ $# == 1 && $1 == --sync-hold && "$env" == recette ]] || die 'Option backup invalide.'
  sync_hold=true
fi
[[ "$env" != preprod ]] || die 'PREPROD : utiliser la chaîne chiffrée backup-preprod.sh/restore-preprod.sh avec documents.'
require_docker
umask 077
DOCUMENT_VOLUME=''
if [[ "$env" == recette ]]; then
  recette_operation_lock
  source "$SCRIPT_DIR/_recette-documents.sh"
  recette_documents_setup
  if $sync_hold; then
    [[ -n "$DOCUMENT_VOLUME" ]] || die 'Synchronisation : stockage justificatifs requis.'
    CONTRATS_VOLUME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/data/contrats/pieces-jointes"}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}{{end}}' wavy-contrats-api-recette)"
    [[ "$CONTRATS_VOLUME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || die 'Volume Contrats RECETTE requis.'
  fi
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
  if [[ -n "$DOCUMENT_VOLUME" ]] && { ! $sync_hold || ((code != 0)); }; then
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
  if $sync_hold; then
    docker run --rm --pull never --network none --read-only --security-opt no-new-privileges:true \
      --user 0:0 --mount "type=volume,source=$CONTRATS_VOLUME,target=/store,readonly,volume-nocopy" \
      --entrypoint sh "$DOCUMENT_IMAGE" -ec 'tar -cpf - -C /store .' > "$backup_dir/contrats.tar"
  else
    recette_resume || die 'Reprise des backends RECETTE en échec ; lot non publié.'
  fi
  mv "$backup_dir" "$final_backup_dir"
  backup_dir="$final_backup_dir"
fi
success " Sauvegarde complète : $backup_dir"

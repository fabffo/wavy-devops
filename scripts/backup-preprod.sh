#!/usr/bin/env bash
# Lot atomique de cinq dumps chiffrés, authentifiés et privés.
set -euo pipefail
# Contrat commun : conserve le verrou pendant toute la commande et refuse une réservation.
if [[ ${WAVY_PREPROD_WRAPPED_ENTRY:-} != "${BASH_SOURCE[0]}" ]]; then
  export WAVY_PREPROD_WRAPPED_ENTRY="${BASH_SOURCE[0]}"
  exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/preprod_operation.py" -- bash "${BASH_SOURCE[0]}" "$@"
fi
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_preprod.sh"
source "$SCRIPT_DIR/_preprod-documents.sh"
passphrase="$(preprod_value WAVY_BACKUP_ENCRYPTION_PASSPHRASE)"
[[ ${#passphrase} -ge 32 && "$passphrase" != *CHANGE_ME* ]] || die 'Passphrase backup absente ou trop courte.'
retention="$(preprod_value WAVY_BACKUP_RETENTION_DAYS)"
[[ "$retention" =~ ^[1-9][0-9]*$ ]] || die 'Rétention invalide.'
preprod_host_guard
"$SCRIPT_DIR/validate-preprod-config.sh"
preprod_document_volume_guard
# Dès qu'un lot PWA a été préparé, une archive Contrats seule ne doit plus masquer un stockage absent.
if [[ -f "$ROOT_DIR/deployments/pwa-release/state.json" ]]; then
  preprod_document_tool ro 'test -d /documents/notes-frais; test ! -L /documents/notes-frais'
fi
require_command openssl
require_command flock
preprod_backup_operation_lock
base="$ROOT_DIR/backups/preprod"
mkdir -p "$base"
chmod 700 "$base"
exec 8>"$base/.backup.lock"
flock -n 8 || die 'Une sauvegarde/restauration PREPROD est déjà en cours.'
for db in socle tiers contrats factures tresorerie; do
  preprod_container_guard "$(db_container "$db" preprod)" "$db-postgres"
done
stage="$(mktemp -d "$base/.incomplete.XXXXXX")"
QUIESCED_SERVICES=()
finish_backup() {
  local code=$?
  trap - EXIT
  preprod_resume || code=1
  rm -rf -- "$stage"
  exit "$code"
}
trap finish_backup EXIT
preprod_quiesce
for db in socle tiers contrats factures tresorerie; do
  container="$(db_container "$db" preprod)"
  info "Sauvegarde chiffrée de $db..."
  docker exec "$container" pg_dump -U "$(db_user "$db" preprod)" -d "$(db_name "$db" preprod)" -Fc \
    | WAVY_BACKUP_PASSPHRASE="$passphrase" openssl enc -aes-256-cbc -salt -pbkdf2 \
        -pass env:WAVY_BACKUP_PASSPHRASE -out "$stage/$db.dump.enc"
done
info 'Archivage chiffré des documents Contrats et Notes de frais si présents...'
preprod_document_tool ro 'test -d /documents/contrats; test ! -L /documents/notes-frais; if test -d /documents/notes-frais; then tar -cpf - -C /documents contrats notes-frais; else tar -cpf - -C /documents contrats; fi'   | WAVY_BACKUP_PASSPHRASE="$passphrase" openssl enc -aes-256-cbc -salt -pbkdf2       -pass env:WAVY_BACKUP_PASSPHRASE -out "$stage/documents.tar.enc"
# Relire l’archive chiffrée avant de publier un lot déclaré restaurable.
WAVY_BACKUP_PASSPHRASE="$passphrase" openssl enc -d -aes-256-cbc -pbkdf2 -pass env:WAVY_BACKUP_PASSPHRASE -in "$stage/documents.tar.enc" \
  | python3 "$SCRIPT_DIR/preprod_document_archive.py" -
WAVY_BACKUP_PASSPHRASE="$passphrase" python3 "$SCRIPT_DIR/preprod_backup_manifest.py" sign "$stage"
preprod_resume || die "Reprise des backends impossible."
for service in "${QUIESCED_SERVICES[@]}"; do preprod_wait "$service"; done
QUIESCED_SERVICES=()
final="$base/$(date -u +%Y%m%dT%H%M%SZ)-${stage##*.}"
mv "$stage" "$final"
# Seuls les lots complets suivant notre convention sont éligibles à la rétention.
find "$base" -mindepth 1 -maxdepth 1 -type d -name '????????T??????Z-*' -mtime "+$retention" -exec rm -rf -- {} +
success " Sauvegarde PREPROD complète : $final"

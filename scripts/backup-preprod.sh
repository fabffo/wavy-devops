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
# Un abandon avant toute preparation de stockage ne rend pas Notes obligatoire.
# Tout etat engage, ambigu ou illisible conserve le controle strict existant.
if [[ -f "$ROOT_DIR/deployments/pwa-release/state.json" ]]; then
  notes_policy="$(python3 - "$SCRIPT_DIR" "$ROOT_DIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from preprod_operation import read_private
try:
    state = read_private(Path(sys.argv[2]) / 'deployments/pwa-release/state.json')
    unused = (state.get('phase') == 'abandoned' and state.get('mutationStarted') is False
              and 'previous' in state and state['previous'] is None
              and state.get('completed') == [] and state.get('observed') == {}
              and 'storagePreconditions' not in state and 'backup' not in state)
except Exception:
    unused = False
print('optional' if unused else 'required')
PY
)"
  notes_probe='test -d /documents/notes-frais; test ! -L /documents/notes-frais'
  if [[ "$notes_policy" == optional ]]; then
    notes_probe='test -r /documents; test -x /documents; test ! -L /documents/notes-frais; if test -e /documents/notes-frais; then test -d /documents/notes-frais; fi'
  fi
  preprod_document_tool ro "$notes_probe" || {
    code=$?
    error "Sauvegarde PREPROD refusee : controle documentaire PWA en echec (code=$code, notes=$notes_policy). Verifier /documents/notes-frais (presence requise selon l'etat PWA, type, acces, lien symbolique) et le conteneur utilitaire."
    exit "$code"
  }
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
  if ((code != 0)); then error "Lot PREPROD incomplet conserve : $stage"; fi
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
# Le nettoyage fait l'objet d'un plan et d'un accord distincts ; aucune purge a la livraison.
success " Sauvegarde PREPROD complète : $final"

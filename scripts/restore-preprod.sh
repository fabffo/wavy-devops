#!/usr/bin/env bash
# Restore explicite, jamais appelé automatiquement par release-preprod.sh.
set -euo pipefail
# Contrat commun : conserve le verrou pendant toute la commande et refuse une réservation.
if [[ ${WAVY_PREPROD_WRAPPED_ENTRY:-} != "${BASH_SOURCE[0]}" ]]; then
  export WAVY_PREPROD_WRAPPED_ENTRY="${BASH_SOURCE[0]}"
  exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/preprod_operation.py" -- bash "${BASH_SOURCE[0]}" "$@"
fi
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_preprod.sh"
source "$SCRIPT_DIR/_preprod-documents.sh"
[[ $# == 2 && $2 == --with-documents ]] || die 'Usage : restore-preprod.sh backups/preprod/<lot> --with-documents (remplace DB ET pièces jointes)'
backup="$(realpath "$1")"
[[ "$backup" == "$ROOT_DIR/backups/preprod/"* && -d "$backup" ]] || die 'Lot hors du répertoire backups/preprod.'
passphrase="$(preprod_value WAVY_BACKUP_ENCRYPTION_PASSPHRASE)"
[[ ${#passphrase} -ge 32 && "$passphrase" != *CHANGE_ME* ]] || die 'Passphrase absente.'
preprod_host_guard
"$SCRIPT_DIR/validate-preprod-config.sh"
for key in WAVY_SMOKE_TENANT_ID WAVY_SMOKE_USER_ID WAVY_SMOKE_COMPANY_ID; do
  [[ "${!key:-}" =~ ^[1-9][0-9]*$ ]] || die "Contexte smoke manquant : $key"
done
[[ -n "${WAVY_SMOKE_USER:-}" && -n "${WAVY_SMOKE_PASSWORD:-}" ]] || die 'Authentification smoke requise.'
preprod_document_volume_guard
require_command openssl
require_command flock
mkdir -p "$ROOT_DIR/deployments"
preprod_backup_operation_lock
exec 8>"$ROOT_DIR/backups/preprod/.backup.lock"
flock -n 8 || die 'Une sauvegarde PREPROD est déjà en cours.'
WAVY_BACKUP_PASSPHRASE="$passphrase" python3 "$SCRIPT_DIR/preprod_backup_manifest.py" verify "$backup"
# Les cinq déchiffrements et catalogues sont vérifiés AVANT toute modification DB.
tmp="$(mktemp -d "${TMPDIR:-/tmp}/wavy-preprod-restore.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT
for db in socle tiers contrats factures tresorerie; do
  container="$(db_container "$db" preprod)"
  preprod_container_guard "$container" "$db-postgres"
  WAVY_BACKUP_PASSPHRASE="$passphrase" openssl enc -d -aes-256-cbc -pbkdf2 \
    -pass env:WAVY_BACKUP_PASSPHRASE -in "$backup/$db.dump.enc" -out "$tmp/$db.dump"
  docker exec -i "$container" pg_restore --list < "$tmp/$db.dump" >/dev/null
 done
WAVY_BACKUP_PASSPHRASE="$passphrase" openssl enc -d -aes-256-cbc -pbkdf2   -pass env:WAVY_BACKUP_PASSPHRASE -in "$backup/documents.tar.enc" -out "$tmp/documents.tar"
python3 "$SCRIPT_DIR/preprod_document_archive.py" "$tmp/documents.tar"
# Pas de restauration avec des APIs susceptibles d’écrire en parallèle.
for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$(service_name "$component" preprod)" 2>/dev/null || true)" == false ]] || die 'Arrêter les six backends PREPROD avant restauration.'
done
warn 'Remplacement des cinq bases PREPROD ; aucun restore distribué atomique.'
confirm 'Confirmer le remplacement des CINQ BASES ET des DOCUMENTS Contrats et Notes de frais sur wavy-preprod ?' || die 'Restauration annulée.'
for db in socle tiers contrats factures tresorerie; do
  docker exec -i "$(db_container "$db" preprod)" pg_restore \
    -U "$(db_user "$db" preprod)" -d "$(db_name "$db" preprod)" \
    --clean --if-exists --no-owner --exit-on-error --single-transaction < "$tmp/$db.dump"
done
# Le volume est privé, les backends restent arrêtés jusqu’à la fin de l’extraction.
preprod_document_tool rw 'test -d /documents/contrats; rm -rf /documents/contrats /documents/notes-frais; tar -xpf - -C /documents; mkdir -p /documents/notes-frais; chown 100:101 /documents/notes-frais; chmod 700 /documents/notes-frais' < "$tmp/documents.tar"
# Redémarrage des conteneurs existants, sans pull/recréation/changement d’image.
for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway; do
  container="$(service_name "$component" preprod)"
  [[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$container")" == wavy-preprod ]] || die 'Conteneur hors PREPROD.'
  docker start "$container" >/dev/null
  preprod_wait "$container"
done
"$SCRIPT_DIR/healthcheck.sh" preprod
"$SCRIPT_DIR/smoke-test.sh" preprod
success 'Restauration PREPROD terminée, healthchecks et smoke tests OK.'

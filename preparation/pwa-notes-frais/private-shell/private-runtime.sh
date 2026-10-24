#!/usr/bin/env bash
# Adaptateur privé : jamais appelé sans propriétaire + FD global hérité.
set -euo pipefail
umask 077
unset WAVY_PRIVATE_BASELINE
PRIVATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PRIVATE_DIR/../scripts/_runtime.sh"
preprod_host_guard
python3 - "$DEVOPS_ROOT" "$PWA_RELEASE_PLAN" "$PWA_RELEASE_RUN" "$PWA_RELEASE_LOCK_FD" <<'PY'
import importlib.util,json,os,sys
from pathlib import Path
root=Path(sys.argv[1]);directory=root/'deployments/pwa-release'
spec=importlib.util.spec_from_file_location('op',root/'scripts/preprod_operation.py')
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)
if Path(sys.argv[2]) != directory/'runtime-plan.json': raise SystemExit('Plan non canonique')
with op.Operation(root,owner=sys.argv[3],inherited=int(sys.argv[4])):
    state=op.read_private(directory/'state.json')
    reserved=op.read_private(root/'deployments/preprod-reservation.json')
    plan=json.loads((directory/'runtime-plan.json').read_text())
    import hashlib
    digest=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
    if not (state.get('profile')=='private-tunnel-v1' and plan.get('privateProfile')=='private-tunnel-v1'
            and state['run']==reserved['run']==sys.argv[3]
            and state['planHash']==reserved['planHash']==digest):raise SystemExit('Lot privé refusé')
PY
# Même FD et même réservation que l'orchestrateur ; aucune relaxation HTTPS publique.
preprod_backup_operation_lock
candidate_validate() {
  python3 "$PRIVATE_DIR/validate-private.py" --env-file "$PWA_RELEASE_ENV" \
    --gate-dir "$WAVY_PRIVATE_PWA_GATE_DIR" --release-candidate
}
preprod_value() { python3 "$SCRIPT_DIR/preprod_config.py" value "$PWA_RELEASE_ENV" "$1"; }
case "${1:-}" in
  guard)
    candidate_validate
    for db in socle tiers contrats factures tresorerie; do
      preprod_container_guard "$(db_container "$db" preprod)" "$db-postgres"
    done
    preprod_document_volume_guard
    for dir in "$ROOT_DIR" "$(docker info --format '{{.DockerRootDir}}')"; do
      available="$(df -Pk "$dir" | awk 'NR==2 {print $4}')"
      [[ $available =~ ^[0-9]+$ ]] && ((available>=1048576)) || die 'Disque insuffisant.'
    done
    ;;
  checks)
    preprod_reload_erp_shell_nginx
    "$SCRIPT_DIR/healthcheck.sh" preprod
    # Le smoke actif ne peut pas entrer dans une réservation sans wrapper propriétaire.
    # Ces GET conservateurs complètent les checks de session opérateur sans fausse identité.
    for path in / /modules/socle/ /modules/tiers/ /modules/contrats/ /modules/factures/ /modules/tresorerie/; do
      curl --silent --show-error --fail --max-time 15 "http://127.0.0.1:24443$path" >/dev/null
    done
    ;;
  closed)
    for path in /pwa /pwa/ /pwa/ngsw-worker.js /pwa/ngsw.json /pwa/manifest.webmanifest /api/pwa /api/pwa/session; do
      response="$(curl --silent --show-error --max-time 5 -D - -o /dev/null -w $'\n%{http_code}' "http://127.0.0.1:24443$path")"
      [[ ${response##*$'\n'} == 404 ]] && printf '%s' "$response" | grep -Eqi '^X-Wavy-Private-Gate: closed[[:space:]]*$' || die 'Fermeture privée non prouvée.'
    done
    # OPTIONS sans corps/session : aucun effet métier, marqueur Nginx obligatoire.
    for path in /api/notes-frais /api/notes-frais/0 /api/notes-frais/0/justificatif /api/notes-frais/0/valider /api/notes-frais/transformer-facture-achat; do
      response="$(curl --silent --show-error --max-time 5 -X OPTIONS -D - -o /dev/null -w $'\n%{http_code}' "http://127.0.0.1:24443$path")"
      [[ ${response##*$'\n'} == 403 ]] && printf '%s' "$response" | grep -Eqi '^X-Wavy-Private-Gate: closed[[:space:]]*$' || die 'Verrou Notes non prouvé.'
    done
    ;;
  backup|backup-baseline)
    [[ $1 != backup-baseline ]] || export WAVY_PRIVATE_BASELINE=1
    source "$PRIVATE_DIR/backup-private.sh"
    ;;
  verify-backup)
    passphrase="$(preprod_value WAVY_BACKUP_ENCRYPTION_PASSPHRASE)"
    WAVY_BACKUP_PASSPHRASE="$passphrase" python3 "$SCRIPT_DIR/preprod_backup_manifest.py" verify "$2"
    ;;
  restore-isolated)
    python3 "$PRIVATE_DIR/restore-private.py" --execute-on-approved-host --env "$PWA_RELEASE_ENV" --backup "$2"
    ;;
  *) die 'Action privée non supportée.';;
esac

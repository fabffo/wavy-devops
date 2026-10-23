#!/usr/bin/env bash
# Adaptateur candidat : aucune action lors du source ; aucun changement des scripts actifs.
set -euo pipefail
CANDIDATE_SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANDIDATE_DIR="$(dirname "$CANDIDATE_SCRIPTS")"
DEVOPS_ROOT="$(cd "$CANDIDATE_DIR/../.." && pwd)"
source "$DEVOPS_ROOT/scripts/_preprod.sh"
source "$DEVOPS_ROOT/scripts/_preprod-documents.sh"
: "${PWA_RELEASE_PLAN:?plan requis}"
: "${PWA_RELEASE_ENV:?dotenv requis}"
preprod_value() { python3 "$DEVOPS_ROOT/scripts/preprod_config.py" value "$PWA_RELEASE_ENV" "$1"; }
candidate_validate() {
  python3 "$CANDIDATE_SCRIPTS/preprod_config.py" validate "$PWA_RELEASE_ENV" --plan "$PWA_RELEASE_PLAN"
}
preprod_compose() {
  python3 "$CANDIDATE_SCRIPTS/preprod_config.py" compose "$PWA_RELEASE_ENV" --plan "$PWA_RELEASE_PLAN" "$@"
}
preprod_backup_operation_lock() {
  [[ ${PWA_RELEASE_LOCK_FD:-} =~ ^[0-9]+$ && ${PWA_RELEASE_RUN:-} =~ ^[a-f0-9]{32}$ ]] || die 'Propriétaire et verrou hérités requis.'
  exec 9<&"$PWA_RELEASE_LOCK_FD"
  python3 - "$DEVOPS_ROOT" "$PWA_RELEASE_RUN" <<'PY'
import importlib.util,sys
sys.dont_write_bytecode=True
from pathlib import Path
root=Path(sys.argv[1]);spec=importlib.util.spec_from_file_location('operation',root/'scripts/preprod_operation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try:
    with m.Operation(root,owner=sys.argv[2],inherited=9):pass
except Exception:raise SystemExit('Verrou/réservation candidate refusé.')
PY
}

#!/usr/bin/env bash
# Option --env-file réservée à la validation statique, jamais au déploiement.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
preprod_env="$ROOT_DIR/.env.preprod"
if [[ $# != 0 ]]; then
  [[ $# == 2 && $1 == --env-file ]] || die 'Usage : validate-preprod-config.sh [--env-file fichier-factice]'
  preprod_env="$2"
fi
exec python3 "$SCRIPT_DIR/preprod_config.py" validate "$preprod_env"

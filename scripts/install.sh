#!/usr/bin/env bash
# Parcours de livraison de la CLI existante ; aucun transport distant.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
umask 077
[[ ( $# == 1 && ( $1 == recette || $1 == preprod ) ) || ( $# == 2 && $1 == recette && $2 == --check ) ]] || die 'Usage : ./wavy install recette [--check] | preprod'
env="$1"
if [[ "${2:-}" == --check ]]; then
  exec python3 -B "$SCRIPT_DIR/delivery_check.py" diagnose
fi
# Un seul moteur : precontroles, lot coordonne, application de la release.
exec python3 "$SCRIPT_DIR/delivery_batch.py" run "$env"

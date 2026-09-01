#!/usr/bin/env bash
# Délègue le smoke authentifié RECETTE au dépôt Gateway, sans dupliquer sa logique.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gateway_smoke="$script_dir/../../wavy-gateway/scripts/smoke-authenticated-recette.sh"

[[ -x "$gateway_smoke" ]] || {
  printf 'Script Gateway introuvable ou non exécutable : %s\n' "$gateway_smoke" >&2
  exit 2
}

exec "$gateway_smoke" "$@"

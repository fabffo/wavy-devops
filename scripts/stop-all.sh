#!/usr/bin/env bash
# Arrête les services applicatifs. Les bases PostgreSQL ne sont arrêtées qu'après confirmation.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

env="$(env_name)"
if [[ "$env" == preprod && ${WAVY_PREPROD_WRAPPED_ENTRY:-} != "${BASH_SOURCE[0]}" ]]; then
  export WAVY_PREPROD_WRAPPED_ENTRY="${BASH_SOURCE[0]}"
  exec python3 "$SCRIPT_DIR/preprod_operation.py" -- bash "${BASH_SOURCE[0]}" "$@"
fi
require_docker
app_services=(
  "$(service_name socle-api "$env")"
  "$(service_name tiers-api "$env")"
  "$(service_name contrats-api "$env")"
  "$(service_name factures-api "$env")"
  "$(service_name tresorerie-api "$env")"
  "$(service_name gateway "$env")"
  "$(service_name socle-front "$env")"
  "$(service_name tiers-front "$env")"
  "$(service_name contrats-front "$env")"
  "$(service_name factures-front "$env")"
  "$(service_name tresorerie-front "$env")"
  "$(service_name pwa "$env")"
  "$(service_name erp-shell "$env")"
)

info "Arrêt des services applicatifs ($env)..."
compose "$env" stop "${app_services[@]}"
success " Services applicatifs arrêtés."

if confirm "Arrêter aussi les bases PostgreSQL $env ? Les volumes de données seront conservés."; then
  compose "$env" stop socle-postgres tiers-postgres contrats-postgres factures-postgres tresorerie-postgres
  success " Bases PostgreSQL arrêtées, volumes conservés."
else
  warn "Bases PostgreSQL laissées démarrées."
fi

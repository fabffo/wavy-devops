#!/usr/bin/env bash
# Affiche les logs d'un service Wavy choisi.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
env="$(env_name)"
choice="${1:-}"

if [[ -z "$choice" ]]; then
  echo "Service à suivre ($env) :"
  select choice in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
    [[ -n "$choice" ]] && break
  done
fi

service="$(service_name "$choice" "$env")"
info "Logs de $service. Ctrl+C pour quitter."
compose "$env" logs -f --tail="${TAIL:-150}" "$service"

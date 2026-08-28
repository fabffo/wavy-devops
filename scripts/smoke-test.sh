#!/usr/bin/env bash
# Vérifie des fonctions applicatives GET sans modifier les données Wavy.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

usage() {
  printf 'Usage : %s <local|recette|preprod>\n' "$0" >&2
}

[[ "$#" -eq 1 ]] || { usage; exit 2; }
env="$1"
case "$env" in
  local|recette|preprod) ;;
  *) usage; die "Environnement invalide : $env" ;;
esac

require_command curl
[[ "$env" != preprod ]] || require_docker

tenant_id="${WAVY_SMOKE_TENANT_ID:-}"
user_id="${WAVY_SMOKE_USER_ID:-}"
company_id="${WAVY_SMOKE_COMPANY_ID:-}"
smoke_user="${WAVY_SMOKE_USER:-}"
smoke_password="${WAVY_SMOKE_PASSWORD:-}"

if [[ "$env" != preprod ]]; then
  tenant_id="${tenant_id:-1}"
  user_id="${user_id:-1}"
  company_id="${company_id:-1}"
fi

services=(socle tiers contrats factures tresorerie gateway)
labels=(Socle Tiers Contrats Factures Tresorerie Gateway)
internal_ports=(8080 8081 8082 8083 8086 8088)
paths=(
  /actuator/health
  /api/tiers/referentiels/natures-personne
  /api/contrats
  /actuator/health
  /api/tresorerie/comptes-bancaires
  /api/tiers/health
)
if [[ "$env" == recette ]]; then
  paths[4]=/actuator/health
fi
port_variables=(
  WAVY_SOCLE_API_HOST_PORT
  WAVY_TIERS_API_HOST_PORT
  WAVY_CONTRATS_API_HOST_PORT
  WAVY_FACTURES_API_HOST_PORT
  WAVY_TRESORERIE_API_HOST_PORT
  WAVY_GATEWAY_HOST_PORT
)
default_host_ports_local=(18080 18081 18082 18083 18086 18088)
default_host_ports_recette=(28080 28081 28082 28083 28086 28088)

response_body=''

context_available() {
  [[ -n "$tenant_id" && -n "$user_id" && -n "$company_id" ]]
}

fetch_from_host() {
  local url="$1" output
  local -a args=(
    -fsS --max-time 10
    -H "X-Tenant-Id: $tenant_id"
    -H "X-Utilisateur-Id: $user_id"
    -H "X-Societe-Courante-Id: $company_id"
  )
  if [[ -n "$smoke_user" && -n "$smoke_password" ]]; then
    args+=(-u "$smoke_user:$smoke_password")
  fi
  output="$(curl "${args[@]}" "$url")" || return 1
  response_body="$output"
}

fetch_from_preprod() {
  local service="$1" port="$2" path="$3" container output
  container="wavy-${service}-api-preprod"
  [[ "$service" == gateway ]] && container=wavy-gateway-preprod

  if [[ "$service" == socle ]]; then
    local -a curl_args=(
      -fsS --max-time 10
      -H "X-Tenant-Id: $tenant_id"
      -H "X-Utilisateur-Id: $user_id"
      -H "X-Societe-Courante-Id: $company_id"
    )
    if [[ -n "$smoke_user" && -n "$smoke_password" ]]; then
      curl_args+=(-u "$smoke_user:$smoke_password")
    fi
    output="$(docker exec "$container" curl "${curl_args[@]}" "http://localhost:${port}${path}")" || return 1
  else
    local -a wget_args=(
      -qO- -T 10
      --header="X-Tenant-Id: $tenant_id"
      --header="X-Utilisateur-Id: $user_id"
      --header="X-Societe-Courante-Id: $company_id"
    )
    if [[ -n "$smoke_user" && -n "$smoke_password" ]]; then
      wget_args+=(--user="$smoke_user" --password="$smoke_password")
    fi
    output="$(docker exec "$container" wget "${wget_args[@]}" "http://localhost:${port}${path}")" || return 1
  fi
  response_body="$output"
}

fetch_service() {
  local index="$1" host_port url
  if [[ "$env" == preprod ]]; then
    fetch_from_preprod "${services[$index]}" "${internal_ports[$index]}" "${paths[$index]}"
    return
  fi

  if [[ "$env" == local ]]; then
    host_port="$(env_value "$env" "${port_variables[$index]}" "${default_host_ports_local[$index]}")"
  else
    host_port="$(env_value "$env" "${port_variables[$index]}" "${default_host_ports_recette[$index]}")"
  fi
  url="http://localhost:${host_port}${paths[$index]}"
  fetch_from_host "$url"
}

is_json_array() {
  [[ "$response_body" =~ ^[[:space:]]*\[.*\][[:space:]]*$ ]]
}

validate_response() {
  local service="$1"
  case "$service" in
    socle) [[ "$response_body" == *'"status":"UP"'* ]] ;;
    tiers) is_json_array && [[ "$response_body" == *'"SALARIE_INTERNE"'* ]] ;;
    contrats) is_json_array ;;
    factures) [[ "$response_body" == *'"status":"UP"'* ]] ;;
    tresorerie)
      if [[ "$env" == recette ]]; then
        [[ "$response_body" == *'"status":"UP"'* ]]
      else
        is_json_array
      fi
      ;;
    gateway)
      [[ "$response_body" == *'"module":"wavy-tiers-api"'* \
        && "$response_body" == *'"status":"OK"'* ]]
      ;;
    *) return 1 ;;
  esac
}

needs_context() {
  case "$1" in
    contrats|factures|tresorerie) return 0 ;;
    *) return 1 ;;
  esac
}

needs_preprod_auth() {
  [[ "$env" == preprod ]] || return 1
  case "$1" in
    socle|contrats) return 0 ;;
    *) return 1 ;;
  esac
}

failed=0
passed=0
for index in "${!services[@]}"; do
  service="${services[$index]}"
  label="${labels[$index]}"
  printf '%-12s GET %s\n' "$label" "${paths[$index]}"

  if needs_context "$service" && ! context_available; then
    printf '%-12s KO (définir WAVY_SMOKE_TENANT_ID, WAVY_SMOKE_USER_ID et WAVY_SMOKE_COMPANY_ID)\n' "$label" >&2
    failed=$((failed + 1))
    continue
  fi
  if needs_preprod_auth "$service" && [[ -z "$smoke_user" || -z "$smoke_password" ]]; then
    printf '%-12s KO (définir WAVY_SMOKE_USER et WAVY_SMOKE_PASSWORD)\n' "$label" >&2
    failed=$((failed + 1))
    continue
  fi

  if fetch_service "$index" && validate_response "$service"; then
    printf '%-12s OK\n' "$label"
    passed=$((passed + 1))
  else
    printf '%-12s KO (requête ou contenu invalide)\n' "$label" >&2
    failed=$((failed + 1))
  fi
done

printf '\nRésumé : %d OK, %d KO\n' "$passed" "$failed"
if ((failed)); then
  printf 'Smoke tests %s : KO\n' "$env" >&2
  exit 1
fi

printf 'Smoke tests %s : OK\n' "$env"

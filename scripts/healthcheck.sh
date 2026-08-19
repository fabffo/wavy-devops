#!/usr/bin/env bash
# Attend la disponibilité HTTP réelle des six backends Wavy.
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

attempts="${HEALTHCHECK_MAX_ATTEMPTS:-30}"
interval="${HEALTHCHECK_INTERVAL_SECONDS:-2}"
[[ "$attempts" =~ ^[1-9][0-9]*$ ]] || die "HEALTHCHECK_MAX_ATTEMPTS doit être un entier positif."
[[ "$interval" =~ ^[0-9]+$ ]] || die "HEALTHCHECK_INTERVAL_SECONDS doit être un entier positif ou nul."

services=(socle tiers contrats factures tresorerie gateway)
ports=(8080 8081 8082 8083 8086 8088)
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

http_check_from_host() {
  local url="$1"
  curl -fsS --max-time 5 "$url" >/dev/null 2>&1
}

http_check_in_container() {
  local service="$1" port="$2" container tool
  container="wavy-${service}-api-preprod"
  [[ "$service" == "gateway" ]] && container="wavy-gateway-preprod"
  tool=wget
  [[ "$service" == "socle" ]] && tool=curl
  if [[ "$tool" == curl ]]; then
    docker exec "$container" curl -fsS --max-time 5 "http://localhost:${port}/actuator/health" >/dev/null 2>&1
  else
    docker exec "$container" wget -qO- -T 5 "http://localhost:${port}/actuator/health" >/dev/null 2>&1
  fi
}

check_service() {
  local index="$1" service port host_port url attempt
  service="${services[$index]}"
  port="${ports[$index]}"

  if [[ "$env" == preprod ]]; then
    url="http://localhost:${port}/actuator/health (dans le conteneur)"
  else
    if [[ "$env" == local ]]; then
      host_port="$(env_value "$env" "${port_variables[$index]}" "${default_host_ports_local[$index]}")"
    else
      host_port="$(env_value "$env" "${port_variables[$index]}" "${default_host_ports_recette[$index]}")"
    fi
    url="http://localhost:${host_port}/actuator/health"
  fi

  printf '%-12s attente de %s\n' "${service^}" "$url"
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if [[ "$env" == preprod ]]; then
      if http_check_in_container "$service" "$port"; then
        printf '%-12s OK (tentative %d/%d)\n' "${service^}" "$attempt" "$attempts"
        return 0
      fi
    elif http_check_from_host "$url"; then
      printf '%-12s OK (tentative %d/%d)\n' "${service^}" "$attempt" "$attempts"
      return 0
    fi
    ((attempt < attempts)) && sleep "$interval"
  done

  printf '%-12s KO après %d tentatives\n' "${service^}" "$attempts" >&2
  return 1
}

require_command curl
[[ "$env" != preprod ]] || require_docker

failed=0
for index in "${!services[@]}"; do
  check_service "$index" || failed=1
done

if ((failed)); then
  error "Au moins une API $env reste indisponible."
  exit 1
fi

success " Toutes les APIs $env répondent sur /actuator/health."

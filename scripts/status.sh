#!/usr/bin/env bash
# Affiche le statut lisible des conteneurs Wavy, ports et healthchecks.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
info "Conteneurs Wavy"
printf "%-38s %-24s %-10s %s\n" "NOM" "STATUT" "HEALTH" "PORTS"
printf "%-38s %-24s %-10s %s\n" "--------------------------------------" "------------------------" "----------" "-----"

while IFS= read -r container; do
  status="$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || printf '-')"
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$container" 2>/dev/null || printf '-')"
  ports="$(docker port "$container" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  [[ -n "$ports" ]] || ports="-"
  case "$health" in
    healthy) health_text="${GREEN}${health}${NC}" ;;
    unhealthy) health_text="${RED}${health}${NC}" ;;
    starting) health_text="${YELLOW}${health}${NC}" ;;
    *) health_text="$health" ;;
  esac
  printf "%-38s %-24s %-19b %s\n" "$container" "$status" "$health_text" "$ports"
done < <(docker ps -a --format '{{.Names}}' | grep -E '^(wavy-|socle-db-|tiers-db-|contrats-db-|factures-db-|tresorerie-db-)' | sort)

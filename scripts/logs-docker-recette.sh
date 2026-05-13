#!/usr/bin/env bash
set -euo pipefail

base_dir="${WAVY_PROJECTS_DIR:-$HOME/projets}"

for project in wavy-socle-api wavy-tiers-api wavy-contrats-api wavy-factures-api wavy-gateway wavy-socle-front wavy-contrats-front wavy-factures-front; do
  compose="$base_dir/$project/docker-compose.recette.yml"
  env_file="$base_dir/$project/.env.recette"
  if [[ -f "$compose" ]]; then
    args=(-f "$compose")
    [[ -f "$env_file" ]] && args=(--env-file "$env_file" "${args[@]}")
    docker compose "${args[@]}" logs --tail=80
  fi
done

#!/usr/bin/env bash
set -euo pipefail

base_dir="${WAVY_PROJECTS_DIR:-$HOME/projets}"

for project in wavy-factures-front wavy-contrats-front wavy-socle-front wavy-gateway wavy-factures-api wavy-contrats-api wavy-tiers-api wavy-socle-api; do
  compose="$base_dir/$project/docker-compose.recette.yml"
  env_file="$base_dir/$project/.env.recette"
  if [[ -f "$compose" ]]; then
    args=(-f "$compose")
    [[ -f "$env_file" ]] && args=(--env-file "$env_file" "${args[@]}")
    docker compose "${args[@]}" down
  fi
done

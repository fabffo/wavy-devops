#!/usr/bin/env bash
set -euo pipefail

base_dir="${WAVY_PROJECTS_DIR:-$HOME/projets}"
network="${WAVY_DOCKER_RECETTE_NETWORK:-wavy-recette}"

docker network inspect "$network" >/dev/null 2>&1 || docker network create "$network"

for project in wavy-socle-api wavy-tiers-api wavy-contrats-api wavy-factures-api wavy-gateway wavy-socle-front wavy-contrats-front wavy-factures-front; do
  compose="$base_dir/$project/docker-compose.recette.yml"
  env_file="$base_dir/$project/.env.recette"
  if [[ -f "$compose" ]]; then
    args=(-f "$compose")
    [[ -f "$env_file" ]] && args=(--env-file "$env_file" "${args[@]}")
    docker compose "${args[@]}" up -d --build
  else
    echo "Ignore, compose absent: $compose"
  fi
done

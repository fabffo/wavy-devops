#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.recette.yml"
ENV_FILE="$ROOT_DIR/.env.recette"
REMOVE_VOLUMES=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volumes)
      REMOVE_VOLUMES=true
      shift
      ;;
    *)
      echo "Usage: $0 [--volumes]" >&2
      exit 1
      ;;
  esac
done

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

echo "Arrêt des services Docker recette..."
if [ "$REMOVE_VOLUMES" = true ]; then
  compose down --volumes
else
  compose down
fi

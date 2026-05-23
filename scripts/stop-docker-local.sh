#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

docker compose --env-file "$ROOT_DIR/.env.local" -f "$ROOT_DIR/docker-compose.local.yml" down

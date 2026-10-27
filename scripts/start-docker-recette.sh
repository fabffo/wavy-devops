#!/usr/bin/env bash
# Entrée historique : même configuration CORS et mêmes images que ./wavy.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/wavy" start recette "$@"

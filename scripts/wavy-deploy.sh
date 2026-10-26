#!/usr/bin/env bash
# Façade des composants DevOps existants ; aucune mutation par défaut.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 -B "$ROOT/preparation/https-msi/wavy_deploy.py" "$@"

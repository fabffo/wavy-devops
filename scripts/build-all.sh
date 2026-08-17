#!/usr/bin/env bash
# Reconstruit toutes les images Wavy pour local et recette.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
for env in local recette; do
  info "Reconstruction de toutes les images ($env)..."
  compose "$env" build
  success " Images reconstruites pour $env."
done

#!/usr/bin/env bash
# Reconstruit toutes les images de l'environnement local.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
info "Reconstruction des images locales..."
compose local build
success " Images locales reconstruites."

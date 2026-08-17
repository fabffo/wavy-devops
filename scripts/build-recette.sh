#!/usr/bin/env bash
# Reconstruit toutes les images de l'environnement recette.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
info "Reconstruction des images recette..."
compose recette build
success " Images recette reconstruites."

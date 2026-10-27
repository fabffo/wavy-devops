#!/usr/bin/env bash
# Télécharge et vérifie toutes les images de l'environnement recette.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
info "Téléchargement et vérification des images recette..."
compose recette build
success " Images recette validées et disponibles."

#!/usr/bin/env bash
# Reconstruit puis redémarre tous les services applicatifs recette sans recréer les bases.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
services=(
  wavy-socle-api-recette
  wavy-tiers-api-recette
  wavy-contrats-api-recette
  wavy-factures-api-recette
  wavy-tresorerie-api-recette
  wavy-gateway-recette
  wavy-socle-front-recette
  wavy-tiers-front-recette
  wavy-contrats-front-recette
  wavy-factures-front-recette
  wavy-tresorerie-front-recette
  wavy-pwa-recette
  wavy-erp-shell-recette
)

info "Reconstruction de toutes les images applicatives recette..."
compose recette build "${services[@]}"
info "Redémarrage des services applicatifs recette, bases PostgreSQL conservées..."
compose recette up -d --force-recreate "${services[@]}"
success " Services applicatifs recette redémarrés."
info "Statut actuel :"
"$SCRIPT_DIR/status.sh"

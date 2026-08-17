#!/usr/bin/env bash
# Nettoie Docker sans supprimer les volumes de données Wavy.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
info "Suppression des images inutilisées..."
docker image prune -f

info "Suppression du cache de build Docker..."
docker builder prune -f

unused_volumes="$(docker volume ls -qf dangling=true | grep -Ev '(postgres|db|wavy.*(socle|tiers|contrats|factures)|socle|tiers|contrats|factures)' || true)"
if [[ -z "$unused_volumes" ]]; then
  success " Aucun volume inutilisé non sensible à supprimer."
else
  warn "Volumes inutilisés non identifiés comme bases de données :"
  printf '%s\n' "$unused_volumes"
  if confirm "Supprimer ces volumes inutilisés ?"; then
    printf '%s\n' "$unused_volumes" | xargs -r docker volume rm
    success " Volumes inutilisés supprimés."
  else
    warn "Suppression des volumes annulée."
  fi
fi

success " Nettoyage terminé. Les volumes de bases Wavy n'ont pas été supprimés."

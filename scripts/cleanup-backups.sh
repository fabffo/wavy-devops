#!/usr/bin/env bash
# Rétention conservatrice des sauvegardes PostgreSQL locales Wavy.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

usage() { printf 'Usage : %s [--dry-run|--execute]\n' "$0" >&2; }
mode="${1:---dry-run}"
[[ "$#" -le 1 ]] || { usage; exit 2; }
case "$mode" in --dry-run|--execute) ;; *) usage; exit 2 ;; esac

retention_days="${WAVY_BACKUP_RETENTION_DAYS:-14}"
retention_count="${WAVY_BACKUP_RETENTION_COUNT:-20}"
[[ "$retention_days" =~ ^[0-9]+$ ]] || die "WAVY_BACKUP_RETENTION_DAYS doit être un entier positif ou nul."
[[ "$retention_count" =~ ^[1-9][0-9]*$ ]] || die "WAVY_BACKUP_RETENTION_COUNT doit être un entier strictement positif."

backup_root="$ROOT_DIR/backups"
[[ -d "$backup_root" ]] || { success " Aucun répertoire de sauvegarde à nettoyer."; exit 0; }
mapfile -t candidates < <(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' \
  | awk '/^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}(-[0-9]{2})?$/' | sort -r)

deleted=0
kept=0
now="$(date +%s)"
for index in "${!candidates[@]}"; do
  name="${candidates[$index]}"
  path="$backup_root/$name"
  modified="$(stat -c %Y -- "$path")"
  age_days=$(((now - modified) / 86400))
  if ((index < retention_count || age_days <= retention_days)); then
    kept=$((kept + 1))
    continue
  fi
  if [[ "$mode" == --dry-run ]]; then
    info "DRY-RUN suppression sauvegarde reconnue : $path (âge=${age_days}j)"
  else
    info "Suppression sauvegarde reconnue : $path (âge=${age_days}j)"
    find "$path" -mindepth 1 -delete
    rmdir -- "$path"
  fi
  deleted=$((deleted + 1))
done
success " Nettoyage sauvegardes : mode=$mode candidats=${#candidates[@]} conservés=$kept supprimables=$deleted rétention=${retention_days}j/${retention_count} dernières"

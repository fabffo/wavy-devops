#!/usr/bin/env bash
# Restaure une base PostgreSQL Wavy depuis backups/.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_docker
env="$(env_name)"
backup_root="$ROOT_DIR/backups"
[[ -d "$backup_root" ]] || die "Aucun dossier backups trouvé : $backup_root"

mapfile -t backups < <(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)
[[ "${#backups[@]}" -gt 0 ]] || die "Aucune sauvegarde disponible."

echo "Sauvegarde à restaurer ($env) :"
select backup in "${backups[@]}"; do
  [[ -n "$backup" ]] && break
done

echo "Base à restaurer :"
select db in socle tiers contrats factures tresorerie; do
  [[ -n "$db" ]] && break
done

dump="$backup_root/$backup/${db}.dump"
[[ -f "$dump" ]] || die "Dump introuvable : $dump"

container="$(db_container "$db" "$env")"
user="$(db_user "$db" "$env")"
name="$(db_name "$db" "$env")"
ensure_container_running "$container"

warn "La restauration va remplacer le contenu de $name dans $container."
confirm "Confirmer la restauration de $dump ?" || die "Restauration annulée."

info "Restauration de $db depuis $dump..."
docker exec -i "$container" pg_restore -U "$user" -d "$name" --clean --if-exists --no-owner < "$dump"
success " Base $db restaurée dans l'environnement $env."

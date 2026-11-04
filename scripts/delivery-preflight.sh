#!/usr/bin/env bash
# Precontroles partages par la livraison complete, sans sauvegarde ni remplacement.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
umask 077
[[ $# == 1 && ( $1 == recette || $1 == preprod ) ]] || die 'Environnement de livraison invalide.'
env="$1"
if [[ "$env" == preprod ]]; then
  source "$SCRIPT_DIR/_preprod.sh"
  preprod_host_guard
  "$SCRIPT_DIR/validate-preprod-config.sh"
  python3 "$SCRIPT_DIR/delivery_check.py" promotion
  preprod_backup_operation_lock
  preprod_release_checks
  for db in socle tiers contrats factures tresorerie; do
    preprod_container_guard "$(db_container "$db" preprod)" "$db-postgres"
  done
  for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
    preprod_container_guard "$(service_name "$component" preprod)" "$(service_name "$component" preprod)"
    preprod_verify_image "$component" "$(component_version preprod "$component")" "$(component_digest preprod "$component")"
  done
  # Reprise : controler le demarrage courant, sans relancer de migration.
  for component in socle-api tiers-api contrats-api factures-api tresorerie-api; do
    service="$(service_name "$component" preprod)"
    since="$(docker inspect -f '{{.State.StartedAt}}' "$service")"
    [[ -n "$since" ]] || die "Etat de demarrage illisible : $component"
    preprod_migration_logs "$service" "$since" || die "Reprise refusee : migrations non valides pour $component"
  done
  preprod_compose config --quiet >/dev/null 2>&1 || die 'Compose PREPROD invalide avant sauvegarde.'
  exit 0
fi
# Un seul rapport de tous les prérequis avant verrou, pull, backup ou provisionnement.
python3 -B "$SCRIPT_DIR/delivery_check.py" diagnose
[[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || die 'Daemon distant interdit.'
[[ "$(env_value recette WAVY_INSTALL_HOSTNAME '')" == "$(hostname -s)" ]] || die 'Configurer WAVY_INSTALL_HOSTNAME sur la VM cible ; installation refusée sur cet hôte.'
[[ ! -f "$ROOT_DIR/deployments/recette-https-reservation.json" && ! -f "$HOME/.local/state/wavy/recettelocal/runtime-info.json" ]] || die 'Session MSI réservée : utiliser ./wavy local.'
require_docker
require_command python3
[[ "$(docker context inspect --format '{{.Endpoints.docker.Host}}')" == unix:///var/run/docker.sock ]] || die 'Socket Docker système local requis.'
recette_operation_lock
# Les historiques des 13 composants RECETTE sont enrichis par les déploiements.
# Exclusions exactes : aucun autre fichier de versions/ n'échappe au contrôle.
delivery_paths=(wavy scripts docker ':(glob)docker-compose*.yml' versions)
for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
  delivery_paths+=(":(exclude,literal)versions/history/recette/$component.tsv")
done
delivery_status="$(git -C "$ROOT_DIR" status --porcelain --untracked-files=all -- "${delivery_paths[@]}")" \
  || die 'Impossible de vérifier la synchronisation Git de la livraison.'
[[ -z "$delivery_status" ]] || die 'Livraison non synchronisée avec Git ; publier puis synchroniser le dépôt avant installation.'
timeout="$(env_value recette WAVY_INSTALL_WAIT_SECONDS 600)"
[[ "$timeout" =~ ^[1-9][0-9]*$ && "$timeout" -ge 180 && "$timeout" -le 3600 ]] || die 'Délai attendu entre 180 et 3600 secondes.'
python3 "$SCRIPT_DIR/delivery_check.py" preflight
python3 "$SCRIPT_DIR/release_images.py" verify recette
python3 "$SCRIPT_DIR/delivery_check.py" storage

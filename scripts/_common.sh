#!/usr/bin/env bash
# Fonctions communes pour les scripts d'administration Wavy.
# Ce fichier est source par les scripts publics du dossier scripts/.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

info() { printf "${BLUE}==>${NC} %s\n" "$*"; }
success() { printf "${GREEN}OK${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}WARN${NC} %s\n" "$*"; }
error() { printf "${RED}ERREUR${NC} %s\n" "$*" >&2; }

die() {
  error "$*"
  exit 1
}

confirm() {
  local message="$1"
  local answer
  read -r -p "$message [y/N] " answer
  [[ "$answer" =~ ^[Yy]$ ]]
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Commande introuvable : $1"
}

require_docker() {
  require_command docker
  docker info >/dev/null 2>&1 || die "Docker n'est pas disponible ou le daemon n'est pas démarré."
  docker compose version >/dev/null 2>&1 || die "Docker Compose v2 n'est pas disponible."
}

env_name() {
  case "${WAVY_ENV:-recette}" in
    local|recette|preprod) printf '%s\n' "${WAVY_ENV:-recette}" ;;
    *) die "WAVY_ENV doit valoir 'local', 'recette' ou 'preprod'." ;;
  esac
}

compose_file() {
  local env="$1"
  printf '%s/docker-compose.%s.yml\n' "$ROOT_DIR" "$env"
}

env_file() {
  local env="$1"
  printf '%s/.env.%s\n' "$ROOT_DIR" "$env"
}

versions_file() {
  local env="$1"
  printf '%s/versions/%s.env\n' "$ROOT_DIR" "$env"
}

digests_file() {
  local env="$1"
  printf '%s/versions/%s.digests\n' "$ROOT_DIR" "$env"
}

manifest_value() {
  local file="$1" key="$2" default_value="${3:-}"
  local value
  value="$(awk -F= -v key="$key" '$1 == key { value=$0; sub(/^[^=]*=/, "", value); print value }' "$file" 2>/dev/null | tail -n 1)"
  printf '%s\n' "${value:-$default_value}"
}

component_key() {
  printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_'
}

deployment_mode() {
  local env="$1" component="$2"
  case "$env/$component" in
    recette/tresorerie-api|recette/gateway|recette/tresorerie-front|recette/socle-front|recette/tiers-front|recette/contrats-front|recette/factures-front|recette/pwa) printf 'IMAGE\n' ;;
    *) printf 'SOURCE\n' ;;
  esac
}

component_version() {
  local env="$1" component="$2"
  manifest_value "$(versions_file "$env")" "$(component_key "$component")_VERSION"
}

component_digest() {
  local env="$1" component="$2"
  manifest_value "$(digests_file "$env")" "$(component_key "$component")_DIGEST"
}

validated_history_file() {
  local env="$1" component="$2"
  [[ "$env" =~ ^[a-z0-9-]+$ ]] || die "Environnement invalide pour l'historique : $env"
  [[ "$component" =~ ^[a-z0-9-]+$ ]] || die "Composant invalide pour l'historique : $component"
  printf '%s/versions/history/%s/%s.tsv\n' "$ROOT_DIR" "$env" "$component"
}

get_validated_digest() {
  local env="$1" component="$2" version="$3" file digest conflicts
  file="$(validated_history_file "$env" "$component")"
  [[ -f "$file" ]] || die "Historique de versions validées introuvable : $file"
  digest="$(awk -F '\t' -v version="$version" 'NR > 1 && $1 == version {print $2}' "$file" | head -n 1)"
  [[ -n "$digest" ]] || die "Aucun digest validé pour $env/$component version $version."
  conflicts="$(awk -F '\t' -v version="$version" -v digest="$digest" 'NR > 1 && $1 == version && $2 != digest {print $2}' "$file")"
  [[ -z "$conflicts" ]] || die "Historique incohérent : plusieurs digests pour $env/$component version $version."
  printf '%s\n' "$digest"
}

record_validated_image() {
  local env="$1" component="$2" version="$3" digest="$4" commit="${5:-indisponible}"
  local file existing
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || die "Digest OCI invalide : $digest"
  file="$(validated_history_file "$env" "$component")"
  mkdir -p "$(dirname "$file")"
  exec {history_lock_fd}>>"$file"
  flock "$history_lock_fd"
  if [[ ! -s "$file" ]]; then
    printf 'version\tdigest\tcommit\tdate_validation\n' >> "$file"
  fi
  existing="$(awk -F '\t' -v version="$version" 'NR > 1 && $1 == version {print $2; exit}' "$file")"
  if [[ -n "$existing" ]]; then
    [[ "$existing" == "$digest" ]] || die "Version $version déjà validée avec un digest différent : $existing"
    flock -u "$history_lock_fd"
    return 0
  fi
  printf '%s\t%s\t%s\t%s\n' "$version" "$digest" "${commit:-indisponible}" "$(date -Is)" >> "$file"
  flock -u "$history_lock_fd"
}

component_image() {
  local env="$1" component="$2" version="$3"
  local registry
  registry="$(manifest_value "$(versions_file "$env")" WAVY_IMAGE_REGISTRY)"
  [[ -n "$registry" ]] || die "WAVY_IMAGE_REGISTRY est vide dans $(versions_file "$env")."
  printf '%s/wavy-%s:%s\n' "${registry%/}" "$component" "$version"
}

image_repo_digest() {
  local image="$1" repository="${1%:*}" repo_digest
  repo_digest="$(docker image inspect "$image" --format '{{range .RepoDigests}}{{println .}}{{end}}' 2>/dev/null \
    | awk -F@ -v repository="$repository" '$1 == repository {print $2; exit}')"
  [[ -n "$repo_digest" ]] || die "Aucun RepoDigest trouvé pour $image."
  printf '%s\n' "$repo_digest"
}

verify_image_digest() {
  local image="$1" expected_digest="$2" actual_digest
  actual_digest="$(image_repo_digest "$image")"
  if [[ -n "$expected_digest" && "$actual_digest" != "$expected_digest" ]]; then
    die "Digest refusé pour $image : attendu=$expected_digest obtenu=$actual_digest"
  fi
  printf '%s\n' "$actual_digest"
}

project_name() {
  local env="$1"
  env_value "$env" COMPOSE_PROJECT_NAME "wavy-$env"
}

compose() {
  local env="$1"
  local env_file_path compose_file_path versions_file_path
  local -a env_args
  env_file_path="$(env_file "$env")"
  versions_file_path="$(versions_file "$env")"
  compose_file_path="$(compose_file "$env")"
  [[ -f "$compose_file_path" ]] || die "Fichier compose introuvable : $compose_file_path"
  [[ -f "$env_file_path" ]] || die "Fichier d'environnement introuvable : $env_file_path"
  env_args=(--env-file "$env_file_path")
  [[ ! -f "$versions_file_path" ]] || env_args+=(--env-file "$versions_file_path")
  docker compose "${env_args[@]}" -p "$(project_name "$env")" -f "$compose_file_path" "${@:2}"
}

current_compose() {
  compose "$(env_name)" "$@"
}

service_name() {
  local logical="$1"
  local env="${2:-$(env_name)}"
  case "$logical" in
    socle-api) printf 'wavy-socle-api-%s\n' "$env" ;;
    tiers-api) printf 'wavy-tiers-api-%s\n' "$env" ;;
    contrats-api) printf 'wavy-contrats-api-%s\n' "$env" ;;
    factures-api) printf 'wavy-factures-api-%s\n' "$env" ;;
    tresorerie-api) printf 'wavy-tresorerie-api-%s\n' "$env" ;;
    gateway) printf 'wavy-gateway-%s\n' "$env" ;;
    socle-front) printf 'wavy-socle-front-%s\n' "$env" ;;
    tiers-front) printf 'wavy-tiers-front-%s\n' "$env" ;;
    contrats-front) printf 'wavy-contrats-front-%s\n' "$env" ;;
    factures-front) printf 'wavy-factures-front-%s\n' "$env" ;;
    tresorerie-front) printf 'wavy-tresorerie-front-%s\n' "$env" ;;
    pwa) printf 'wavy-pwa-%s\n' "$env" ;;
    erp-shell) printf 'wavy-erp-shell-%s\n' "$env" ;;
    *) die "Service logique inconnu : $logical" ;;
  esac
}

db_container() {
  local db="$1"
  local env="${2:-$(env_name)}"
  case "$db" in
    socle) printf 'socle-db-%s\n' "$env" ;;
    tiers) printf 'tiers-db-%s\n' "$env" ;;
    contrats) printf 'contrats-db-%s\n' "$env" ;;
    factures) printf 'factures-db-%s\n' "$env" ;;
    tresorerie) printf 'tresorerie-db-%s\n' "$env" ;;
    *) die "Base inconnue : $db" ;;
  esac
}

db_user() {
  local db="$1"
  local env="${2:-$(env_name)}"
  case "$db" in
    socle) env_value "$env" WAVY_SOCLE_DB_USERNAME socle_user ;;
    tiers) env_value "$env" WAVY_TIERS_DB_USER tiers_user ;;
    contrats) env_value "$env" WAVY_CONTRATS_DB_USER contrats_user ;;
    factures) env_value "$env" WAVY_FACTURES_DB_USER factures_user ;;
    tresorerie) env_value "$env" WAVY_TRESORERIE_DB_USER tresorerie_user ;;
    *) die "Base inconnue : $db" ;;
  esac
}

db_name() {
  local db="$1"
  local env="${2:-$(env_name)}"
  case "$db" in
    socle) env_value "$env" WAVY_SOCLE_DB_NAME wavy_socle_db ;;
    tiers) env_value "$env" WAVY_TIERS_DB_NAME wavy_tiers_db ;;
    contrats) env_value "$env" WAVY_CONTRATS_DB_NAME wavy_contrats_db ;;
    factures) env_value "$env" WAVY_FACTURES_DB_NAME wavy_factures_db ;;
    tresorerie) env_value "$env" WAVY_TRESORERIE_DB_NAME wavy_tresorerie_db ;;
    *) die "Base inconnue : $db" ;;
  esac
}

env_value() {
  local env="$1"
  local key="$2"
  local default_value="$3"
  local file value
  file="$(env_file "$env")"
  value="$(awk -F= -v key="$key" '$1 == key { value=$0; sub(/^[^=]*=/, "", value); print value }' "$file" 2>/dev/null | tail -n 1)"
  printf '%s\n' "${value:-$default_value}"
}

ensure_container_running() {
  local container="$1"
  docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null | grep -q true \
    || die "Le conteneur $container n'est pas démarré."
}

restart_service() {
  local logical="$1"
  local env="${2:-$(env_name)}"
  local service
  service="$(service_name "$logical" "$env")"
  require_docker
  info "Reconstruction de l'image $service ($env)..."
  compose "$env" build "$service"
  success " Image reconstruite : $service"
  info "Recréation du conteneur $service ($env), dépendances conservées..."
  compose "$env" up -d --no-deps --force-recreate "$service"
  success " Service redémarré avec la nouvelle image : $service"
  info "Logs récents de $service..."
  compose "$env" logs --tail="${LOG_LINES:-80}" "$service" || true
  success " $service est disponible. Consultez ./scripts/status.sh pour le statut complet."
}

list_wavy_containers() {
  docker ps -a --filter "name=wavy-" --filter "name=socle-db-" --filter "name=tiers-db-" \
    --filter "name=contrats-db-" --filter "name=factures-db-" \
    --filter "name=tresorerie-db-" \
    --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
}

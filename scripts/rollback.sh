#!/usr/bin/env bash
# Rollback applicatif contrôlé en mode SOURCE (commit) ou IMAGE (version).
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

usage() {
  cat >&2 <<EOF
Usage : $0 <local|recette> <composant> <commit-ou-version-cible> [--yes]

En mode SOURCE, la cible est un commit Git. En mode IMAGE, la cible est un tag versionné.
EOF
}

started_at="$(date -Is)"
result=KO
env="${1:-inconnu}"
component="${2:-inconnu}"
target_input="${3:-indisponible}"
mode=indisponible
commit=indisponible
version=non-versionnee
digest=''
system_user="$(id -un)"
journal_file="$ROOT_DIR/deployments/history.tsv"
temp_dir=''
worktree=''

finish() {
  local exit_code=$?
  if [[ -n "$worktree" && -d "$worktree" && -n "${source_repo:-}" ]]; then
    git -C "$source_repo" worktree remove --force "$worktree" >/dev/null 2>&1 || true
  fi
  if [[ -n "$temp_dir" && -d "$temp_dir" ]]; then
    find "$temp_dir" -mindepth 1 -maxdepth 1 -type f -delete 2>/dev/null || true
    rmdir "$temp_dir" 2>/dev/null || true
  fi
  mkdir -p "$(dirname "$journal_file")"
  if [[ -f "$journal_file" ]] && [[ "$(head -n 1 "$journal_file")" == $'date\tenvironnement\tcomposant\tcommit\tversion\tresultat\tutilisateur' ]]; then
    awk -F '\t' 'BEGIN {OFS="\t"; print "date","action","environnement","composant","mode","commit","version","digest","resultat","utilisateur"}
      NR > 1 {print $1,"DEPLOY",$2,$3,"SOURCE",$4,$5,"",$6,$7}' "$journal_file" > "$journal_file.migrate"
    mv "$journal_file.migrate" "$journal_file"
  elif [[ ! -f "$journal_file" ]]; then
    printf 'date\taction\tenvironnement\tcomposant\tmode\tcommit\tversion\tdigest\tresultat\tutilisateur\n' > "$journal_file"
  fi
  printf '%s\tROLLBACK\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -Is)" "$env" "$component" "$mode" "$commit" "$version" "$digest" "$result" "$system_user" >> "$journal_file"
  exit "$exit_code"
}
trap finish EXIT

[[ "$#" -ge 3 && "$#" -le 4 ]] || { usage; exit 2; }
assume_yes=false
if [[ "$#" -eq 4 ]]; then
  [[ "$4" == --yes ]] || { usage; die "Option inconnue : $4"; }
  assume_yes=true
fi
case "$env" in
  local|recette) ;;
  preprod) die "Le rollback préproduction reste volontairement désactivé pendant cette étape." ;;
  *) usage; die "Environnement invalide : $env" ;;
esac
case "$component" in
  socle-api|tiers-api|contrats-api|factures-api|tresorerie-api|gateway|socle-front|tiers-front|contrats-front|factures-front|tresorerie-front|pwa|erp-shell) ;;
  *) usage; die "Composant inconnu : $component" ;;
esac

mode="$(deployment_mode "$env" "$component")"
service="$(service_name "$component" "$env")"
is_api=false
has_database=false
case "$component" in
  socle-api|tiers-api|contrats-api|factures-api|tresorerie-api) is_api=true; has_database=true ;;
  gateway) is_api=true ;;
esac
require_docker

current_image_id="$(docker inspect -f '{{.Image}}' "$service" 2>/dev/null || true)"
current_image_name="$(docker inspect -f '{{.Config.Image}}' "$service" 2>/dev/null || true)"
[[ -n "$current_image_id" ]] || die "Aucune image active identifiable pour $service."

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/wavy-rollback.XXXXXX")"
override_file="$temp_dir/compose.rollback.yml"

if [[ "$mode" == IMAGE ]]; then
  version="$target_input"
  [[ "$version" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "Version IMAGE invalide : $version"
  target_image="$(component_image "$env" "$component" "$version")"
  expected_digest="$(get_validated_digest "$env" "$component" "$version")"
  info "Vérification de l'existence de $target_image..."
  docker manifest inspect "$target_image" >/dev/null || die "Version distante introuvable ou inaccessible : $target_image"
  docker pull "$target_image"
  digest="$(verify_image_digest "$target_image" "$expected_digest")"
  commit="$(docker image inspect "$target_image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
  target_image_id="$(docker image inspect -f '{{.Id}}' "$target_image")"
  {
    printf 'services:\n'
    printf '  %s:\n' "$service"
    printf '    image: "%s"\n' "$target_image"
  } > "$override_file"

  cat <<EOF

ROLLBACK APPLICATION — MODE IMAGE
Composant        : $component
Environnement    : $env
Image actuelle   : $current_image_name
ID actuel        : $current_image_id
Version cible    : $version
Image cible      : $target_image
Digest cible     : $digest

La base PostgreSQL ne sera jamais restaurée automatiquement.
EOF
  [[ "$current_image_id" != "$target_image_id" ]] || warn "La version cible correspond déjà exactement à l'image active."
else
  source_repo="$ROOT_DIR/../wavy-$component"
  [[ -d "$source_repo/.git" ]] || die "Dépôt source introuvable : $source_repo"
  git_changes="$(git -C "$source_repo" status --porcelain)"
  [[ -z "$git_changes" ]] || die "Rollback bloqué : le dépôt source principal doit être propre."
  origin_commit="$(git -C "$source_repo" rev-parse --short HEAD)"
  git -C "$source_repo" cat-file -e "${target_input}^{commit}" 2>/dev/null || die "Le commit cible n'existe pas : $target_input"
  commit="$(git -C "$source_repo" rev-parse --short "${target_input}^{commit}")"
  worktree="$temp_dir/source"
  git -C "$source_repo" worktree add --detach "$worktree" "$commit"
  {
    printf 'services:\n'
    printf '  %s:\n' "$service"
    printf '    build:\n'
    printf '      context: "%s"\n' "$worktree"
    [[ "$component" != pwa ]] || printf '      dockerfile: "%s/docker/wavy-pwa.Dockerfile"\n' "$ROOT_DIR"
  } > "$override_file"
  cat <<EOF

ROLLBACK APPLICATION — MODE SOURCE
Composant        : $component
Environnement    : $env
Commit origine   : $origin_commit
Commit cible     : $commit

La base PostgreSQL ne sera jamais restaurée automatiquement.
EOF
fi

if ! $assume_yes; then
  read -r -p "Confirmer le rollback applicatif ? [y/N] " answer
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then result=ANNULE; info "Rollback annulé sans modification."; exit 0; fi
fi

minimum_free_kb="${WAVY_ROLLBACK_MIN_FREE_KB:-1048576}"
available_kb="$(df -Pk "$ROOT_DIR" | awk 'NR == 2 {print $4}')"
((available_kb >= minimum_free_kb)) || die "Espace disque insuffisant."
if $has_database; then
  info "Sauvegarde pré-rollback des bases $env..."
  WAVY_ENV="$env" WAVY_BACKUP_COMPONENT="$component" WAVY_BACKUP_VERSION="$version" "$SCRIPT_DIR/backup-db.sh"
  warn "Cette sauvegarde ne sera pas restaurée automatiquement."
fi

cached_image="wavy-rollback-cache/${env}-${component}:before-rollback-$(date +%Y%m%dT%H%M%S)"
docker image tag "$current_image_id" "$cached_image"
success " Image avant rollback conservée : $cached_image"

rollback_compose() {
  local -a env_args=(--env-file "$(env_file "$env")")
  [[ ! -f "$(versions_file "$env")" ]] || env_args+=(--env-file "$(versions_file "$env")")
  docker compose "${env_args[@]}" -p "$(project_name "$env")" \
    -f "$(compose_file "$env")" -f "$override_file" "$@"
}

if [[ "$mode" == SOURCE ]]; then
  info "Construction isolée de $service depuis $commit..."
  rollback_compose build "$service"
else
  info "Mode IMAGE : aucun build Docker ne sera exécuté."
fi
info "Recréation ciblée de $service sans redémarrer ses dépendances..."
rollback_compose up -d --no-deps --force-recreate --pull never "$service"

attempts="${WAVY_ROLLBACK_HEALTH_ATTEMPTS:-60}"
interval="${WAVY_ROLLBACK_HEALTH_INTERVAL_SECONDS:-2}"
for ((attempt = 1; attempt <= attempts; attempt++)); do
  status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$service" 2>/dev/null || printf absent)"
  [[ "$status" == healthy || "$status" == running ]] && break
  [[ "$status" != unhealthy && "$attempt" -lt "$attempts" ]] || die "$component n'est pas disponible ($status)."
  sleep "$interval"
done
success " $component disponible ($status)"

if [[ "$is_api" == false ]]; then
  case "$component" in
    socle-front) front_port="$(env_value "$env" WAVY_SOCLE_FRONT_HOST_PORT "$([[ "$env" == recette ]] && echo 24200 || echo 14200)")" ;;
    tiers-front) front_port="$(env_value "$env" WAVY_TIERS_FRONT_HOST_PORT "$([[ "$env" == recette ]] && echo 24201 || echo 14201)")" ;;
    contrats-front) front_port="$(env_value "$env" WAVY_CONTRATS_FRONT_HOST_PORT "$([[ "$env" == recette ]] && echo 24202 || echo 14202)")" ;;
    factures-front) front_port="$(env_value "$env" WAVY_FACTURES_FRONT_HOST_PORT "$([[ "$env" == recette ]] && echo 24203 || echo 14203)")" ;;
    pwa) front_port="$(env_value "$env" WAVY_PWA_HOST_PORT "$([[ "$env" == recette ]] && echo 24204 || echo 14204)")" ;;
    tresorerie-front) front_port="$(env_value "$env" WAVY_TRESORERIE_FRONT_HOST_PORT "$([[ "$env" == recette ]] && echo 24206 || echo 14206)")" ;;
    erp-shell) front_port="$(env_value "$env" WAVY_ERP_SHELL_HOST_PORT "$([[ "$env" == recette ]] && echo 24207 || echo 14207)")" ;;
  esac
  front_url="http://localhost:${front_port}/"
  front_ok=false
  for attempt in {1..30}; do
    if curl -fsS --max-time 5 "$front_url" >/dev/null 2>&1; then front_ok=true; break; fi
    ((attempt < 30)) && sleep 2
  done
  $front_ok || die "$component ne répond pas sur $front_url."
  success " $component répond sur $front_url"
fi

if $has_database; then
  recent_logs="$(compose "$env" logs --no-color --since "$started_at" "$service" 2>&1 || true)"
  if printf '%s\n' "$recent_logs" | grep -Eqi 'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException'; then
    error "Une erreur Flyway a été détectée après rollback."
    printf '%s\n' "$recent_logs" | grep -Ei 'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException' >&2 || true
    exit 1
  fi
  success " Aucune erreur Flyway ciblée détectée"
fi
if $is_api || [[ "$mode" == IMAGE ]]; then
  "$SCRIPT_DIR/healthcheck.sh" "$env"
  "$SCRIPT_DIR/smoke-test.sh" "$env"
fi

if [[ "$mode" == IMAGE ]]; then
  [[ "$(docker inspect -f '{{.Image}}' "$service")" == "$target_image_id" ]] || die "Le conteneur n'exécute pas l'image cible."
fi
result=OK
success " Rollback $env/$component terminé : mode=$mode commit=$commit version=$version digest=${digest:-indisponible}"
warn "Aucun rollback de base de données n'a été exécuté."

#!/usr/bin/env bash
# Déploiement contrôlé d'un composant Wavy en mode SOURCE ou IMAGE.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

usage() {
  cat >&2 <<EOF
Usage : $0 <local|recette> <composant> [--allow-dirty]

Composants :
  socle-api tiers-api contrats-api factures-api tresorerie-api gateway
  socle-front tiers-front contrats-front factures-front tresorerie-front
  pwa erp-shell
EOF
}

started_at="$(date -Is)"
result=KO
env="${1:-inconnu}"
component="${2:-inconnu}"
mode=indisponible
commit=indisponible
version=non-versionnee
digest=''
system_user="$(id -un)"
journal_file="$ROOT_DIR/deployments/history.tsv"

write_journal() {
  local legacy_header=$'date\tenvironnement\tcomposant\tcommit\tversion\tresultat\tutilisateur'
  local header=$'date\taction\tenvironnement\tcomposant\tmode\tcommit\tversion\tdigest\tresultat\tutilisateur'
  mkdir -p "$(dirname "$journal_file")"
  if [[ -f "$journal_file" ]] && [[ "$(head -n 1 "$journal_file")" == "$legacy_header" ]]; then
    awk -F '\t' 'BEGIN {OFS="\t"; print "date","action","environnement","composant","mode","commit","version","digest","resultat","utilisateur"}
      NR > 1 {print $1,"DEPLOY",$2,$3,"SOURCE",$4,$5,"",$6,$7}' "$journal_file" > "$journal_file.migrate"
    mv "$journal_file.migrate" "$journal_file"
  elif [[ ! -f "$journal_file" ]]; then
    printf '%s\n' "$header" > "$journal_file"
  fi
  printf '%s\tDEPLOY\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$(date -Is)" "$env" "$component" "$mode" "$commit" "$version" "$digest" "$result" "$system_user" >> "$journal_file"
}
trap write_journal EXIT

[[ "$#" -ge 2 && "$#" -le 3 ]] || { usage; exit 2; }
allow_dirty=false
if [[ "$#" -eq 3 ]]; then
  [[ "$3" == --allow-dirty ]] || { usage; die "Option inconnue : $3"; }
  allow_dirty=true
fi

case "$env" in
  local|recette) ;;
  preprod) die "Le déploiement préproduction reste volontairement désactivé pendant cette étape." ;;
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
info "Mode de déploiement : $mode"

minimum_free_kb="${WAVY_DEPLOY_MIN_FREE_KB:-1048576}"
[[ "$minimum_free_kb" =~ ^[1-9][0-9]*$ ]] || die "WAVY_DEPLOY_MIN_FREE_KB doit être un entier positif."
available_kb="$(df -Pk "$ROOT_DIR" | awk 'NR == 2 {print $4}')"
[[ "$available_kb" =~ ^[0-9]+$ ]] || die "Impossible de mesurer l'espace disque disponible."
((available_kb >= minimum_free_kb)) || die "Espace disque insuffisant : ${available_kb} Kio disponibles, ${minimum_free_kb} Kio requis."
success " Espace disque disponible : ${available_kb} Kio"
require_docker

if [[ "$mode" == SOURCE ]]; then
  source_repo="$ROOT_DIR/../wavy-$component"
  [[ -d "$source_repo/.git" ]] || die "Dépôt source introuvable : $source_repo"
  commit="$(git -C "$source_repo" rev-parse --short HEAD)"
  branch="$(git -C "$source_repo" branch --show-current)"
  git_changes="$(git -C "$source_repo" status --porcelain)"
  info "Source : $source_repo"
  info "Git : branche ${branch:-detached}, commit $commit"
  if [[ -n "$git_changes" ]]; then
    warn "Le dépôt $component contient des modifications locales :"
    printf '%s\n' "$git_changes"
    $allow_dirty || die "Déploiement bloqué. Committer les changements ou utiliser explicitement --allow-dirty."
    warn "Contournement explicite activé : le build ne sera pas reproductible depuis le seul commit $commit."
  fi
  declared_version="$(component_version "$env" "$component")"
  [[ -z "$declared_version" ]] || version="$declared_version"
else
  $allow_dirty && die "--allow-dirty ne s'applique pas au mode IMAGE."
  require_command flock
  version="$(component_version "$env" "$component")"
  [[ -n "$version" ]] || die "Version vide pour $env/$component dans $(versions_file "$env")."
  expected_digest="$(component_digest "$env" "$component")"
  [[ -n "$expected_digest" ]] || die "Digest validé absent pour $env/$component dans $(digests_file "$env")."
  history_file="$(validated_history_file "$env" "$component")"
  if [[ -f "$history_file" ]] && awk -F '\t' -v version="$version" 'NR > 1 && $1 == version {found=1} END {exit !found}' "$history_file"; then
    historical_digest="$(get_validated_digest "$env" "$component" "$version")"
    [[ "$historical_digest" == "$expected_digest" ]] \
      || die "Version $version déjà enregistrée avec un digest différent : $historical_digest"
  fi
  image="$(component_image "$env" "$component" "$version")"
  info "Image distante : $image"
  info "Vérification de l'existence du tag distant..."
  docker manifest inspect "$image" >/dev/null || die "Image distante introuvable ou inaccessible : $image"
  info "Pull de l'image versionnée..."
  docker pull "$image"
  digest="$(verify_image_digest "$image" "$expected_digest")"
  commit="$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
  success " Digest vérifié : $digest"

  current_image_id="$(docker inspect -f '{{.Image}}' "$service" 2>/dev/null || true)"
  current_image_name="$(docker inspect -f '{{.Config.Image}}' "$service" 2>/dev/null || true)"
  [[ -n "$current_image_id" ]] || die "Aucune image active identifiable pour $service."
  rollback_tag="wavy-rollback-cache/${env}-${component}:before-deploy-$(date +%Y%m%dT%H%M%S)"
  docker image tag "$current_image_id" "$rollback_tag"
  info "Image active avant remplacement : $current_image_name ($current_image_id)"
  success " Tag de rollback créé : $rollback_tag"
fi

info "Version déclarée : $version"
if $has_database; then
  info "Sauvegarde préalable des bases $env..."
  WAVY_ENV="$env" WAVY_BACKUP_COMPONENT="$component" WAVY_BACKUP_VERSION="$version" "$SCRIPT_DIR/backup-db.sh"
fi

if [[ "$mode" == SOURCE ]]; then
  info "Construction de $service depuis le commit $commit..."
  compose "$env" build "$service"
else
  info "Mode IMAGE : aucun build Docker ne sera exécuté."
fi
info "Recréation ciblée de $service sans redémarrer ses dépendances..."
compose "$env" up -d --no-deps --force-recreate --pull never "$service"

wait_for_docker_health() {
  local container="$1" attempts="${WAVY_DEPLOY_HEALTH_ATTEMPTS:-60}" interval="${WAVY_DEPLOY_HEALTH_INTERVAL_SECONDS:-2}"
  local attempt status
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || printf absent)"
    if [[ "$status" == healthy || "$status" == running ]]; then
      success " $component disponible ($status, tentative $attempt/$attempts)"
      return 0
    fi
    [[ "$status" != unhealthy ]] || die "$component est déclaré unhealthy par Docker."
    ((attempt < attempts)) && sleep "$interval"
  done
  die "$component n'est pas disponible après $attempts tentatives."
}

front_url() {
  local variable default_port port
  case "$component" in
    socle-front) variable=WAVY_SOCLE_FRONT_HOST_PORT; default_port=$([[ "$env" == recette ]] && echo 24200 || echo 14200) ;;
    tiers-front) variable=WAVY_TIERS_FRONT_HOST_PORT; default_port=$([[ "$env" == recette ]] && echo 24201 || echo 14201) ;;
    contrats-front) variable=WAVY_CONTRATS_FRONT_HOST_PORT; default_port=$([[ "$env" == recette ]] && echo 24202 || echo 14202) ;;
    factures-front) variable=WAVY_FACTURES_FRONT_HOST_PORT; default_port=$([[ "$env" == recette ]] && echo 24203 || echo 14203) ;;
    pwa) variable=WAVY_PWA_HOST_PORT; default_port=$([[ "$env" == recette ]] && echo 24204 || echo 14204) ;;
    tresorerie-front) variable=WAVY_TRESORERIE_FRONT_HOST_PORT; default_port=$([[ "$env" == recette ]] && echo 24206 || echo 14206) ;;
    erp-shell) variable=WAVY_ERP_SHELL_HOST_PORT; default_port=$([[ "$env" == recette ]] && echo 24207 || echo 14207) ;;
  esac
  port="$(env_value "$env" "$variable" "$default_port")"
  printf 'http://localhost:%s/' "$port"
}

if $is_api; then
  wait_for_docker_health "$service"
  if $has_database; then
    info "Contrôle des logs Flyway récents..."
    recent_logs="$(compose "$env" logs --no-color --since "$started_at" "$service" 2>&1 || true)"
    if printf '%s\n' "$recent_logs" | grep -Eqi 'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException'; then
      error "Une erreur Flyway a été détectée dans les logs de $component."
      printf '%s\n' "$recent_logs" | grep -Ei 'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException' >&2 || true
      exit 1
    fi
    success " Aucune erreur Flyway ciblée détectée"
  fi
  "$SCRIPT_DIR/healthcheck.sh" "$env"
  "$SCRIPT_DIR/smoke-test.sh" "$env"
else
  url="$(front_url)"
  for attempt in {1..30}; do curl -fsS --max-time 5 "$url" >/dev/null 2>&1 && break; ((attempt < 30)) && sleep 2; done
  curl -fsS --max-time 5 "$url" >/dev/null || die "$component ne répond pas sur $url."
  success " $component répond sur $url"
fi

if [[ "$mode" == IMAGE ]]; then
  running_id="$(docker inspect -f '{{.Image}}' "$service")"
  [[ "$running_id" == "$(docker image inspect -f '{{.Id}}' "$image")" ]] || die "Le conteneur n'exécute pas l'image validée."
  record_validated_image "$env" "$component" "$version" "$digest" "$commit"
  success " Couple version/digest présent dans l'historique validé"
fi
result=OK
success " Déploiement $env/$component terminé : mode=$mode commit=$commit version=$version digest=${digest:-indisponible}"

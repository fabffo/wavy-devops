#!/usr/bin/env bash
# Fonctions exclusivement PREPROD ; aucun effet lors du source.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
preprod_value() { python3 "$SCRIPT_DIR/preprod_config.py" value "$ROOT_DIR/.env.preprod" "$1"; }
preprod_compose() { python3 "$SCRIPT_DIR/preprod_config.py" compose "$ROOT_DIR/.env.preprod" "$@"; }
# Le backup hérite du descripteur 9 de release/validate-runtime, sans rouvrir
# le fichier (ce qui créerait un verrou concurrent avec son propre parent).
preprod_backup_operation_lock() {
  local lock="$ROOT_DIR/deployments/preprod.lock"
  require_command flock
  mkdir -p "$ROOT_DIR/deployments"
  if [[ ! /proc/$$/fd/9 -ef "$lock" ]]; then
    exec 9>"$lock"
  fi
  flock -n 9 || die 'Une opération PREPROD est déjà en cours.'
}
preprod_host_guard() {
  [[ "$(hostname -s)" == wavy-preprod ]] || die 'Opération réservée à la VM wavy-preprod ; refus sur ce poste.'
  [[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || die 'Overrides Docker distants interdits.'
  local endpoint
  endpoint="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
  [[ "$endpoint" == unix:///var/run/docker.sock ]] || die 'Le daemon Docker local système est requis.'
  require_docker
}
preprod_container_guard() {
  local container="$1" expected_service="$2"
  [[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$container")" == wavy-preprod ]] || die 'Conteneur hors projet PREPROD.'
  [[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$container")" == "$expected_service" ]] || die 'Service Docker inattendu.'
  ensure_container_running "$container"
}
preprod_verify_image() {
  local component="$1" version="$2" expected="$3" image labels
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[0-9a-f]{7,40}$ ]] || die 'Version PREPROD invalide.'
  [[ "$expected" =~ ^sha256:[0-9a-f]{64}$ ]] || die 'Digest PREPROD invalide.'
  image="$(component_image preprod "$component" "$version")"
  docker manifest inspect "$image" >/dev/null 2>&1 || die "Image distante inaccessible : $component/$version"
  docker pull "$image" >/dev/null 2>&1 || die "Pull impossible : $component/$version"
  verify_image_digest "$image" "$expected" >/dev/null
  labels="$(docker image inspect "$image" --format '{{json .Config.Labels}}')"
  python3 -c '
import json,sys
labels=json.loads(sys.argv[1]) or {}
version,revision=sys.argv[2].rsplit("-",1)
actual=labels.get("org.opencontainers.image.revision", "")
if not (len(actual) >= len(revision) and actual.startswith(revision) and all(c in "0123456789abcdef" for c in actual)):
    raise ValueError("revision OCI refusée")
if labels.get("org.opencontainers.image.version") != version:
    raise ValueError("version OCI refusée")
if labels.get("org.opencontainers.image.source") != "https://github.com/fabffo/wavy-"+sys.argv[3]:
    raise ValueError("source OCI refusée")
' "$labels" "$version" "$component" || die "Labels OCI refusés : $component"
  success " Image $component : version, RepoDigest et labels OCI conformes."
}
preprod_wait() {
  local service="$1" status attempt
  for ((attempt=1; attempt<=60; attempt++)); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$service" 2>/dev/null || true)"
    [[ "$status" != healthy ]] || return 0
    [[ "$status" != unhealthy ]] || die "Healthcheck Docker en échec : $service"
    sleep 2
  done
  die "Délai healthy dépassé : $service"
}

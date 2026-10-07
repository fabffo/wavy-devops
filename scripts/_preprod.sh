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

# Un reload est asynchrone : valider aussi une requête via les workers Nginx.
# Retours explicites pour propager les erreurs même depuis un appel conditionnel.
preprod_nginx_running() {
  local container="$1" running
  running="$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" || {
    error "Protection Nginx PREPROD : conteneur absent/inaccessible : $container"; return 1;
  }
  [[ "$running" == true ]] || {
    error "Protection Nginx PREPROD : conteneur arrêté : $container"; return 1;
  }
}

preprod_nginx_wait_healthy() {
  local container="$1" attempt status
  for ((attempt=1; attempt<=30; attempt++)); do
    preprod_nginx_running "$container" || return 1
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container" 2>/dev/null)" || {
      error "Protection Nginx PREPROD : état inaccessible : $container"; return 1;
    }
    [[ "$status" != healthy ]] || return 0
    [[ "$status" == starting ]] || {
      error "Protection Nginx PREPROD : $container non healthy ($status)"; return 1;
    }
    ((attempt == 30)) || sleep 2
  done
  error "Protection Nginx PREPROD : délai healthy dépassé : $container"
  return 1
}

preprod_nginx_gateway_check() {
  local shell=wavy-erp-shell-preprod gateway=wavy-gateway-preprod body
  preprod_nginx_running "$shell" || return 1
  preprod_nginx_wait_healthy "$gateway" || return 1
  docker exec "$shell" getent hosts "$gateway" >/dev/null || {
    error 'Protection Nginx PREPROD : résolution Gateway impossible depuis ERP Shell'; return 1;
  }
  body="$(docker exec "$shell" wget -qO- -T 5 "http://$gateway:8088/actuator/health")" || {
    error 'Protection Nginx PREPROD : Gateway ne répond pas depuis ERP Shell'; return 1;
  }
  [[ "$body" =~ \"status\"[[:space:]]*:[[:space:]]*\"UP\" ]] || {
    error 'Protection Nginx PREPROD : réponse health Gateway non UP'; return 1;
  }
}

preprod_reload_erp_shell_nginx() {
  local shell=wavy-erp-shell-preprod attempt body
  info 'Protection Nginx PREPROD : contrôle Gateway puis reload ERP Shell'
  preprod_nginx_gateway_check || return 1
  docker exec "$shell" nginx -t || {
    error 'Protection Nginx PREPROD : nginx -t KO, reload refusé'; return 1;
  }
  docker exec "$shell" nginx -s reload || {
    error 'Protection Nginx PREPROD : nginx reload KO'; return 1;
  }
  preprod_nginx_wait_healthy "$shell" || return 1
  preprod_nginx_gateway_check || return 1
  # Le healthcheck du front ne couvre que / ; vérifier le vrai proxy /api/.
  # Attente bornée de la prise en compte du reload, sans sleep inconditionnel.
  for ((attempt=1; attempt<=30; attempt++)); do
    body="$(docker exec "$shell" wget -qO- -T 5 http://127.0.0.1/api/tiers/health)" &&
      [[ "$body" =~ \"module\"[[:space:]]*:[[:space:]]*\"wavy-tiers-api\" &&
         "$body" =~ \"status\"[[:space:]]*:[[:space:]]*\"OK\" ]] && break
    ((attempt == 30)) || sleep 2
  done
  if ((attempt > 30)); then
    error 'Protection Nginx PREPROD : proxy ERP Shell vers Gateway indisponible après reload'; return 1
  fi
  preprod_nginx_wait_healthy "$shell" || return 1
  preprod_nginx_gateway_check || return 1
  success ' Nginx ERP Shell rechargé ; Gateway et proxy /api/ vérifiés'
}

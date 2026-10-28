#!/usr/bin/env bash
# Parcours de livraison de la CLI existante ; aucun transport distant.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
umask 077
[[ $# == 1 && ( $1 == recette || $1 == preprod ) ]] || die 'Usage : ./wavy install recette|preprod'
env="$1"
if [[ "$env" == preprod ]]; then
  if [[ ${WAVY_PREPROD_WRAPPED_ENTRY:-} != "${BASH_SOURCE[0]}" ]]; then
    export WAVY_PREPROD_WRAPPED_ENTRY="${BASH_SOURCE[0]}"
    exec python3 "$SCRIPT_DIR/preprod_operation.py" -- bash "${BASH_SOURCE[0]}" "$@"
  fi
  source "$SCRIPT_DIR/_preprod.sh"
  preprod_host_guard
  "$SCRIPT_DIR/validate-preprod-config.sh"
  python3 "$SCRIPT_DIR/delivery_check.py" promotion
  # Chaque composant garde backups chiffrés, migrations et smoke de l'orchestrateur.
  for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
    "$SCRIPT_DIR/deploy.sh" preprod "$component"
  done
  exit 0
fi
[[ -z "${DOCKER_HOST:-}" && -z "${DOCKER_CONTEXT:-}" ]] || die 'Daemon distant interdit.'
[[ "$(env_value recette WAVY_INSTALL_HOSTNAME '')" == "$(hostname -s)" ]] || die 'Configurer WAVY_INSTALL_HOSTNAME sur la VM cible ; installation refusée sur cet hôte.'
[[ ! -f "$ROOT_DIR/deployments/recette-https-reservation.json" && ! -f "$HOME/.local/state/wavy/recettelocal/runtime-info.json" ]] || die 'Session MSI réservée : utiliser ./wavy local.'
require_docker
require_command python3
[[ "$(docker context inspect --format '{{.Endpoints.docker.Host}}')" == unix:///var/run/docker.sock ]] || die 'Socket Docker système local requis.'
recette_operation_lock
[[ -z "$(git -C "$ROOT_DIR" status --porcelain -- wavy scripts docker docker-compose.recette.yml versions)" ]] || die 'Livraison non synchronisée avec Git ; publier puis synchroniser le dépôt avant installation.'
timeout="$(env_value recette WAVY_INSTALL_WAIT_SECONDS 600)"
[[ "$timeout" =~ ^[1-9][0-9]*$ && "$timeout" -ge 180 && "$timeout" -le 3600 ]] || die 'Délai attendu entre 180 et 3600 secondes.'
python3 "$SCRIPT_DIR/delivery_check.py" preflight
python3 "$SCRIPT_DIR/release_images.py" verify recette
python3 "$SCRIPT_DIR/delivery_check.py" storage
# Refus d'une installation partielle : aucune initialisation de DB implicite.
WAVY_ENV=recette "$SCRIPT_DIR/backup-db.sh"
release_revision="$(git -C "$ROOT_DIR" rev-parse HEAD)"
started="$(date -Is)"
result=KO
finish() {
  local code=$?
  printf '%s\tINSTALL\trecette\t%s\t%s\t%s\n' "$(date -Is)" "$result" "$(id -un)" "$release_revision" >> "$ROOT_DIR/deployments/recette-install.tsv"
  exit "$code"
}
trap finish EXIT
compose recette up -d --wait --wait-timeout "$timeout"
for component in socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
  docker exec "wavy-$component-recette" wget -qO- -T 10 http://127.0.0.1/ >/dev/null
done
python3 "$SCRIPT_DIR/delivery_check.py" migrations "$started"
docker exec wavy-erp-shell-recette nginx -t
docker exec wavy-erp-shell-recette nginx -s reload
python3 "$SCRIPT_DIR/delivery_check.py" runtime
result=OK
success 'RECETTE disponible pour vos tests : https://recette.wavyservices.fr ; services laissés démarrés.'

#!/usr/bin/env bash
# Continuation interne : exige le contexte verifie du moteur commun.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
umask 077
[[ $# == 1 && ( $1 == recette || $1 == preprod ) ]] || die 'Environnement de livraison invalide.'
env="$1"
python3 "$SCRIPT_DIR/delivery_batch.py" check "$env"
if [[ "$env" == preprod ]]; then
  for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
    info "Livraison PREPROD : composant=$component"
    "$SCRIPT_DIR/deploy.sh" preprod "$component" || {
      code=$?
      error "Livraison PREPROD interrompue : composant=$component, code=$code. Aucune restauration automatique."
      exit "$code"
    }
  done
  success 'PREPROD : livraison complete des 13 composants terminee.'
  exit 0
fi
timeout="$(env_value recette WAVY_INSTALL_WAIT_SECONDS 600)"
[[ "$timeout" =~ ^[1-9][0-9]*$ && "$timeout" -ge 180 && "$timeout" -le 3600 ]] || die 'Delai invalide.'
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
success 'RECETTE installée, contrôles internes réussis ; services laissés démarrés. Tester HTTPS / ERP / PWA dans Chrome : https://recette.wavyservices.fr.'

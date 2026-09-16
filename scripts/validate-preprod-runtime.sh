#!/usr/bin/env bash
# Validation explicite d’une installation initiale ; ne recrée aucun service.
set -euo pipefail
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_preprod.sh"
preprod_host_guard
"$SCRIPT_DIR/validate-preprod-config.sh"
require_command flock
mkdir -p "$ROOT_DIR/deployments"
exec 9>"$ROOT_DIR/deployments/preprod.lock"
flock -n 9 || die 'Une opération PREPROD est en cours.'
for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
  service="$(service_name "$component" preprod)"
  preprod_container_guard "$service" "$service"
  version="$(component_version preprod "$component")"
  digest="$(component_digest preprod "$component")"
  preprod_verify_image "$component" "$version" "$digest"
  image="$(component_image preprod "$component" "$version")"
  [[ "$(docker inspect -f '{{.Image}}' "$service")" == "$(docker image inspect -f '{{.Id}}' "$image")" ]] || die 'Image active différente du manifeste.'
  [[ "$(docker inspect -f '{{.Config.Image}}' "$service")" == "${image%:*}@$digest" ]] || die 'Image active non épinglée.'
  preprod_wait "$service"
  if [[ "$component" == *-api ]]; then
    since="$(docker inspect -f '{{.State.StartedAt}}' "$service")"
    logs="$(preprod_compose logs --no-color --since "$since" "$service" 2>&1)" || die 'Logs inaccessibles.'
    if grep -Eqi 'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException' <<< "$logs"; then
      die 'Erreur Flyway détectée.'
    fi
  fi
done
"$SCRIPT_DIR/healthcheck.sh" preprod
"$SCRIPT_DIR/smoke-test.sh" preprod
"$SCRIPT_DIR/backup-preprod.sh"
for component in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do
  version="$(component_version preprod "$component")"
  record_validated_image preprod "$component" "$version" "$(component_digest preprod "$component")" "${version##*-}"
done
printf '%s\tVALIDATE_INITIAL\tOK\n' "$(date -Is)" >> "$ROOT_DIR/deployments/preprod-initialization.tsv"
success 'Installation PREPROD validée ; historique technique renseigné, sans fausse entrée DEPLOY.'

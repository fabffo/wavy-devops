#!/usr/bin/env bash
# Déploiement/rollback ciblé PREPROD, jamais de build ni de restore automatique.
set -euo pipefail
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_preprod.sh"
action="${1:-}"; component="${2:-}"
case "$component" in
  socle-api|tiers-api|contrats-api|factures-api|tresorerie-api|gateway|socle-front|tiers-front|contrats-front|factures-front|tresorerie-front|pwa|erp-shell) ;;
  *) die 'Composant PREPROD inconnu.' ;;
esac
case "$action" in
  DEPLOY) [[ $# == 2 ]] || die 'Usage : deploy.sh preprod <composant>' ;;
  ROLLBACK) [[ $# == 3 || ( $# == 4 && $4 == --yes ) ]] || die 'Usage : rollback.sh preprod <composant> <version> [--yes]' ;;
  *) die 'Action PREPROD inconnue.' ;;
esac
preprod_host_guard
"$SCRIPT_DIR/validate-preprod-config.sh"
require_command flock
mkdir -p "$ROOT_DIR/deployments"
exec 9>"$ROOT_DIR/deployments/preprod.lock"
flock -n 9 || die 'Une opération PREPROD est déjà en cours.'
# Refuse une configuration non reproductible, sans interdire l’historique runtime ignoré.
git -C "$ROOT_DIR" diff --quiet -- docker-compose.preprod.yml scripts versions/preprod.env versions/preprod.digests || die 'Configuration PREPROD modifiée : synchroniser Git avant déploiement.'
git -C "$ROOT_DIR" diff --cached --quiet || die 'Index Git modifié.'
[[ -z "$(git -C "$ROOT_DIR" ls-files --others --exclude-standard -- scripts versions/preprod.env versions/preprod.digests docker-compose.preprod.yml)" ]] || die 'Fichiers PREPROD non versionnés.'
minimum="${WAVY_DEPLOY_MIN_FREE_KB:-1048576}"
[[ "$minimum" =~ ^[1-9][0-9]*$ ]] || die 'Seuil disque invalide.'
for dir in "$ROOT_DIR" "$(docker info --format '{{.DockerRootDir}}')"; do
  available="$(df -Pk "$dir" | awk 'NR==2 {print $4}')"
  [[ "$available" =~ ^[0-9]+$ ]] && ((available >= minimum)) || die 'Espace disque insuffisant.'
done
# Les smoke tests doivent pouvoir être exécutés après remplacement.
for key in WAVY_SMOKE_TENANT_ID WAVY_SMOKE_USER_ID WAVY_SMOKE_COMPANY_ID; do
  [[ "${!key:-}" =~ ^[1-9][0-9]*$ ]] || die "Contexte smoke requis avant déploiement : $key"
done
[[ -n "${WAVY_SMOKE_USER:-}" && -n "${WAVY_SMOKE_PASSWORD:-}" ]] || die "Authentification smoke requise."
version="$(component_version preprod "$component")"
digest="$(component_digest preprod "$component")"
if [[ "$action" == ROLLBACK ]]; then
  version="$3"
  digest="$(get_validated_digest preprod "$component" "$version")"
fi
history="$(validated_history_file preprod "$component")"
if awk -F '\t' -v v="$version" 'NR>1 && $1==v {found=1} END {exit !found}' "$history"; then
  [[ "$(get_validated_digest preprod "$component" "$version")" == "$digest" ]] || die 'Digest incompatible avec l’historique.'
fi
service="$(service_name "$component" preprod)"
# Ce chemin met à jour une installation existante ; il ne provisionne pas les bases.
preprod_container_guard "$service" "$service"
for db in socle tiers contrats factures tresorerie; do
  preprod_container_guard "$(db_container "$db" preprod)" "$db-postgres"
done
preprod_verify_image "$component" "$version" "$digest"
image="$(component_image preprod "$component" "$version")"
pinned="${image%:*}@$digest"
image_id="$(docker image inspect -f '{{.Id}}' "$image")"
commit="$(docker image inspect "$image" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
current_id="$(docker inspect -f '{{.Image}}' "$service")"
if [[ "$action" == ROLLBACK && "${4:-}" != --yes ]]; then
  confirm "Rollback PREPROD $component vers $version ($digest) ?" || die 'Rollback annulé.'
fi
tmp="$(mktemp -d "${TMPDIR:-/tmp}/wavy-preprod-release.XXXXXX")"
started="$(date -Is)"; result=KO; mutation=false
finish() {
  local code=$?
  if $mutation; then
    local journal="$ROOT_DIR/deployments/preprod.tsv"
    [[ -f "$journal" ]] || printf 'date\taction\tenvironnement\tcomposant\tmode\tcommit\tversion\tdigest\tresultat\tutilisateur\n' > "$journal"
    printf '%s\t%s\tpreprod\t%s\tIMAGE\t%s\t%s\t%s\t%s\t%s\n' "$(date -Is)" "$action" "$component" "$commit" "$version" "$digest" "$result" "$(id -un)" >> "$journal"
  fi
  rm -rf -- "$tmp"
  exit "$code"
}
trap finish EXIT
printf 'services:\n  %s:\n    image: %s\n' "$service" "$pinned" > "$tmp/pinned.yml"
preprod_compose -f "$tmp/pinned.yml" config --quiet >/dev/null 2>&1 || die 'Compose final invalide.'
# Sauvegarde des cinq bases même pour un front ou Gateway.
"$SCRIPT_DIR/backup-preprod.sh"
cache="wavy-rollback-cache/preprod-${component}:before-$(date +%Y%m%dT%H%M%S)"
docker image tag "$current_id" "$cache"
success " Cache avant remplacement : $cache"
mutation=true
preprod_compose -f "$tmp/pinned.yml" up -d --no-deps --no-build --force-recreate --pull never "$service"
preprod_wait "$service"
if [[ "$component" == *-api ]]; then
  preprod_compose logs --no-color --since "$started" "$service" > "$tmp/logs" 2>&1 || die 'Impossible de contrôler les logs Flyway.'
  if grep -Eqi 'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException' "$tmp/logs"; then
    die 'Erreur Flyway détectée ; logs conservés uniquement dans Docker, aucun rollback automatique.'
  fi
fi
if [[ "$component" == *-front || "$component" == pwa || "$component" == erp-shell ]]; then
  docker exec "$service" wget -qO- -T 5 http://127.0.0.1/ >/dev/null || die 'Front indisponible.'
fi
"$SCRIPT_DIR/healthcheck.sh" preprod
"$SCRIPT_DIR/smoke-test.sh" preprod
[[ "$(docker inspect -f '{{.Image}}' "$service")" == "$image_id" ]] || die 'ID de l’image active non conforme.'
[[ "$(docker inspect -f '{{.Config.Image}}' "$service")" == "$pinned" ]] || die 'Référence active non épinglée au digest.'
verify_image_digest "$image" "$digest" >/dev/null
record_validated_image preprod "$component" "$version" "$digest" "$commit"
result=OK
success " $action PREPROD $component : $version $digest"
[[ "$action" != ROLLBACK ]] || warn 'Aligner les manifestes Git sur la cible validée avant le prochain déploiement. Aucune base restaurée.'

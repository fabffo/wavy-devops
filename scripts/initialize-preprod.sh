#!/usr/bin/env bash
# Premier provisionnement explicite UNIQUEMENT sur une VM sans état PREPROD.
# Ne jamais utiliser pour une mise à jour ; celles-ci passent par deploy.sh.
set -euo pipefail
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_preprod.sh"
source "$SCRIPT_DIR/_preprod-documents.sh"
[[ $# == 1 && $1 == --empty-installation ]] || die 'Usage : initialize-preprod.sh --empty-installation'
preprod_host_guard
"$SCRIPT_DIR/validate-preprod-config.sh"
require_command flock
mkdir -p "$ROOT_DIR/deployments"
exec 9>"$ROOT_DIR/deployments/preprod.lock"
flock -n 9 || die 'Opération PREPROD déjà en cours.'
[[ -z "$(git -C "$ROOT_DIR" status --porcelain -- scripts docker-compose.preprod.yml versions/preprod.env versions/preprod.digests)" ]] || die 'Configuration non synchronisée avec Git.'
for dir in "$ROOT_DIR" "$(docker info --format '{{.DockerRootDir}}')"; do
  available="$(df -Pk "$dir" | awk 'NR==2 {print $4}')"
  [[ "$available" =~ ^[0-9]+$ ]] && ((available >= 1048576)) || die 'Espace disque insuffisant.'
done
[[ -z "$(docker volume ls -q --filter label=com.docker.compose.project=wavy-preprod)" ]] || die 'Volumes PREPROD existants : initialisation refusée.'
[[ -z "$(docker ps -aq --filter label=com.docker.compose.project=wavy-preprod)" ]] || die 'Conteneurs PREPROD existants : initialisation refusée.'
# Détecter également les volumes conventionnels et noms fixes non étiquetés.
for volume in socle-postgres-preprod-data tiers-postgres-preprod-data contrats-postgres-preprod-data factures-postgres-preprod-data tresorerie-postgres-preprod-data documents-preprod; do
  ! docker volume inspect "wavy-preprod_$volume" >/dev/null 2>&1 || die 'Volume de destination déjà présent.'
done
components=(socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell)
for component in "${components[@]}"; do
  ! docker inspect "$(service_name "$component" preprod)" >/dev/null 2>&1 || die 'Nom de conteneur déjà utilisé.'
done
for db in socle tiers contrats factures tresorerie; do
  ! docker inspect "$(db_container "$db" preprod)" >/dev/null 2>&1 || die 'Nom de base déjà utilisé.'
done
tmp="$(mktemp -d "${TMPDIR:-/tmp}/wavy-preprod-initialize.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT
printf 'services:\n' > "$tmp/pinned.yml"
for component in "${components[@]}"; do
  version="$(component_version preprod "$component")"
  digest="$(component_digest preprod "$component")"
  preprod_verify_image "$component" "$version" "$digest"
  image="$(component_image preprod "$component" "$version")"
  printf '  %s:\n    image: %s@%s\n' "$(service_name "$component" preprod)" "${image%:*}" "$digest" >> "$tmp/pinned.yml"
done
postgres='postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f'
docker pull "$postgres" >/dev/null 2>&1 || die 'Image PostgreSQL épinglée inaccessible.'
preprod_compose -f "$tmp/pinned.yml" config --quiet >/dev/null 2>&1 || die 'Compose final invalide.'
confirm 'Créer la première installation PREPROD vide (volumes, migrations des images, bootstrap selon configuration) ?' || die 'Initialisation annulée.'
# UID/GID 100:101 relevés dans /etc/passwd de l’image Contrats 527874b.
# Création uniquement après tous les contrôles et la confirmation d’installation vide.
docker volume create --label com.docker.compose.project=wavy-preprod   --label com.docker.compose.volume=documents-preprod "$DOCUMENT_VOLUME" >/dev/null
preprod_document_volume_guard
preprod_document_tool rw 'mkdir /documents/contrats; chown 100:101 /documents/contrats; chmod 0700 /documents/contrats'
# Aucun backup possible avant le premier démarrage : aucune base n’existe encore.
# Après un échec, ne jamais supprimer les volumes ni relancer ce script à l’aveugle.
preprod_compose -f "$tmp/pinned.yml" up -d --no-build --pull never --wait
"$SCRIPT_DIR/healthcheck.sh" preprod
printf '%s\tINITIALIZE\tPENDING_SMOKE\n' "$(date -Is)" >> "$ROOT_DIR/deployments/preprod-initialization.tsv"
warn 'Installation démarrée, pas encore validée. Fournir le contexte smoke réel puis exécuter validate-preprod-runtime.sh.'

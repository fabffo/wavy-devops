#!/usr/bin/env bash
# Teste et construit une image OCI immuable Wavy ; aucun push par défaut.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

usage() {
  cat >&2 <<EOF
Usage : $0 <composant> <version> [--push]

Exemple :
  $0 factures-api 2.5.0
  $0 factures-api 2.5.0 --push
EOF
}

[[ "$#" -ge 2 && "$#" -le 3 ]] || { usage; exit 2; }
component="$1"
functional_version="$2"
push=false
if [[ "$#" -eq 3 ]]; then
  [[ "$3" == --push ]] || { usage; die "Option inconnue : $3"; }
  push=true
fi

case "$component" in
  socle-api|tiers-api|contrats-api|factures-api|tresorerie-api|gateway|socle-front|tiers-front|contrats-front|factures-front|tresorerie-front|pwa|erp-shell) ;;
  *) usage; die "Composant inconnu : $component" ;;
esac
[[ "$functional_version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z]+)*$ ]] \
  || die "Version invalide : utiliser une version explicite telle que 2.5.0."

repository="$ROOT_DIR/../wavy-$component"
[[ -d "$repository/.git" ]] || die "Dépôt Git introuvable : $repository"
sha="$(git -C "$repository" rev-parse --short=7 HEAD)"
tag="${functional_version}-${sha}"
registry="ghcr.io/fabffo"
image="${registry}/wavy-${component}:${tag}"
source_url="https://github.com/fabffo/wavy-${component}"
version_key="$(printf '%s_VERSION' "$component" | tr '[:lower:]-' '[:upper:]_')"

info "Composant : $component"
info "Commit : $sha"
info "Image cible : $image"
docker image inspect "$image" >/dev/null 2>&1 \
  && die "Le tag existe déjà localement et ne sera pas reconstruit : $image"

git_changes="$(git -C "$repository" status --porcelain)"
if [[ -n "$git_changes" ]]; then
  error "Le dépôt $component contient des modifications locales :"
  printf '%s\n' "$git_changes" >&2
  die "Build d'image bloqué : commit requis et arbre Git propre."
fi

is_java=false
[[ -f "$repository/pom.xml" ]] && is_java=true
if $is_java; then
  info "Tests Maven de $component..."
  if [[ -x "$repository/mvnw" ]]; then
    (cd "$repository" && ./mvnw test)
  else
    require_command mvn
    (cd "$repository" && mvn test)
  fi
else
  require_command npm
  [[ -f "$repository/package-lock.json" ]] || die "package-lock.json absent : npm ci non reproductible."
  info "Installation npm reproductible de $component..."
  (cd "$repository" && npm ci)
  info "Tests Angular/Vitest non interactifs de $component..."
  (cd "$repository" && npm test -- --watch=false)
  info "Build Angular de production de $component..."
  (cd "$repository" && npm run build -- --configuration production)
fi

require_docker
dockerfile="$repository/Dockerfile"
[[ "$component" != pwa ]] || dockerfile="$ROOT_DIR/docker/wavy-pwa.Dockerfile"
[[ -f "$dockerfile" ]] || die "Dockerfile introuvable : $dockerfile"

build_args=()
case "$component" in
  tiers-front|contrats-front|tresorerie-front) build_args+=(--build-arg API_BASE_URL=) ;;
  factures-front) build_args+=(--build-arg API_GATEWAY_BASE_URL=/api) ;;
  pwa) build_args+=(--build-arg API_BASE_URL=/api) ;;
esac

info "Construction Docker sans push..."
docker build \
  --file "$dockerfile" \
  --tag "$image" \
  --label "org.opencontainers.image.revision=$sha" \
  --label "org.opencontainers.image.version=$functional_version" \
  --label "org.opencontainers.image.source=$source_url" \
  "${build_args[@]}" \
  "$repository"

image_id="$(docker image inspect --format '{{.Id}}' "$image")"
image_size="$(docker image inspect --format '{{.Size}}' "$image")"
image_size_mib="$(awk -v bytes="$image_size" 'BEGIN {printf "%.2f", bytes / 1024 / 1024}')"
success " Image construite : $image"
info "Identifiant local : $image_id"
info "Taille : ${image_size_mib} Mio ($image_size octets)"

if $push; then
  [[ -n "${GHCR_USERNAME:-}" ]] || die "GHCR_USERNAME doit être fourni par l'environnement."
  [[ -n "${GHCR_TOKEN:-}" ]] || die "GHCR_TOKEN doit être fourni par l'environnement."

  info "Authentification à GHCR..."
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin >/dev/null
  info "Vérification de l'immuabilité du tag dans GHCR..."
  if manifest_output="$(docker manifest inspect "$image" 2>&1)"; then
    die "Le tag existe déjà dans GHCR et ne sera pas remplacé : $image"
  elif ! printf '%s\n' "$manifest_output" | grep -Eqi 'manifest unknown|no such manifest'; then
    die "Impossible de prouver l'absence du tag dans GHCR. Push refusé : $manifest_output"
  fi
  docker push "$image"

  remote_digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image" | awk -F@ -v prefix="${registry}/wavy-${component}" '$1 == prefix {print $2; exit}')"
  [[ "$remote_digest" == sha256:* ]] || die "Push terminé mais digest distant introuvable."
  success " Image publiée : ${registry}/wavy-${component}@${remote_digest}"
  printf 'Suggestion de manifest (à appliquer séparément) :\n%s=%s\n' "$version_key" "$tag"
else
  info "Aucun push demandé. Utiliser --push après validation explicite et authentification GHCR."
  printf 'Suggestion après publication réussie : %s=%s\n' "$version_key" "$tag"
fi

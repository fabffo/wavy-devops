#!/usr/bin/env bash
# Rétention des tags locaux wavy-rollback-cache, sans toucher aux images actives.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

usage() { printf 'Usage : %s [--dry-run|--execute]\n' "$0" >&2; }
mode="${1:---dry-run}"
[[ "$#" -le 1 ]] || { usage; exit 2; }
case "$mode" in --dry-run|--execute) ;; *) usage; exit 2 ;; esac
keep="${WAVY_ROLLBACK_CACHE_RETENTION_COUNT:-5}"
[[ "$keep" =~ ^[1-9][0-9]*$ ]] || die "WAVY_ROLLBACK_CACHE_RETENTION_COUNT doit être un entier strictement positif."
require_docker

declare -A active_ids=()
while IFS= read -r id; do [[ -z "$id" ]] || active_ids["$id"]=1; done \
  < <(docker ps -aq | xargs -r docker inspect -f '{{.Image}}' | sort -u)

mapfile -t repositories < <(docker image ls --format '{{.Repository}}' \
  | awk '/^wavy-rollback-cache\/[a-z0-9][a-z0-9-]*$/' | sort -u)
removed=0
skipped_active=0
skipped_sole_reference=0

for repository in "${repositories[@]}"; do
  mapfile -t tags < <(docker image ls "$repository" --format '{{.Tag}}' \
    | awk 'match($0, /[0-9]{8}T[0-9]{6}$/) {print substr($0, RSTART), $0}' | sort -r | awk '{print $2}')
  info "Cache $repository : ${#tags[@]} tag(s) horodaté(s), conservation=$keep"
  for index in "${!tags[@]}"; do
    ((index < keep)) && continue
    ref="$repository:${tags[$index]}"
    image_id="$(docker image inspect -f '{{.Id}}' "$ref")"
    if [[ -n "${active_ids[$image_id]:-}" ]]; then
      warn "Tag protégé car son image est active : $ref ($image_id)"
      skipped_active=$((skipped_active + 1))
      continue
    fi
    other_references="$(docker image inspect "$ref" --format '{{range .RepoTags}}{{println .}}{{end}}{{range .RepoDigests}}{{println .}}{{end}}' \
      | awk '$0 !~ /^wavy-rollback-cache\//')"
    if [[ -z "$other_references" ]]; then
      warn "Tag protégé car il est la seule référence locale de l'image : $ref ($image_id)"
      skipped_sole_reference=$((skipped_sole_reference + 1))
      continue
    fi
    if [[ "$mode" == --dry-run ]]; then
      info "DRY-RUN suppression tag rollback : $ref"
    else
      info "Suppression tag rollback : $ref"
      docker image rm "$ref" >/dev/null
    fi
    removed=$((removed + 1))
  done
done
success " Nettoyage rollback-cache : mode=$mode supprimables=$removed protégés-actifs=$skipped_active protégés-référence-unique=$skipped_sole_reference conservation=$keep par composant"

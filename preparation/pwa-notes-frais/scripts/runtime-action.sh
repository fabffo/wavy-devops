#!/usr/bin/env bash
# Commandes runtime candidates. Appelées seulement après autorisation future sur la VM.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_runtime.sh"
preprod_host_guard
case "${1:-}" in
  record|checks|backup) preprod_backup_operation_lock ;;
esac
case "${1:-}" in
  host) ;;
  record)
    case "${2:-}" in factures-api|factures-front|pwa|erp-shell) ;; *) exit 2;; esac
    [[ ${3:-} =~ ^[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{7,40}$ && ${5:-} =~ ^[a-f0-9]{7,40}$ ]] || exit 2
    record_validated_image preprod "$2" "$3" "$4" "$5"
    ;;
  guard)
    candidate_validate
    [[ -z "$(git -C "$ROOT_DIR" status --porcelain -- scripts preparation/pwa-notes-frais docker-compose.preprod.yml versions)" ]] \
      || die 'Sources de release non synchronisées.'
    for key in WAVY_SMOKE_TENANT_ID WAVY_SMOKE_USER_ID WAVY_SMOKE_COMPANY_ID; do
      [[ ${!key:-} =~ ^[1-9][0-9]*$ ]] || die 'Contexte smoke requis.'
    done
    [[ -n ${WAVY_SMOKE_USER:-} && -n ${WAVY_SMOKE_PASSWORD:-} ]] || die 'Identifiants smoke requis.'
    for db in socle tiers contrats factures tresorerie; do
      preprod_container_guard "$(db_container "$db" preprod)" "$db-postgres"
    done
    for dir in "$ROOT_DIR" "$(docker info --format '{{.DockerRootDir}}')"; do
      available="$(df -Pk "$dir" | awk 'NR==2 {print $4}')"
      [[ $available =~ ^[0-9]+$ ]] && ((available >= 1048576)) || die 'Disque insuffisant.'
    done
    ;;
  provision-storage)
    deadline="$(candidate_provision_guard)"
    preprod_document_volume_guard
    [[ "$(docker volume inspect -f '{{.Name}}' "$DOCUMENT_VOLUME")" == wavy-preprod_documents-preprod ]] || die 'Identité du volume inattendue.'
    python_image=python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d
    docker image inspect "$python_image" >/dev/null 2>&1 || die 'Image Python de provisionnement épinglée absente.'
    docker run --rm --pull never --network none --read-only --user 0:0 \
      --security-opt no-new-privileges:true --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE \
      --env "WAVY_STORAGE_DEADLINE=$deadline" \
      --mount "type=volume,source=$DOCUMENT_VOLUME,target=/documents" \
      --mount "type=bind,source=$CANDIDATE_SCRIPTS/provision_storage.py,target=/provision_storage.py,readonly" \
      --entrypoint python3 "$python_image" -B /provision_storage.py
    ;;
  storage)
    preprod_document_volume_guard
    # Lecture seulement : ne crée ni répertoire ni fichier sur le volume.
    preprod_document_tool ro 'test -d /documents/contrats; test ! -L /documents/contrats; test -d /documents/notes-frais; test ! -L /documents/notes-frais; test "$(stat -c %u:%g:%a /documents/notes-frais)" = 100:101:700'
    docker run --rm --pull never --network none --read-only --user 100:101 \
      --security-opt no-new-privileges:true \
      --mount "type=volume,source=$DOCUMENT_VOLUME,target=/documents,volume-subpath=notes-frais,readonly" \
      --entrypoint /bin/sh "$DOCUMENT_TOOL_IMAGE" -eu -c 'test -r /documents; test -x /documents'
    ;;
  https)
    url="$(preprod_value WAVY_PUBLIC_URL)"
    curl --silent --show-error --fail --max-time 15 --proto '=https' --tlsv1.2 "$url/" >/dev/null
    ;;
  wait)
    case "${2:-}" in factures-api|factures-front|pwa|erp-shell) ;; *) exit 2;; esac
    preprod_wait "wavy-$2-preprod"
    ;;
  checks)
    preprod_reload_erp_shell_nginx
    "$SCRIPT_DIR/healthcheck.sh" preprod
    "$SCRIPT_DIR/smoke-test.sh" preprod
    ;;
  closed|opened)
    url="$(preprod_value WAVY_PUBLIC_URL)"
    paths=(/pwa /pwa/ /pwa/ngsw-worker.js /pwa/ngsw.json /pwa/main.js /pwa/assets/probe /api/pwa /api/pwa/session /pwa-integration.json)
    [[ $1 == closed ]] || paths=(/pwa /pwa/ /pwa-integration.json)
    for path in "${paths[@]}"; do
      response="$(curl --silent --show-error --max-time 15 --proto '=https' --tlsv1.2 -D - -o /dev/null -w $'\n%{http_code}' "$url$path")"
      code="${response##*$'\n'}"
      if [[ $1 == closed ]]; then
        [[ $code == 404 ]] && printf '%s' "$response" | grep -Eqi '^X-Wavy-PWA-Gate: closed[[:space:]]*$' || die 'Fermeture EDGE non confirmée.'
      else
        [[ $code == 200 || ( $path == /pwa && $code == 308 ) ]] || die 'Route PWA indisponible.'
        printf '%s' "$response" | grep -Eqi '^X-Wavy-PWA-Gate: open[[:space:]]*$' || die 'Barrière EDGE absente.'
      fi
    done
    if [[ $1 == opened ]]; then
      curl --silent --show-error --fail --max-time 15 --proto '=https' --tlsv1.2 "$url/pwa-integration.json" \
        | python3 -c 'import json,sys; assert json.load(sys.stdin)["enabled"] is True'
    fi
    ;;
  backup)
    bash "$CANDIDATE_SCRIPTS/backup-preprod.sh"
    ;;
  *) exit 2;;
esac

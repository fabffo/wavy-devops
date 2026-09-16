#!/usr/bin/env bash
# Fonctions opérationnelles ; source sans effet. Même image utilitaire déjà épinglée.
DOCUMENT_VOLUME=wavy-preprod_documents-preprod
DOCUMENT_TOOL_IMAGE=postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f
preprod_document_volume_guard() {
  [[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.project"}}' "$DOCUMENT_VOLUME")" == wavy-preprod ]] || die 'Volume documentaire hors PREPROD.'
  [[ "$(docker volume inspect -f '{{index .Labels "com.docker.compose.volume"}}' "$DOCUMENT_VOLUME")" == documents-preprod ]] || die 'Volume documentaire inattendu.'
  docker image inspect "$DOCUMENT_TOOL_IMAGE" >/dev/null 2>&1 || die 'Image utilitaire documentaire épinglée absente.'
}
preprod_document_tool() {
  local access="$1"; shift
  local mount="type=volume,source=$DOCUMENT_VOLUME,target=/documents"
  [[ "$access" != ro ]] || mount+=,readonly
  docker run --rm -i --pull never --network none --read-only --security-opt no-new-privileges:true \
    --user 0:0 --mount "$mount" --entrypoint /bin/sh "$DOCUMENT_TOOL_IMAGE" -eu -c "$1"
}
# Les backends sont arrêtés proprement pendant tout le lot DB + documents.
# Un arrêt forcé (137) est refusé : une transaction documentaire peut être inachevée.
preprod_quiesce() {
  QUIESCED_SERVICES=()
  for component in gateway socle-api tiers-api contrats-api factures-api tresorerie-api; do
    local service
    service="$(service_name "$component" preprod)"
    preprod_container_guard "$service" "$service"
    QUIESCED_SERVICES+=("$service")
    docker stop --time 60 "$service" >/dev/null || die 'Arrêt des écritures impossible.'
    [[ "$(docker inspect -f '{{.State.ExitCode}}' "$service")" != 137 ]] || die 'Arrêt forcé : cohérence documentaire non garantie, sauvegarde refusée.'
  done
}
preprod_resume() {
  local i failed=0
  for ((i=${#QUIESCED_SERVICES[@]}-1; i>=0; i--)); do
    docker start "${QUIESCED_SERVICES[$i]}" >/dev/null || failed=1
  done
  return "$failed"
}

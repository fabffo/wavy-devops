#!/usr/bin/env bash
# Fonctions du backup standard RECETTE ; sourcer ce fichier ne modifie rien.
recette_documents_setup() {
  DOCUMENT_VOLUME="$(env_value recette WAVY_FACTURES_JUSTIFICATIFS_VOLUME '')"
  DOCUMENT_VOLUME="${DOCUMENT_VOLUME#\'}"; DOCUMENT_VOLUME="${DOCUMENT_VOLUME%\'}"
  DOCUMENT_VOLUME="${DOCUMENT_VOLUME#\"}"; DOCUMENT_VOLUME="${DOCUMENT_VOLUME%\"}"
  python3 - "$ROOT_DIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from release_images import manifest
from recette_pwa import preserve_storage, literal, storage_permissions
import json,subprocess
machine=manifest(Path(sys.argv[1])/'.env.recette',strict=False)
volume=literal(machine.get('WAVY_FACTURES_JUSTIFICATIFS_VOLUME',''))
preserve_storage({'volume':volume})
if volume:
    obj=json.loads(subprocess.check_output(['docker','inspect','wavy-factures-api-recette']))[0]
    env=dict(x.split('=',1) for x in obj['Config']['Env'] if '=' in x)
    mounts=[m for m in obj.get('Mounts',[]) if m['Destination']=='/app/justificatifs']
    if not env.get('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS') and not mounts and literal(machine.get('WAVY_RECETTE_VALIDATION_MODE',''))=='technical':
        # Premier rattachement : stockage auparavant désactivé. Ne pas masquer
        # un répertoire existant ; l'archive initiale doit être vide et privée.
        subprocess.run(['docker','exec','wavy-factures-api-recette','sh','-ec',
                        'test ! -e /app/justificatifs || { test -d /app/justificatifs; test ! -L /app/justificatifs; test -z "$(ls -A /app/justificatifs)"; }'],check=True)
        from recette_storage import check_volume, tool
        image=obj['Image']
        check_volume(volume,image)
        tool(volume,image,'test -z "$(ls -A /app/justificatifs)"')
    else:
        if env.get('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS')!='/app/justificatifs' or len(mounts)!=1 or mounts[0].get('Type')!='volume' or mounts[0].get('Name')!=volume:
            raise SystemExit('Stockage Factures à qualifier avant sauvegarde complète')
        storage_permissions(require_capacity=False)
PY
  if [[ -z "$DOCUMENT_VOLUME" ]]; then
    [[ "$(env_value recette WAVY_PWA_ENABLED false)" != true && "$(env_value recette WAVY_NOTES_WRITES_ENABLED false)" != true ]] \
      || die 'Sauvegarde PWA : volume privé requis.'
    return
  fi
  [[ "$DOCUMENT_VOLUME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || die 'Volume documentaire invalide.'
  ensure_container_running wavy-factures-api-recette
  DOCUMENT_IMAGE="$(docker inspect -f '{{.Image}}' wavy-factures-api-recette)"
  docker volume inspect "$DOCUMENT_VOLUME" >/dev/null
  read -r DOCUMENT_UID DOCUMENT_GID < <(docker exec wavy-factures-api-recette sh -ec 'printf "%s %s\n" "$(id -u)" "$(id -g)"')
  [[ "$DOCUMENT_UID" =~ ^[1-9][0-9]*$ && "$DOCUMENT_GID" =~ ^[0-9]+$ ]] || die 'UID/GID documentaire invalide.'
}
recette_quiesce() {
  QUIESCED_SERVICES=()
  # Tous les writers, y compris les API accessibles directement, doivent s'arrêter.
  for component in gateway socle-api tiers-api contrats-api factures-api tresorerie-api; do
    local service="wavy-$component-recette"
    ensure_container_running "$service"
    QUIESCED_SERVICES+=("$service")
    docker stop --time 60 "$service" >/dev/null || die 'Arrêt des écritures RECETTE impossible.'
    [[ "$(docker inspect -f '{{.State.ExitCode}}' "$service")" != 137 ]] || die 'Arrêt forcé : cohérence DB/documents non garantie.'
  done
}
recette_resume() {
  local i failed=0
  local -a pending=()
  for ((i=${#QUIESCED_SERVICES[@]}-1; i>=0; i--)); do
    docker start "${QUIESCED_SERVICES[$i]}" >/dev/null || { pending+=("${QUIESCED_SERVICES[$i]}"); failed=1; }
  done
  QUIESCED_SERVICES=("${pending[@]}")
  return "$failed"
}
recette_archive_documents() {
  docker run --rm --pull never --network none --read-only --security-opt no-new-privileges:true \
    --user 0:0 --mount "type=volume,source=$DOCUMENT_VOLUME,target=/store,readonly,volume-nocopy" \
    --entrypoint sh "$DOCUMENT_IMAGE" -ec 'test -d /store; test ! -L /store; tar -cpf - -C /store .' \
    > "$backup_dir/justificatifs.tar"
  python3 "$SCRIPT_DIR/recette_documents.py" seal "$backup_dir" "$DOCUMENT_VOLUME" "$DOCUMENT_UID" "$DOCUMENT_GID" >/dev/null
}

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$ROOT_DIR/docker-compose.recette.yml"
ENV_FILE="$ROOT_DIR/.env.recette"
EXAMPLE_ENV_FILE="$ROOT_DIR/.env.recette.example"

if [ ! -f "$ENV_FILE" ]; then
  echo "Fichier .env.recette introuvable."
  if [ -f "$EXAMPLE_ENV_FILE" ]; then
    read -rp "Voulez-vous copier .env.recette.example en .env.recette ? [Y/n] " answer
    answer="${answer:-Y}"
    if [[ "$answer" =~ ^[Yy] ]]; then
      cp "$EXAMPLE_ENV_FILE" "$ENV_FILE"
      echo "Fichier .env.recette créé à partir de l'exemple. Ajustez les variables si nécessaire."
    else
      echo "Abandon." >&2
      exit 1
    fi
  else
    echo "Fichier d'exemple non trouvé : $EXAMPLE_ENV_FILE" >&2
    exit 1
  fi
fi

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

env_value() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { value=$0; sub(/^[^=]*=/, "", value); print value }' "$ENV_FILE" | tail -n 1
}

env_value_or_default() {
  local key="$1"
  local default_value="$2"
  local value
  value="$(env_value "$key")"
  printf '%s\n' "${value:-$default_value}"
}

echo "Construction du jar wavy-gateway utilisé par son Dockerfile..."
(cd "$ROOT_DIR/../wavy-gateway" && ./mvnw -q -DskipTests package)

echo "Démarrage de la pile Docker recette..."
compose up -d --build

echo
GATEWAY_PORT="$(env_value_or_default WAVY_GATEWAY_HOST_PORT 28088)"
SOCLE_FRONT_PORT="$(env_value_or_default WAVY_SOCLE_FRONT_HOST_PORT 24200)"
TIERS_FRONT_PORT="$(env_value_or_default WAVY_TIERS_FRONT_HOST_PORT 24201)"
CONTRATS_FRONT_PORT="$(env_value_or_default WAVY_CONTRATS_FRONT_HOST_PORT 24202)"
FACTURES_FRONT_PORT="$(env_value_or_default WAVY_FACTURES_FRONT_HOST_PORT 24203)"
PWA_PORT="$(env_value_or_default WAVY_PWA_HOST_PORT 24204)"
PUBLIC_GATEWAY_URL="$(env_value_or_default WAVY_PUBLIC_GATEWAY_URL "http://localhost:${GATEWAY_PORT}")"
cat <<EOF
Pile Docker recette démarrée.
URLs :
- Gateway : ${PUBLIC_GATEWAY_URL}
- Socle   : http://localhost:${SOCLE_FRONT_PORT}
- Tiers   : http://localhost:${TIERS_FRONT_PORT}
- Contrats: http://localhost:${CONTRATS_FRONT_PORT}
- Factures: http://localhost:${FACTURES_FRONT_PORT}
- PWA     : http://localhost:${PWA_PORT}
EOF

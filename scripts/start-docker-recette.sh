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

echo "Construction du jar wavy-gateway utilisé par son Dockerfile..."
(cd "$ROOT_DIR/../wavy-gateway" && ./mvnw -q -DskipTests package)

echo "Démarrage de la pile Docker recette..."
compose up -d --build

echo
cat <<EOF
Pile Docker recette démarrée.
URLs :
- Gateway : http://localhost:28088
- Socle   : http://localhost:24200
- Tiers   : http://localhost:24201
- Contrats: http://localhost:24202
- Factures: http://localhost:24203
EOF

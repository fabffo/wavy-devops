#!/usr/bin/env bash
set -euo pipefail

base_dir="${WAVY_PROJECTS_DIR:-$HOME/projets}"
session="${WAVY_TMUX_SESSION:-wavy-local}"

tmux has-session -t "$session" 2>/dev/null && {
  echo "Session tmux deja active: $session"
  tmux attach -t "$session"
  exit 0
}

tmux new-session -d -s "$session" -n socle-api -c "$base_dir/wavy-socle-api" \
  'WAVY_SOCLE_DB_URL=jdbc:postgresql://localhost:5432/wavy_socle_db ./mvnw spring-boot:run -Dspring-boot.run.profiles=local'
tmux new-window -t "$session" -n tiers-api -c "$base_dir/wavy-tiers-api" \
  'WAVY_TIERS_DB_HOST=localhost WAVY_TIERS_DB_PORT=5432 WAVY_TIERS_DB_NAME=wavy_tiers_db ./mvnw spring-boot:run -Dspring-boot.run.profiles=local'
tmux new-window -t "$session" -n contrats-api -c "$base_dir/wavy-contrats-api" \
  'WAVY_CONTRATS_DB_HOST=localhost WAVY_CONTRATS_DB_PORT=5432 WAVY_CONTRATS_DB_NAME=wavy_contrats_db ./mvnw spring-boot:run -Dspring-boot.run.profiles=local'
tmux new-window -t "$session" -n factures-api -c "$base_dir/wavy-factures-api" \
  'WAVY_FACTURES_DB_HOST=localhost WAVY_FACTURES_DB_PORT=5432 WAVY_FACTURES_DB_NAME=wavy_factures_db WAVY_FACTURES_DB_USER=factures_user WAVY_FACTURES_DB_PASSWORD=factures_password ./mvnw spring-boot:run -Dspring-boot.run.profiles=local'
tmux new-window -t "$session" -n gateway -c "$base_dir/wavy-gateway" \
  './mvnw spring-boot:run'
tmux new-window -t "$session" -n socle-front -c "$base_dir/wavy-socle-front" \
  'npm start'
tmux new-window -t "$session" -n contrats-front -c "$base_dir/wavy-contrats-front" \
  'npm start'
tmux new-window -t "$session" -n factures-front -c "$base_dir/wavy-factures-front" \
  'npm start'

echo "Session tmux demarree: $session"
echo "Attacher: tmux attach -t $session"

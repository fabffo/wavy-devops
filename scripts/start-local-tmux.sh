#!/usr/bin/env bash
set -e

SESSION="wavy-local"

# Stop ancienne session si elle existe
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Création session
tmux new-session -d -s "$SESSION" -n socle-api

tmux send-keys -t "$SESSION:socle-api" \
"cd ~/projets/wavy-socle-api && ./mvnw spring-boot:run -Dspring-boot.run.profiles=local" C-m

tmux new-window -t "$SESSION" -n tiers-api
tmux send-keys -t "$SESSION:tiers-api" \
"cd ~/projets/wavy-tiers-api && mvn spring-boot:run -Dspring-boot.run.profiles=local" C-m

tmux new-window -t "$SESSION" -n contrats-api
tmux send-keys -t "$SESSION:contrats-api" \
"cd ~/projets/wavy-contrats-api && ./mvnw spring-boot:run -Dspring-boot.run.profiles=local" C-m

tmux new-window -t "$SESSION" -n factures-api
tmux send-keys -t "$SESSION:factures-api" \
"cd ~/projets/wavy-factures-api && set -a && source ~/projets/wavy-devops/.env.pur-local && set +a && ./mvnw spring-boot:run -Dspring-boot.run.profiles=local" C-m

tmux new-window -t "$SESSION" -n gateway
tmux send-keys -t "$SESSION:gateway" \
"cd ~/projets/wavy-gateway && ./mvnw spring-boot:run -Dspring-boot.run.profiles=local" C-m

tmux new-window -t "$SESSION" -n socle-front
tmux send-keys -t "$SESSION:socle-front" \
"cd ~/projets/wavy-socle-front && npm start" C-m

tmux new-window -t "$SESSION" -n tiers-front
tmux send-keys -t "$SESSION:tiers-front" \
"cd ~/projets/wavy-tiers-front && npm start" C-m

tmux new-window -t "$SESSION" -n contrats-front
tmux send-keys -t "$SESSION:contrats-front" \
"cd ~/projets/wavy-contrats-front && npm start" C-m

tmux new-window -t "$SESSION" -n factures-front
tmux send-keys -t "$SESSION:factures-front" \
"cd ~/projets/wavy-factures-front && npm start" C-m

tmux new-window -t "$SESSION" -n wavy-pwa
tmux send-keys -t "$SESSION:wavy-pwa" \
"cd ~/projets/wavy-pwa && npm start" C-m

echo "Session tmux locale démarrée : $SESSION"
echo ""
echo "APIs :"
echo "- Socle    : http://localhost:8080"
echo "- Tiers    : http://localhost:8081"
echo "- Contrats : http://localhost:8082"
echo "- Factures : http://localhost:8083"
echo "- Gateway  : http://localhost:8088"
echo ""
echo "Fronts :"
echo "- Socle    : http://localhost:4200"
echo "- Tiers    : http://localhost:4201"
echo "- Contrats : http://localhost:4202"
echo "- Factures : http://localhost:4203"
echo "- Wavy PWA : http://localhost:4204"
echo ""
echo "Pour ouvrir tmux :"
echo "tmux attach -t $SESSION"

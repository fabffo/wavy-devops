#!/usr/bin/env bash
# Diagnostic global de l'environnement Wavy.
# Ce script s'appuie sur scripts/_common.sh pour les chemins, couleurs,
# conventions Docker Compose et noms de services/conteneurs.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

DOCTOR_ENV="${WAVY_ENV:-recette}"
ISSUES=()
SUMMARY=()

RECETTE_PORTS=(28080 28081 28082 28083 28086 28088 24200 24201 24202 24203 24204 24206)
TOOLS=(docker git java mvn node npm ng)
AI_VARS=(
  WAVY_AI_PROVIDER
  WAVY_AI_MODEL
  WAVY_AI_API_KEY
  WAVY_AI_TIMEOUT_SECONDS
  WAVY_AI_MAX_FILE_SIZE_MB
)
APP_SERVICES=(
  socle-api
  tiers-api
  contrats-api
  factures-api
  tresorerie-api
  gateway
  socle-front
  tiers-front
  contrats-front
  factures-front
  tresorerie-front
  pwa
)
DBS=(socle tiers contrats factures tresorerie)

print_header() {
  printf "\n${BLUE}==============================${NC}\n"
  printf "${BLUE}         WAVY DOCTOR${NC}\n"
  printf "${BLUE}==============================${NC}\n\n"
}

add_issue() {
  ISSUES+=("$1")
}

summary_line() {
  SUMMARY+=("$1|$2")
}

ok() {
  printf "${GREEN}✔${NC} %s\n" "$1"
}

ko() {
  printf "${RED}✘${NC} %s\n" "$1"
  add_issue "$1"
}

notice() {
  printf "${YELLOW}!${NC} %s\n" "$1"
}

version_or_absent() {
  local command_name="$1"
  local version=""

  if ! command -v "$command_name" >/dev/null 2>&1; then
    ko "$command_name introuvable"
    summary_line "$command_name" "${RED}✘${NC}"
    return
  fi

  case "$command_name" in
    docker) version="$(docker --version 2>/dev/null | sed 's/^Docker version //; s/,.*//')" ;;
    git) version="$(git --version 2>/dev/null | awk '{print $3}')" ;;
    java) version="$(java -version 2>&1 | awk -F\" '/version/ {print $2; exit}')" ;;
    mvn) version="$(mvn -version 2>/dev/null | awk 'NR==1 {print $3}')" ;;
    node) version="$(node --version 2>/dev/null)" ;;
    npm) version="$(npm --version 2>/dev/null)" ;;
    ng) version="$(ng version 2>/dev/null | awk -F: '/Angular CLI/ {gsub(/^[ \t]+/, "", $2); print $2; exit}')" ;;
  esac

  [[ -n "$version" ]] || version="version détectée"
  ok "$command_name $version"
  summary_line "$command_name" "${GREEN}✔${NC} $version"
}

check_environment() {
  info "Environnement"
  for tool in "${TOOLS[@]}"; do
    version_or_absent "$tool"
  done

  if docker info >/dev/null 2>&1; then
    ok "Docker Engine actif"
    summary_line "Docker Engine" "${GREEN}✔${NC}"
  else
    ko "Docker Engine inactif ou inaccessible"
    summary_line "Docker Engine" "${RED}✘${NC}"
  fi

  if docker compose version >/dev/null 2>&1; then
    local compose_version
    compose_version="$(docker compose version --short 2>/dev/null || docker compose version 2>/dev/null)"
    ok "Docker Compose v2 $compose_version"
    summary_line "Docker Compose" "${GREEN}✔${NC} $compose_version"
  else
    ko "Docker Compose v2 indisponible"
    summary_line "Docker Compose" "${RED}✘${NC}"
  fi
}

check_wsl() {
  info "Plateforme"
  if grep -qi microsoft /proc/version 2>/dev/null; then
    ok "Ubuntu WSL détecté"
    summary_line "Plateforme" "${GREEN}✔${NC} WSL"
  else
    ok "Linux natif détecté"
    summary_line "Plateforme" "${GREEN}✔${NC} Linux natif"
  fi
}

check_repository() {
  info "Répertoire"
  if [[ "$(basename "$ROOT_DIR")" == "wavy-devops" && -f "$ROOT_DIR/docker-compose.recette.yml" ]]; then
    ok "Répertoire wavy-devops : $ROOT_DIR"
    summary_line "wavy-devops" "${GREEN}✔${NC}"
  else
    ko "Le script doit être lancé depuis le dépôt wavy-devops"
    summary_line "wavy-devops" "${RED}✘${NC}"
  fi
}

check_required_files() {
  info "Fichiers attendus"
  local file
  for file in docker-compose.local.yml docker-compose.recette.yml .env.local .env.recette; do
    if [[ -f "$ROOT_DIR/$file" ]]; then
      ok "$file présent"
      summary_line "$file" "${GREEN}✔${NC}"
    else
      ko "$file absent"
      summary_line "$file" "${RED}✘${NC}"
    fi
  done
}

env_value_present() {
  local env="$1"
  local key="$2"
  local file value
  file="$(env_file "$env")"
  [[ -f "$file" ]] || return 1
  value="$(awk -F= -v key="$key" '$1 == key { value=$0; sub(/^[^=]*=/, "", value); print value }' "$file" 2>/dev/null | tail -n 1)"
  [[ -n "$value" ]]
}

env_value_raw() {
  local env="$1"
  local key="$2"
  local file
  file="$(env_file "$env")"
  awk -F= -v key="$key" '$1 == key { value=$0; sub(/^[^=]*=/, "", value); print value }' "$file" 2>/dev/null | tail -n 1
}

check_ai_variables() {
  info "Variables IA (.env.recette)"
  local key value
  for key in "${AI_VARS[@]}"; do
    if env_value_present recette "$key"; then
      if [[ "$key" == "WAVY_AI_API_KEY" ]]; then
        ok "$key configurée"
        summary_line "AI Key" "${GREEN}✔${NC} configurée"
      else
        value="$(env_value_raw recette "$key")"
        ok "$key=$value"
        summary_line "${key#WAVY_}" "${GREEN}✔${NC} $value"
      fi
    else
      ko "$key absente dans .env.recette"
      if [[ "$key" == "WAVY_AI_API_KEY" ]]; then
        summary_line "AI Key" "${RED}✘${NC} absente"
      else
        summary_line "${key#WAVY_}" "${RED}✘${NC} absente"
      fi
    fi
  done
}

container_state() {
  local container="$1"
  docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || printf 'absent'
}

container_health() {
  local container="$1"
  docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$container" 2>/dev/null || printf '-'
}

format_state() {
  local state="$1"
  case "$state" in
    running) printf "${GREEN}Running${NC}" ;;
    exited|dead|created) printf "${RED}Stopped${NC}" ;;
    absent) printf "${RED}Absent${NC}" ;;
    *) printf "${YELLOW}%s${NC}" "$state" ;;
  esac
}

format_health() {
  local health="$1"
  case "$health" in
    healthy) printf "${GREEN}Healthy${NC}" ;;
    unhealthy) printf "${RED}Unhealthy${NC}" ;;
    starting) printf "${YELLOW}Starting${NC}" ;;
    -) printf "-" ;;
    *) printf "%s" "$health" ;;
  esac
}

check_container() {
  local label="$1"
  local container="$2"
  local state health
  state="$(container_state "$container")"
  health="$(container_health "$container")"
  printf "%-30s %-36s %-18b %-18b\n" "$label" "$container" "$(format_state "$state")" "$(format_health "$health")"

  if [[ "$state" == "running" && "$health" != "unhealthy" ]]; then
    summary_line "$label" "${GREEN}✔${NC}"
  else
    add_issue "$label non opérationnel ($container : $state/$health)"
    summary_line "$label" "${RED}✘${NC}"
  fi
}

check_containers() {
  info "Conteneurs applicatifs Wavy ($DOCTOR_ENV)"
  printf "%-30s %-36s %-18s %-18s\n" "Composant" "Conteneur" "Etat" "Health"
  printf "%-30s %-36s %-18s %-18s\n" "---------" "---------" "----" "------"

  local logical
  for logical in "${APP_SERVICES[@]}"; do
    check_container "$logical" "$(service_name "$logical" "$DOCTOR_ENV")"
  done
}

check_databases() {
  info "Bases PostgreSQL ($DOCTOR_ENV)"
  printf "%-30s %-36s %-18s %-18s\n" "Base" "Conteneur" "Etat" "Health"
  printf "%-30s %-36s %-18s %-18s\n" "----" "---------" "----" "------"

  local db
  for db in "${DBS[@]}"; do
    check_container "$db-db" "$(db_container "$db" "$DOCTOR_ENV")"
  done
}

port_open() {
  local port="$1"
  timeout 2 bash -c "</dev/tcp/127.0.0.1/$port" >/dev/null 2>&1
}

check_ports() {
  info "Ports recette"
  local port
  for port in "${RECETTE_PORTS[@]}"; do
    if port_open "$port"; then
      ok "Port $port ouvert"
      summary_line "Port $port" "${GREEN}✔${NC}"
    else
      ko "Port $port fermé ou inaccessible"
      summary_line "Port $port" "${RED}✘${NC}"
    fi
  done
}

http_get() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 5 "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- --timeout=5 "$url"
  else
    return 127
  fi
}

check_health_endpoint() {
  local label="$1"
  local url="$2"
  local body=""

  if ! body="$(http_get "$url" 2>/dev/null)"; then
    printf "%-18s ${RED}DOWN${NC} %s\n" "$label" "$url"
    add_issue "$label DOWN"
    summary_line "$label" "${RED}✘${NC} DOWN"
    return
  fi

  if printf '%s' "$body" | grep -q '"status"[[:space:]]*:[[:space:]]*"UP"'; then
    printf "%-18s ${GREEN}UP${NC} %s\n" "$label" "$url"
    summary_line "$label" "${GREEN}✔${NC} UP"
  else
    printf "%-18s ${YELLOW}REPONSE NON UP${NC} %s\n" "$label" "$url"
    add_issue "$label ne renvoie pas status=UP"
    summary_line "$label" "${YELLOW}!${NC}"
  fi
}

check_health_checks() {
  info "Health checks HTTP"
  if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    notice "curl ou wget est nécessaire pour tester les endpoints HTTP"
    add_issue "Health checks HTTP non testés : curl/wget absents"
    return
  fi

  check_health_endpoint "Gateway" "http://localhost:28088/actuator/health"
  check_health_endpoint "Socle API" "http://localhost:28080/actuator/health"
  check_health_endpoint "Tiers API" "http://localhost:28081/actuator/health"
  check_health_endpoint "Contrats API" "http://localhost:28082/actuator/health"
  check_health_endpoint "Factures API" "http://localhost:28083/actuator/health"
}

check_compose_usage() {
  info "Utilisation de docker compose dans scripts/"
  local violations=()
  local line file lineno content

  while IFS= read -r line; do
    file="${line%%:*}"
    lineno="${line#*:}"
    lineno="${lineno%%:*}"
    content="${line#*:*:}"

    [[ "$content" == *"docker compose version"* ]] && continue
    [[ "$content" == *"--env-file"* ]] && continue
    violations+=("$file:$lineno:$content")
  done < <(rg -n '^[[:space:]]*(timeout[[:space:]]+[^[:space:]]+[[:space:]]+)?docker[[:space:]]+compose\b' "$SCRIPT_DIR" --glob '*.sh' || true)

  if (( ${#violations[@]} == 0 )); then
    ok "Tous les appels directs à docker compose utilisent --env-file"
    summary_line "Compose env-file" "${GREEN}✔${NC}"
    return
  fi

  ko "Des appels docker compose sans --env-file ont été détectés"
  summary_line "Compose env-file" "${RED}✘${NC}"
  printf "%s\n" "${violations[@]}" | sed 's/^/  - /'
}

print_recommendations() {
  local issue
  if (( ${#ISSUES[@]} == 0 )); then
    return
  fi

  printf "\n${YELLOW}Recommandations${NC}\n"
  for issue in "${ISSUES[@]}"; do
    case "$issue" in
      *"Factures API DOWN"*|*"factures-api non opérationnel"*)
        printf "\nFactures API DOWN\nCommande conseillée :\n./scripts/restart-factures-api.sh\n"
        ;;
      *"Tiers API DOWN"*|*"tiers-api non opérationnel"*)
        printf "\nTiers API DOWN\nCommande conseillée :\n./scripts/restart-tiers-api.sh\n"
        ;;
      *"Contrats API DOWN"*|*"contrats-api non opérationnel"*)
        printf "\nContrats API DOWN\nCommande conseillée :\n./scripts/restart-contrats-api.sh\n"
        ;;
      *"Socle API DOWN"*|*"socle-api non opérationnel"*)
        printf "\nSocle API DOWN\nCommande conseillée :\n./scripts/restart-socle-api.sh\n"
        ;;
      *"Gateway DOWN"*|*"gateway non opérationnel"*)
        printf "\nGateway DOWN\nCommande conseillée :\n./scripts/restart-gateway.sh\n"
        ;;
      *"WAVY_AI_API_KEY absente"*)
        printf "\nClé IA absente\nCommande conseillée :\ndocker compose --env-file .env.recette -p wavy-recette -f docker-compose.recette.yml up -d --force-recreate wavy-factures-api-recette\n"
        ;;
      *"Docker Engine inactif"*)
        printf "\nDocker Engine inactif\nCommande conseillée :\nsudo service docker start\n"
        ;;
      *"Port "*)
        printf "\n%s\nVérifier le conteneur associé avec :\n./scripts/status.sh\n" "$issue"
        ;;
    esac
  done
}

print_summary() {
  printf "\n${BLUE}==============================${NC}\n"
  printf "${BLUE}Résumé${NC}\n"
  printf "${BLUE}==============================${NC}\n\n"

  local entry label value
  for entry in "${SUMMARY[@]}"; do
    label="${entry%%|*}"
    value="${entry#*|}"
    printf "%-28s %b\n" "$label" "$value"
  done

  printf "\n${BLUE}==============================${NC}\n"
  if (( ${#ISSUES[@]} == 0 )); then
    printf "${GREEN}Aucune anomalie détectée${NC}\n"
  else
    printf "${RED}%d anomalie(s) détectée(s)${NC}\n" "${#ISSUES[@]}"
  fi
}

main() {
  print_header
  check_environment
  check_wsl
  check_repository
  check_required_files
  check_ai_variables

  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    check_containers
    check_databases
    check_ports
    check_health_checks
  else
    notice "Les diagnostics Docker, ports et health checks sont ignorés car Docker n'est pas disponible."
  fi

  check_compose_usage
  print_summary
  print_recommendations
}

main "$@"

#!/usr/bin/env bash
# Test destructif, réservé à une stack éphémère explicitement nommée.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
require_docker
[[ "${WAVY_CONFIRM_FROM_ZERO_TEST:-}" == "ERASE_EPHEMERAL_DATABASES" ]] \
  || die "Définir WAVY_CONFIRM_FROM_ZERO_TEST=ERASE_EPHEMERAL_DATABASES pour lancer ce test destructif."
[[ "$(env_value preprod COMPOSE_PROJECT_NAME '')" == "wavy-preprod-from-zero" ]] \
  || die "Utiliser une copie .env.preprod avec COMPOSE_PROJECT_NAME=wavy-preprod-from-zero."
for db in socle tiers contrats factures tresorerie; do
  [[ -z "$(docker ps -aq --filter "name=^/$(db_container "$db" preprod)$")" ]] \
    || die "Une préproduction existe déjà. Exécuter ce test exclusivement sur un runner Docker isolé."
done
trap 'compose preprod down --volumes --remove-orphans >/dev/null 2>&1 || true' EXIT
info "Suppression des seuls volumes du projet éphémère wavy-preprod-from-zero..."
compose preprod down --volumes --remove-orphans
compose preprod up -d --wait
for db in socle tiers contrats factures tresorerie; do
  container="$(db_container "$db" preprod)"
  migrations="$(docker exec "$container" psql -U "$(db_user "$db" preprod)" -d "$(db_name "$db" preprod)" -Atc "select count(*) from flyway_schema_history where success" 2>/dev/null || true)"
  [[ "$migrations" =~ ^[1-9][0-9]*$ ]] || die "Aucune migration Flyway validée pour $db."
  success " $db reconstruite depuis zéro ($migrations migrations)."
done
socle_container="$(db_container socle preprod)"
socle_user="$(db_user socle preprod)"
socle_name="$(db_name socle preprod)"
bootstrap_counts="$(docker exec "$socle_container" psql -U "$socle_user" -d "$socle_name" -Atc \
  "select (select count(*) from tenant), (select count(*) from societe_interne),
          (select count(*) from utilisateur),
          (select count(*) from utilisateur_role ur join role r on r.id=ur.role_id where r.code='ADMIN_TENANT'),
          (select count(*) from parametre_tenant where categorie in ('DELAI_PAIEMENT','FAMILLE_ACTIVITE_CONTRAT')),
          (select count(*) from utilisateur where mot_de_passe_a_changer);" )"
IFS='|' read -r tenants societes utilisateurs admins references mots_de_passe_a_changer <<<"$bootstrap_counts"
[[ "$tenants" == 1 && "$societes" == 1 && "$utilisateurs" == 1 && "$admins" == 1 && "$references" -ge 9 && "$mots_de_passe_a_changer" == 1 ]] \
  || die "Bootstrap Socle invalide : $bootstrap_counts"
success " Bootstrap validé : un tenant, une société, un administrateur et $references paramètres."
"$ROOT_DIR/wavy" health preprod
success " Test database-from-zero terminé."

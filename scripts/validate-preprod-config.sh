#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

preprod_env="$(env_file preprod)"
[[ -f "$preprod_env" ]] || die "Créer .env.preprod depuis .env.preprod.example."

required=(
  WAVY_IMAGE_REGISTRY WAVY_IMAGE_TAG WAVY_PUBLIC_URL WAVY_CORS_ALLOWED_ORIGIN_PATTERNS
  WAVY_SOCLE_DB_PASSWORD WAVY_TIERS_DB_PASSWORD WAVY_CONTRATS_DB_PASSWORD
  WAVY_FACTURES_DB_PASSWORD WAVY_TRESORERIE_DB_PASSWORD WAVY_SESSION_SECRET
  WAVY_BOOTSTRAP_TENANT_CODE WAVY_BOOTSTRAP_TENANT_NAME WAVY_BOOTSTRAP_COMPANY_NAME
  WAVY_BOOTSTRAP_COMPANY_SIREN WAVY_BOOTSTRAP_ADMIN_EMAIL WAVY_BOOTSTRAP_ADMIN_PASSWORD
  WAVY_BACKUP_ENCRYPTION_PASSPHRASE
)
for key in "${required[@]}"; do
  value="$(env_value preprod "$key" '')"
  [[ -n "$value" && "$value" != *CHANGE_ME* ]] || die "$key est absent ou conserve une valeur d'exemple."
done

tag="$(env_value preprod WAVY_IMAGE_TAG '')"
[[ "$tag" != latest ]] || die "Le tag latest est interdit."
[[ "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{6,127}$ ]] || die "WAVY_IMAGE_TAG doit être une version ou un SHA identifiable."
[[ "$(env_value preprod WAVY_PUBLIC_URL '')" == https://* ]] || die "WAVY_PUBLIC_URL doit utiliser HTTPS."
[[ "$(env_value preprod WAVY_BOOTSTRAP_COMPANY_SIREN '')" =~ ^[0-9]{9}$ ]] || die "Le SIREN bootstrap doit contenir 9 chiffres."
admin_password="$(env_value preprod WAVY_BOOTSTRAP_ADMIN_PASSWORD '')"
[[ "${#admin_password}" -ge 12 ]] || die "Le mot de passe bootstrap doit contenir au moins 12 caractères."

require_docker
compose preprod config --quiet
if compose preprod config | awk '/^[[:space:]]+(socle|tiers|contrats|factures|tresorerie)-postgres:/{db=1} db && /^[[:space:]]+ports:/{exit 1} db && /^[[:space:]]{2}[^[:space:]].*:/{db=0}'; then
  :
else
  die "Une base PostgreSQL préproduction expose un port hôte."
fi
success " Configuration préproduction valide, sans secret d'exemple ni tag mutable."

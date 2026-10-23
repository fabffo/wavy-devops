#!/usr/bin/env bash
# Candidat inactif : sans --execute-on-approved-host, aucune opération runtime.
set -euo pipefail
umask 077
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_pwa_preprod.py" "$@"

#!/usr/bin/env bash
# Build + restart du point d'entrée Wavy ERP pour l'environnement sélectionné.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
restart_service erp-shell

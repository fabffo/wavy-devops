#!/usr/bin/env bash
# Build + restart de la PWA, puis affichage des logs récents.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
restart_service pwa

#!/usr/bin/env bash
# Build + restart du Tiers API, puis affichage des logs récents.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
restart_service tiers-api

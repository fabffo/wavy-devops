#!/usr/bin/env bash
set -euo pipefail

session="${WAVY_TMUX_SESSION:-wavy-local}"
tmux kill-session -t "$session" 2>/dev/null || true
echo "Session tmux arretee: $session"

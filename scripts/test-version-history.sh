#!/usr/bin/env bash
# Tests locaux isolés des fonctions d'historique version/digest.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_command flock
require_command timeout
test_root="$(mktemp -d "${TMPDIR:-/tmp}/wavy-version-history-test.XXXXXX")"
trap 'find "$test_root" -mindepth 1 -delete 2>/dev/null || true; rmdir "$test_root" 2>/dev/null || true' EXIT
ROOT_DIR="$test_root"

digest_a=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
digest_b=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
file="$(validated_history_file test component-api)"

fail() { printf 'KO  %s\n' "$*" >&2; exit 1; }
pass() { printf 'OK  %s\n' "$*"; }

record_validated_image test component-api 1.0.0-abc1234 "$digest_a" abc1234
[[ -f "$file" ]] || fail "création du fichier historique"
pass "ajout d'une nouvelle version"

[[ "$(get_validated_digest test component-api 1.0.0-abc1234)" == "$digest_a" ]] \
  || fail "lecture du digest"
pass "lecture du digest validé"

record_validated_image test component-api 1.0.0-abc1234 "$digest_a" abc1234
[[ "$(awk -F '\t' '$1 == "1.0.0-abc1234" {count++} END {print count+0}' "$file")" == 1 ]] \
  || fail "le couple identique a été dupliqué"
pass "répétition idempotente sans doublon"

if bash -c '
  source "$1"
  ROOT_DIR="$2"
  record_validated_image test component-api 1.0.0-abc1234 "$3" def5678
' _ "$SCRIPT_DIR/_common.sh" "$test_root" "$digest_b" >/dev/null 2>&1; then
  fail "un digest différent a été accepté"
fi
pass "refus du changement de digest"

if bash -c '
  source "$1"
  ROOT_DIR="$2"
  get_validated_digest test component-api 9.9.9-inconnue
' _ "$SCRIPT_DIR/_common.sh" "$test_root" >/dev/null 2>&1; then
  fail "une version inconnue a été acceptée"
fi
pass "refus d'une version inconnue"

if bash -c '
  source "$1"
  ROOT_DIR="$2"
  get_validated_digest absent component-api 1.0.0
' _ "$SCRIPT_DIR/_common.sh" "$test_root" >/dev/null 2>&1; then
  fail "un historique absent a été accepté"
fi
pass "refus d'un fichier historique absent"

[[ "$(head -n 1 "$file")" == $'version\tdigest\tcommit\tdate_validation' ]] \
  || fail "en-tête TSV altéré"
[[ "$(grep -c '^version' "$file")" == 1 ]] || fail "en-tête TSV dupliqué"
pass "conservation de l'en-tête TSV"

exec 9>>"$file"
flock -x 9
if timeout 0.2 bash -c '
  source "$1"
  ROOT_DIR="$2"
  record_validated_image test component-api 2.0.0-def5678 "$3" def5678
' _ "$SCRIPT_DIR/_common.sh" "$test_root" "$digest_b" >/dev/null 2>&1; then
  fail "le verrou flock n'a pas bloqué une écriture concurrente"
else
  [[ "$?" == 124 ]] || fail "le test flock a échoué pour une autre raison"
fi
flock -u 9
record_validated_image test component-api 2.0.0-def5678 "$digest_b" def5678
pass "verrouillage flock puis reprise de l'écriture"

printf 'Tests historique version/digest : OK\n'

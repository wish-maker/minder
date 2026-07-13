#!/usr/bin/env bash
# Verify the ported start_services (scripts/setup/lifecycle.py) behaves identically
# to scripts/lib/lifecycle.sh under DRY_RUN=1. Non-destructive: every `compose up`
# is dry-run-gated (prints only). Exercises BOTH ollama branches (internal vs
# external) by controlling .env's OLLAMA_BASE_URL, and checks the resulting
# COMPOSE_PROFILES. Operates on the REAL repo .env — backs it up and ALWAYS
# restores. NOTE: start_services sleeps ~28s per run (faithful), so this is slow.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root
BAK="$(mktemp)"; HAD_ENV=0
[ -f .env ] && { cp .env "$BAK"; HAD_ENV=1; }
restore() { if [ "$HAD_ENV" = 1 ]; then cp "$BAK" .env; else rm -f .env; fi; rm -f "$BAK"; }
trap restore EXIT

bsh() { SCRIPT_DIR="$PWD" DRY_RUN=1 bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1
  unset COMPOSE_PROFILES
  source scripts/lib/config.sh    >/dev/null 2>&1
  source scripts/lib/log.sh       >/dev/null 2>&1
  source scripts/lib/docker.sh    >/dev/null 2>&1
  source scripts/lib/env.sh       >/dev/null 2>&1
  source scripts/lib/lifecycle.sh >/dev/null 2>&1
  '"$1"; }
pyi() { DRY_RUN=1 "$PY" -c "
import os
os.environ.pop('COMPOSE_PROFILES', None)
from scripts.setup import config, docker, env, lifecycle
config.DRY_RUN = True
$1"; }

# Normalize like the gate: strip up to last CR (spinner), ANSI, the compose-file
# path (OS-specific), the timestamp, the _cleanup epilogue; collapse blank lines.
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's#[^[:space:]]*docker-compose\.yml#COMPOSE#g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

FAIL=0
run_case() {  # $1=name  $2=.env-content
  printf '%s' "$2" > .env
  local b p
  b="$(bsh 'start_services; echo "PROFILES=${COMPOSE_PROFILES:-}"' 2>&1)"
  p="$(pyi 'lifecycle.start_services(); print("PROFILES="+os.environ.get("COMPOSE_PROFILES",""))' 2>&1)"
  local bn pn; bn="$(printf '%s' "$b" | norm)"; pn="$(printf '%s' "$p" | norm)"
  if [ "$bn" = "$pn" ]; then echo "PASS  start_services $1"
  else FAIL=1; echo "FAIL  start_services $1"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; fi
}

run_case "internal (empty OLLAMA_BASE_URL)" $'OLLAMA_BASE_URL=\n'
run_case "external (OLLAMA_BASE_URL set)"   $'OLLAMA_BASE_URL=http://gpu-node:11434\n'

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

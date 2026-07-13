#!/usr/bin/env bash
# Verify the ported download_ollama_models (scripts/setup/health.py) vs health.sh
# under DRY_RUN=1: external mode (OLLAMA_BASE_URL set → skip) and internal mode
# (wait for the ollama container, then pull each model — the pull is `run … &>/dev/null`
# so it's gated + silent under dry-run). The installed-model listing at the end is
# live/non-deterministic, so its count is masked and its rows dropped. Operates on
# the REAL repo .env — backs it up and ALWAYS restores. Spinner + sleep disabled.
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2
BAK="$(mktemp)"; HAD_ENV=0
[ -f .env ] && { cp .env "$BAK"; HAD_ENV=1; }
restore() { if [ "$HAD_ENV" = 1 ]; then cp "$BAK" .env; else rm -f .env; fi; rm -f "$BAK"; }
trap restore EXIT

bsh() { SCRIPT_DIR="$PWD" DRY_RUN=1 bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  source scripts/lib/docker.sh >/dev/null 2>&1
  source scripts/lib/env.sh    >/dev/null 2>&1
  source scripts/lib/health.sh >/dev/null 2>&1
  spinner_start() { :; }; spinner_stop() { :; }; sleep() { :; }
  '"$1"; }
pyi() { DRY_RUN=1 "$PY" -c "
import time
from scripts.setup import config, docker, env, health, log
config.DRY_RUN = True
log.spinner_start = lambda *a, **k: None
log.spinner_stop = lambda *a, **k: None
time.sleep = lambda *a, **k: None
$1"; }

# ANSI + CR + timestamps; mask the installed-count line + drop the live listing
# rows that follow it; drop epilogue/blanks.
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's/[0-9]+ model\(s\) available/N model(s) available/' \
                -e '/model\(s\) available/,$ {/model\(s\) available/!d}' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

FAIL=0
cmp() { local n="$1"; printf '%s' "$2" > .env
  local b p; b="$(bsh 'download_ollama_models' 2>&1 | norm)"; p="$(pyi 'health.download_ollama_models()' 2>&1 | norm)"
  if [ "$b" = "$p" ]; then echo "PASS  $n"
  else FAIL=1; echo "FAIL  $n"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi; }

cmp "external (skip)" $'OLLAMA_BASE_URL=http://gpu-node:11434\n'
cmp "internal (pull)" $'OLLAMA_BASE_URL=\nOLLAMA_AUTOMATIC_PULL=true\nOLLAMA_MODELS=llama3.2,nomic-embed-text\n'

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

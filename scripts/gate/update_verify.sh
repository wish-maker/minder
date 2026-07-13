#!/usr/bin/env bash
# Verify the ported `update` verb (scripts/setup/update.py) vs bash cmd_update on
# the DETERMINISTIC path (SKIP_VERSION_CHECK=1 + DRY_RUN=1): --check runs
# version_drift_report (all up-to-date), full update runs pull_all_images (gated) +
# a silent rebuild + the rolling restart (gated `compose up` per running service).
# Spinner + sleep are disabled on both sides (transient / timing) so the [dry-run]
# trace compares cleanly and fast.
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2

bsh() { SCRIPT_DIR="$PWD" DRY_RUN=1 SKIP_VERSION_CHECK=true bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1; SKIP_VERSION_CHECK=true
  SCRIPT_NAME="setup.sh"   # setup.sh sets this from BASH_SOURCE; source-and-call does not
  source scripts/lib/config.sh   >/dev/null 2>&1
  source scripts/lib/log.sh      >/dev/null 2>&1
  source scripts/lib/docker.sh   >/dev/null 2>&1
  source scripts/lib/cache.sh    >/dev/null 2>&1
  source scripts/lib/versions.sh >/dev/null 2>&1
  source scripts/lib/commands.sh >/dev/null 2>&1
  spinner_start() { :; }; spinner_stop() { :; }; sleep() { :; }
  '"$1"; }
pyi() { DRY_RUN=1 SKIP_VERSION_CHECK=true "$PY" -c "
import time
from scripts.setup import config, log, update
config.DRY_RUN = True
config.SKIP_VERSION_CHECK = True
log.spinner_start = lambda *a, **k: None
log.spinner_stop = lambda *a, **k: None
time.sleep = lambda *a, **k: None
$1"; }

# spinner already disabled; strip any CR + ANSI + timestamps, collapse the compose
# path (OS-specific), drop the _cleanup epilogue + blank lines.
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[^[:space:]]*docker-compose\.yml#COMPOSE#g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

FAIL=0
cmp() { local n="$1" b p; b="$(printf '%s' "$2" | norm)"; p="$(printf '%s' "$3" | norm)"
  if [ "$b" = "$p" ]; then echo "PASS  $n"
  else FAIL=1; echo "FAIL  $n"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi; }

cmp "update --check" \
  "$(bsh 'cmd_update --check' 2>&1)" \
  "$(pyi 'update.run("--check")' 2>&1)"
cmp "update (full, dry+skip)" \
  "$(bsh 'cmd_update' 2>&1)" \
  "$(pyi 'update.run()' 2>&1)"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

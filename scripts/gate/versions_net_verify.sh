#!/usr/bin/env bash
# Verify the ported versions orchestration (scripts/setup/versions.py) vs
# versions.sh on its DETERMINISTIC path: under SKIP_VERSION_CHECK=1 + DRY_RUN=1,
# resolve_image_tag short-circuits to the pin (no network), pull_all_images gates
# every `docker pull`, and version_drift_report reports all-up-to-date. That's the
# path install/update/doctor run under the gate. (The live smart-resolution branch
# — list_tags + manifest probes — hits real registries and isn't compared here.)
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2

# The spinner is a background subshell (bash) / daemon thread (python) whose \r
# frames interleave non-deterministically with the [dry-run] pull output. It is
# transient UX (normalized away everywhere else), so disable it on BOTH sides to
# get a clean, comparable command trace + success lines.
bsh() { SCRIPT_DIR="$PWD" DRY_RUN=1 SKIP_VERSION_CHECK=true bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1; SKIP_VERSION_CHECK=true
  source scripts/lib/config.sh   >/dev/null 2>&1
  source scripts/lib/log.sh      >/dev/null 2>&1
  source scripts/lib/docker.sh   >/dev/null 2>&1
  source scripts/lib/cache.sh    >/dev/null 2>&1
  source scripts/lib/versions.sh >/dev/null 2>&1
  spinner_start() { :; }; spinner_stop() { :; }
  '"$1"; }
pyi() { DRY_RUN=1 SKIP_VERSION_CHECK=true "$PY" -c "
from scripts.setup import config, versions, log
config.DRY_RUN = True
config.SKIP_VERSION_CHECK = True
log.spinner_start = lambda *a, **k: None
log.spinner_stop = lambda *a, **k: None
$1"; }

# Normalize: spinner (strip to last CR), ANSI, timestamps, ISO dates, epilogue, blanks.
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's/[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z/DATE/g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

FAIL=0
cmp() { local n="$1" b p; b="$(printf '%s' "$2" | norm)"; p="$(printf '%s' "$3" | norm)"
  if [ "$b" = "$p" ]; then echo "PASS  $n"
  else FAIL=1; echo "FAIL  $n"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi; }

cmp "pull_all_images (dry+skip)" \
  "$(bsh 'pull_all_images' 2>&1)" \
  "$(pyi 'versions.pull_all_images()' 2>&1)"
cmp "version_drift_report (human)" \
  "$(bsh 'version_drift_report' 2>&1)" \
  "$(pyi 'versions.version_drift_report()' 2>&1)"
cmp "version_drift_report (json)" \
  "$(bsh 'version_drift_report true' 2>&1)" \
  "$(pyi 'versions.version_drift_report(json_mode=True)' 2>&1)"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

#!/usr/bin/env bash
# Verify the ported infra helpers (scripts/setup/infra.py) vs scripts/lib/infra.sh
# under DRY_RUN=1, against the LIVE stack.
#  - create_networks: dry-run-gated `docker network create` + read-only probe.
#  - initialize_database / initialize_minio: the compose ups are gated; the CREATE
#    DATABASE / mc bucket ops are un-gated but IDEMPOTENT, so on a stack where all
#    aux DBs + buckets already exist they are a safe no-op ("Already exists" for
#    each). The spinner (wait_*) + the minio `sleep 5` are disabled on both sides.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root

bsh() { SCRIPT_DIR="$PWD" DRY_RUN=1 bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  source scripts/lib/docker.sh >/dev/null 2>&1
  source scripts/lib/env.sh    >/dev/null 2>&1
  source scripts/lib/infra.sh  >/dev/null 2>&1
  spinner_start() { :; }; spinner_stop() { :; }; sleep() { :; }
  '"$1"; }
pyi() { DRY_RUN=1 "$PY" -c "
import time
from scripts.setup import config, docker, env, infra, log
config.DRY_RUN = True
log.spinner_start = lambda *a, **k: None
log.spinner_stop = lambda *a, **k: None
time.sleep = lambda *a, **k: None
$1"; }

norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[^[:space:]]*docker-compose\.yml#COMPOSE#g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

FAIL=0
cmp() { local n="$1" b p; b="$(printf '%s' "$2" | norm)"; p="$(printf '%s' "$3" | norm)"
  if [ "$b" = "$p" ]; then echo "PASS  $n"
  else FAIL=1; echo "FAIL  $n"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi; }

cmp "create_networks"     "$(bsh 'create_networks' 2>&1)"     "$(pyi 'infra.create_networks()' 2>&1)"
cmp "initialize_database" "$(bsh 'initialize_database' 2>&1)" "$(pyi 'infra.initialize_database()' 2>&1)"
cmp "initialize_minio"    "$(bsh 'initialize_minio' 2>&1)"    "$(pyi 'infra.initialize_minio()' 2>&1)"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

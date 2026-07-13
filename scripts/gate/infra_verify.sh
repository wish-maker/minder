#!/usr/bin/env bash
# Verify the ported create_networks (scripts/setup/infra.py) behaves identically
# to scripts/lib/infra.sh under DRY_RUN=1. Non-destructive: the `docker network
# create` is dry-run-gated (prints only); the existence probe is read-only and
# runs against the SAME live docker state on both sides, so both take the same
# already-exists / would-create branch. (initialize_database / initialize_minio
# are not ported — they mutate un-gated.)
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root

# bash side: source config+log+docker+infra (IFS=$'\n\t' mirrors setup.sh so the
# dry-run `run` args newline-join). log.sh's EXIT trap noise is normalized away.
bsh() { SCRIPT_DIR="$PWD" DRY_RUN=1 bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  source scripts/lib/docker.sh >/dev/null 2>&1
  source scripts/lib/infra.sh  >/dev/null 2>&1
  '"$1"; }
pyi() { DRY_RUN=1 "$PY" -c "
from scripts.setup import config, docker, infra
config.DRY_RUN = True
$1"; }

norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
b="$(bsh "create_networks" | norm)"
p="$(pyi "infra.create_networks()" | norm)"
if [ "$b" = "$p" ]; then echo "PASS  create_networks (dry-run)"
else FAIL=1; echo "FAIL  create_networks"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

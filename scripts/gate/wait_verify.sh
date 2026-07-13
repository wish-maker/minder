#!/usr/bin/env bash
# Verify the ported wait/poll helpers (scripts/setup/docker.py) behave
# identically to scripts/lib/docker.sh against the LIVE stack. These use the
# spinner; spinner output is CR-overwritten transient animation, normalized away
# exactly like the gate does (`s/.*\r//`), so what's compared is the final
# success/error line + return code.
#
# Only the healthy / open-port branches are checked. The wait_healthy TIMEOUT
# branch is skipped: for a MISSING container bash's container_health leaks docker's
# stray blank line ("\nn/a") into the message while the Python helper returns a
# clean "n/a" (a known, documented quirk — see docker_verify.sh). No real service
# is unhealthy on a live stack to exercise that branch cleanly.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root

bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  source scripts/lib/docker.sh >/dev/null 2>&1
  '"$1"; }
pyi() { "$PY" -c "
import sys
from scripts.setup import config, docker
$1"; }

# Normalize like the gate: strip up to the last CR (spinner frames + \r\033[K),
# then ANSI, then the timestamp; drop the _cleanup epilogue + blank lines.
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

FAIL=0
cmpout() {  # $1=name  $2=bash-cmd  $3=py-cmd  — compare normalized stdout + exit
  local b bx p px
  b="$(bsh "$2" 2>&1)"; bx=$?
  p="$(pyi "$3" 2>&1)"; px=$?
  local bn pn; bn="$(printf '%s' "$b" | norm)"; pn="$(printf '%s' "$p" | norm)"
  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  $1 (exit $bx)"; else echo "FAIL  $1"; FAIL=1; fi
}

cmpout "wait_healthy postgres" \
  'wait_healthy postgres 90' \
  'sys.exit(0 if docker.wait_healthy("postgres", 90) else 1)'
cmpout "wait_postgres_ready" \
  'wait_postgres_ready 60' \
  'sys.exit(0 if docker.wait_postgres_ready(60) else 1)'
cmpout "wait_port open (8000)" \
  'wait_port 127.0.0.1 8000 30 && echo OK || echo NO' \
  'print("OK" if docker.wait_port("127.0.0.1", 8000, 30) else "NO")'
cmpout "wait_port closed (59999)" \
  'wait_port 127.0.0.1 59999 2 && echo OK || echo NO' \
  'print("OK" if docker.wait_port("127.0.0.1", 59999, 2) else "NO")'

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

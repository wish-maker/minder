#!/usr/bin/env bash
# Verify the ported run_health_checks (scripts/setup/health.py) behaves
# identically to scripts/lib/health.sh against the LIVE stack — STRUCTURALLY.
# Endpoint up/down, the server IP, URLs and counts are live/non-deterministic (and
# bash uses curl while the port uses urllib), so those values are masked exactly
# like the gate's normalize.sed; what's compared is the service SET + order +
# group headers + summary presence, in both human and --json modes.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root

bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  source scripts/lib/docker.sh >/dev/null 2>&1
  source scripts/lib/health.sh >/dev/null 2>&1
  '"$1"; }
pyi() { "$PY" -c "
from scripts.setup import health
$1"; }

# Human mode: mask value-varying tokens (URLs, health parentheticals), collapse
# the summary line, then reduce each endpoint line to "  MARK <name>" so the
# ok/warn/error ICON (live state, and curl-vs-urllib) doesn't matter — only the
# service SET/order/grouping. Mirrors normalize.sed's health rules.
hnorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                 -e '/Re-check: /d' \
                 -e '/endpoints healthy/  s/.*/  MARK HEALTHSUMMARY/' \
                 -e '/endpoints reachable/ s/.*/  MARK HEALTHSUMMARY/' \
                 -e 's#http://[^ ]+#HEALTHRESULT#g' \
                 -e 's/\(container not running\)/HEALTHRESULT/g' \
                 -e 's/\(TCP port check\)/HEALTHRESULT/g' \
                 -e 's/\(not yet reachable\)/HEALTHRESULT/g' \
                 -e 's/^  [^ ]+ ([^ ]+).*/  MARK \1/' \
                 -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
          | sed -e '/^[[:space:]]*$/d'; }
# JSON mode: mask timestamp / status / url / counts; keep name + order.
jnorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/"timestamp": "[^"]*"/"timestamp": "TS"/' \
                 -e 's/"status":"[^"]*"/"status":"S"/g' \
                 -e 's/"url":"[^"]*"/"url":"U"/g' \
                 -e 's/"ok": [0-9]+/"ok": N/' -e 's/"warn": [0-9]+/"warn": N/' \
                 -e '/Script exited unexpectedly/d' -e '/Full log:/d'; }

FAIL=0
cmp() {  # $1=name  $2=bash-out  $3=py-out  $4=normalizer
  local b p; b="$(printf '%s' "$2" | $4)"; p="$(printf '%s' "$3" | $4)"
  if [ "$b" = "$p" ]; then echo "PASS  $1"
  else FAIL=1; echo "FAIL  $1"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi
}

cmp "run_health_checks (human)" \
  "$(bsh 'run_health_checks' 2>&1)" \
  "$(pyi 'health.run_health_checks()' 2>&1)" hnorm
cmp "run_health_checks (--json)" \
  "$(bsh 'run_health_checks --json' 2>&1)" \
  "$(pyi 'health.run_health_checks(json_mode=True)' 2>&1)" jnorm

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

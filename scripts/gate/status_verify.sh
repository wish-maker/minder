#!/usr/bin/env bash
# Verify the ported `status` verb (scripts/setup/status.py) vs bash cmd_status,
# against the LIVE stack. --json delegates to run_health_checks (compared like
# health_verify). Human mode is compared STRUCTURALLY: the container counts,
# `docker ps` statuses/ports and `docker stats` CPU/mem/net are live/varying, so
# they're masked — each table row is reduced to its container name — and the
# health block is masked like the gate. What's verified: section + Summary label +
# the container-name SET in both tables + health structure.
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2

FAIL=0

# --- status --json (delegates to run_health_checks --json) ---
jnorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/"timestamp": "[^"]*"/"timestamp": "TS"/' \
                 -e 's/"status":"[^"]*"/"status":"S"/g' -e 's/"url":"[^"]*"/"url":"U"/g' \
                 -e 's/"ok": [0-9]+/"ok": N/' -e 's/"warn": [0-9]+/"warn": N/' \
                 -e '/Script exited unexpectedly/d' -e '/Full log:/d'; }
bj="$(env CI=true bash setup.bash.sh status --json 2>&1 | jnorm)"
pj="$(env CI=true "$PY" -m scripts.setup status --json 2>&1 | jnorm)"
if [ "$bj" = "$pj" ]; then echo "PASS  status --json"
else FAIL=1; echo "FAIL  status --json"; diff <(printf '%s\n' "$bj") <(printf '%s\n' "$pj") | sed 's/^/    /'; fi

# --- status (human, structural) ---
# Mask: counts (Summary line), each docker table row → its container name, and the
# health block (URLs/parentheticals/summary), plus ANSI/CR/timestamps.
snorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                 -e '/^Summary/,/^Containers/{/^Containers/!d;}' \
                 -e 's/^NAMES .*/NAMES/' -e 's/^NAME .*/NAME/' \
                 -e 's/^(minder-[A-Za-z0-9_-]+).*/\1/' \
                 -e '/Re-check: /d' \
                 -e '/endpoints healthy/  s/.*/  MARK HEALTHSUMMARY/' \
                 -e '/endpoints reachable/ s/.*/  MARK HEALTHSUMMARY/' \
                 -e 's#http://[^ ]+#HEALTHRESULT#g' \
                 -e 's/\(container not running\)/HEALTHRESULT/g' \
                 -e 's/\(TCP port check\)/HEALTHRESULT/g' \
                 -e 's/\(not yet reachable\)/HEALTHRESULT/g' \
                 -e 's/^  [^ ]+ ([^ ]+)  HEALTHRESULT.*/  MARK \1/' \
                 -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
          | sed -e '/^[[:space:]]*$/d'; }
bh="$(env CI=true bash setup.bash.sh status 2>&1 | snorm)"
ph="$(env CI=true "$PY" -m scripts.setup status 2>&1 | snorm)"
if [ "$bh" = "$ph" ]; then echo "PASS  status (human, structural)"
else FAIL=1; echo "FAIL  status (human)"; diff <(printf '%s\n' "$bh") <(printf '%s\n' "$ph") | sed 's/^/    /'; fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

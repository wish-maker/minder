#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup stop` behave identically to
# `bash setup.sh stop`?  Compares (normalized stdout, exit code) under DRY_RUN=1.
#
# SAFETY / NON-DESTRUCTIVE: run under DRY_RUN=1, so the mutating ops (compose
# down, network rm) are gated by run() and only PRINT — nothing is torn down. The
# `docker network ls` probe runs for real (both sides, identical state). The
# `--clean` image-prune path is NOT dry-run-gated, so it is deliberately NOT
# exercised here (plain `stop` only).
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

# Normalize: ANSI + CR; the HH:MM:SS timestamp; the compose-file absolute path,
# which differs by OS/interpreter BY DESIGN (bash builds a forward-slash Git-Bash
# path, Python's Path renders native separators) — collapse both to COMPOSE; and
# setup.sh's global `trap _cleanup EXIT` (log.sh) epilogue on non-zero exit.
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[^[:space:]]*docker-compose\.yml#COMPOSE#g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
bo="$(env DRY_RUN=1 SKIP_VERSION_CHECK=true CI=true NONINTERACTIVE=true bash setup.bash.sh stop 2>&1)"; bx=$?
po="$(env DRY_RUN=1 SKIP_VERSION_CHECK=true CI=true NONINTERACTIVE=true "$PY" -m scripts.setup stop 2>&1)"; px=$?

ok=1
[ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
[ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
if [ "$ok" = 1 ]; then echo "PASS  stop --dry-run (exit $bx)"; else echo "FAIL  stop --dry-run"; FAIL=1; fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

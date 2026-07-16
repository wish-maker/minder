#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup shell …` behave identically
# to `bash setup.bash.sh shell …`?  Compares the two non-interactive error branches
# (no service given under CI=true; container-not-running). The interactive
# `docker exec -it` happy path and the no-service prompt are exercised by hand,
# not here. Read-only. CI=true forces INTERACTIVE=false on both sides.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
run_case() {  # $1=name  rest=args
  local name="$1"; shift
  local bo bx; bo="$(env CI=true bash setup.bash.sh shell "$@" 2>&1)"; bx=$?
  local po px; po="$(env CI=true "$PY" -m scripts.setup shell "$@" 2>&1)"; px=$?
  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  local bn pn; bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  shell $name (exit $bx)"; else echo "FAIL  shell $name"; FAIL=1; fi
}

run_case "no service (non-interactive)"       # lists containers + "Specify a service" + exit 1
run_case "container not running"  zzz-nope    # "Container not running" + exit 1

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

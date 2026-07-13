#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup logs …` behave identically
# to `bash setup.sh logs …`?  Only the "unknown service" error branch is compared
# — the follow paths (`docker logs -f` / `compose logs -f`) stream and block, so
# they are exercised by hand, not here. Read-only.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

# Normalize: ANSI + CR; the HH:MM:SS timestamp; setup.sh's global `trap _cleanup
# EXIT` (log.sh) epilogue on non-zero exit.
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
run_case() {  # $@ = args to logs
  local name="$*"
  local bo bx; bo="$(env CI=true bash setup.sh logs "$@" 2>&1)"; bx=$?
  local po px; po="$(env CI=true "$PY" -m scripts.setup logs "$@" 2>&1)"; px=$?
  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  local bn pn; bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  logs $name (exit $bx)"; else echo "FAIL  logs $name"; FAIL=1; fi
}

run_case zzz-does-not-exist            # unknown service → error + running-list + exit 1

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

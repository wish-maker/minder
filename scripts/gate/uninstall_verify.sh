#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup uninstall [--purge]` behave
# identically to `bash setup.bash.sh uninstall [--purge]`?  Compares (normalized
# stdout, exit code) under DRY_RUN=1 + CI=true.
#
# SAFETY / NON-DESTRUCTIVE: run under DRY_RUN=1, so the compose calls (down /
# down -v --remove-orphans) are gated by run() and only PRINT — no services or
# volumes are removed. CI=true forces INTERACTIVE=false so the --purge DELETE
# prompt is skipped (that prompt is exercised by hand, not here).
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

# Normalize: ANSI + CR; the HH:MM:SS timestamp; the compose-file absolute path
# (OS/interpreter-specific by design — collapse to COMPOSE); setup.sh's global
# `trap _cleanup EXIT` (log.sh) epilogue on non-zero exit.
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[^[:space:]]*docker-compose\.yml#COMPOSE#g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
run_case() {  # $1=name  rest=args
  local name="$1"; shift
  local bo bx; bo="$(env DRY_RUN=1 CI=true SKIP_VERSION_CHECK=true NONINTERACTIVE=true bash setup.bash.sh uninstall "$@" 2>&1)"; bx=$?
  local po px; po="$(env DRY_RUN=1 CI=true SKIP_VERSION_CHECK=true NONINTERACTIVE=true "$PY" -m scripts.setup uninstall "$@" 2>&1)"; px=$?
  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  local bn pn; bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  uninstall $name (exit $bx)"; else echo "FAIL  uninstall $name"; FAIL=1; fi
}

run_case "plain (data preserved)"
run_case "--purge (non-interactive)"  --purge

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

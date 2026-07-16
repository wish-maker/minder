#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup migrate [target]` behave
# identically to `bash setup.bash.sh migrate [target]`?  Compares (normalized stdout,
# exit code) against the live stack.
#
# SAFETY / NON-MUTATING: the migration services ship no Alembic (they self-init
# their schema on startup), so every service takes the "skipping" branch and the
# `alembic upgrade` call is never reached — this verify never mutates any DB. If
# a stack DID carry Alembic, `alembic upgrade <target>` is idempotent at head;
# use a throwaway target only against a throwaway stack. Requires postgres + the
# 5 API services running; otherwise the compared paths are the not-running ones.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

# Normalize away everything that isn't the verb's own output: ANSI + CR; the
# HH:MM:SS timestamp; setup.sh's global `trap _cleanup EXIT` (log.sh) epilogue on
# non-zero exit ("Script exited unexpectedly" + "Full log:").
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
run_case() {  # $@ = args to migrate
  local name="$*"; [ -n "$name" ] || name="(default head)"
  local bo bx; bo="$(bash setup.bash.sh migrate "$@" 2>&1)"; bx=$?
  local po px; po="$("$PY" -m scripts.setup migrate "$@" 2>&1)"; px=$?

  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  local bn pn; bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  migrate $name (exit $bx)"; else echo "FAIL  migrate $name"; FAIL=1; fi
}

run_case                       # default target (head)
run_case head                  # explicit head
run_case verify-only-target    # arbitrary target — exercises the target plumbing

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

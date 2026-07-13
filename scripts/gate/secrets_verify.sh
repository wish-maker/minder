#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup sync-postgres-password`
# behave identically to `bash setup.sh sync-postgres-password`?  Compares
# (normalized stdout, exit code) across cases. Operates on the REAL repo .env, so
# it backs it up first and ALWAYS restores it. Not a permanent artifact.
#
# SAFETY: the success case runs against the REAL .env unchanged, so the live
# `ALTER USER` re-applies the password already in effect (a no-op) — it never
# writes a synthetic password to the running database. The error cases never
# reach postgres. The "container not running" branch is NOT exercised here (it
# would require stopping postgres); its logic is docker.container_running(),
# already verified by docker_verify.sh.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)
BAK="$(mktemp)"; HAD_ENV=0
[ -f .env ] && { cp .env "$BAK"; HAD_ENV=1; }
REAL_ENV=""; [ "$HAD_ENV" = 1 ] && REAL_ENV="$(cat .env)"
restore() { if [ "$HAD_ENV" = 1 ]; then cp "$BAK" .env; else rm -f .env; fi; rm -f "$BAK"; }
trap restore EXIT

# Normalize away everything that isn't the verb's own output:
#  - ANSI + CR; the HH:MM:SS timestamp; the abs .env path (OS-specific by design)
#  - setup.sh's GLOBAL `trap _cleanup EXIT` (log.sh) epilogue printed on any
#    non-zero exit ("Script exited unexpectedly" + "Full log:"); that belongs to
#    the log module, not sync_postgres_password.
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[A-Za-z]:[\\/][^ '"'"']*\.env#ENVPATH#g' -e 's#/[^ '"'"']*/\.env#ENVPATH#g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
run_case() {  # $1=name  $2=init-file-content-or-__NOENV__
  local name="$1" init="$2"
  if [ "$init" = "__NOENV__" ]; then rm -f .env; else printf '%s' "$init" > .env; fi
  local bo bx; bo="$(bash setup.sh sync-postgres-password 2>&1)"; bx=$?
  if [ "$init" = "__NOENV__" ]; then rm -f .env; else printf '%s' "$init" > .env; fi
  local po px; po="$("$PY" -m scripts.setup sync-postgres-password 2>&1)"; px=$?

  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  local bn pn; bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  $name (exit $bx)"; else echo "FAIL  $name"; FAIL=1; fi
}

EMPTY_PW=$'FOO=bar\nPOSTGRES_PASSWORD=\nBAZ=qux\n'

run_case "no .env file"          "__NOENV__"
run_case "POSTGRES_PASSWORD unset" "$EMPTY_PW"
# Success/live path: real .env unchanged → ALTER USER re-applies current password.
if [ "$HAD_ENV" = 1 ]; then
  run_case "sync (live, real .env)" "$REAL_ENV"
else
  echo "SKIP  sync (live) — no repo .env present"
fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

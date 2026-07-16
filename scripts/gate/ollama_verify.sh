#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup ollama-mode ...` behave
# identically to `bash setup.bash.sh ollama-mode ...`?  Compares (normalized stdout,
# exit code, resulting .env) across cases. Operates on the REAL repo .env, so it
# backs it up first and ALWAYS restores it. Not a permanent artifact.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)
BAK="$(mktemp)"; HAD_ENV=0
[ -f .env ] && { cp .env "$BAK"; HAD_ENV=1; }
restore() { if [ "$HAD_ENV" = 1 ]; then cp "$BAK" .env; else rm -f .env; fi; rm -f "$BAK"; }
trap restore EXIT

# Normalize away everything that isn't the ollama-mode verb's own output:
#  - ANSI + CR; the HH:MM:SS timestamp; the abs .env path (OS-specific by design)
#  - setup.sh's GLOBAL `trap _cleanup EXIT` (log.sh) epilogue printed on any
#    non-zero exit ("Script exited unexpectedly" + "Full log:" + its blank line);
#    that belongs to the log module, not cmd_ollama_mode.
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[A-Za-z]:[\\/][^ '"'"']*\.env#ENVPATH#g' -e 's#/[^ '"'"']*/\.env#ENVPATH#g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
run_case() {  # $1=name  $2=init-file-content  rest=args
  local name="$1" init="$2"; shift 2
  printf '%s' "$init" > .env
  local bo bx; bo="$(bash setup.bash.sh ollama-mode "$@" 2>&1)"; bx=$?
  local benv; benv="$(cat .env)"
  printf '%s' "$init" > .env
  local po px; po="$("$PY" -m scripts.setup ollama-mode "$@" 2>&1)"; px=$?
  local penv; penv="$(cat .env)"

  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  [ "$benv" = "$penv" ] || { ok=0; echo "  .env DIFFERS:"; diff <(printf '%s' "$benv") <(printf '%s' "$penv") | sed 's/^/    /'; }
  local bn pn; bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  $name (exit $bx)"; else echo "FAIL  $name"; FAIL=1; fi
}

WITH=$'FOO=bar\nOLLAMA_BASE_URL=http://old:11434\nBAZ=qux\n'
WITHOUT=$'FOO=bar\nBAZ=qux\n'
INTERNAL=$'FOO=bar\nOLLAMA_BASE_URL=\nBAZ=qux\n'

run_case "external valid url"      "$WITH"     external "http://192.168.1.50:11434"
run_case "external default url"    "$WITH"     external
run_case "external invalid url"    "$WITH"     external "not a url"
run_case "internal from external"  "$WITH"     internal
run_case "internal already intern" "$INTERNAL" internal
run_case "bad mode"                "$WITH"     bogus
run_case "no ollama line (append)" "$WITHOUT"  external "http://h:1"
run_case "no args (usage)"         "$WITH"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

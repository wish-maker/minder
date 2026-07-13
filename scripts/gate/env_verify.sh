#!/usr/bin/env bash
# One-shot verification: does python `env.get(KEY)` behave identically to bash
# env.sh `_env_get KEY`?  Operates on the REAL repo .env (both helpers read
# $ENV_FILE / config.ENV_FILE), so it backs it up first and ALWAYS restores it.
# Read-only w.r.t. the stack. Not a permanent artifact.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)
BAK="$(mktemp)"; HAD_ENV=0
[ -f .env ] && { cp .env "$BAK"; HAD_ENV=1; }
restore() { if [ "$HAD_ENV" = 1 ]; then cp "$BAK" .env; else rm -f .env; fi; rm -f "$BAK"; }
trap restore EXIT

# bash side: source config + env (IFS=$'\n\t' mirrors setup.sh:24), call _env_get.
bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"
  IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/env.sh
  _env_get "'"$1"'"'; }
# python side: import env and print env.get(KEY).
pyi() { "$PY" -c "from scripts.setup import env; print(env.get('$1'), end='')"; }

FAIL=0
run_case() {  # $1=name  $2=.env-content  $3=key
  printf '%s' "$2" > .env
  local b p; b="$(bsh "$3")"; p="$(pyi "$3")"
  # Strip CR: Python's text-mode stdout on Windows translates \n->\r\n when the
  # verify prints the value; env.get itself returns clean \n (real verbs emit via
  # log._emit, which writes raw bytes). Same \r normalization the other verifies do.
  b="${b//$'\r'/}"; p="${p//$'\r'/}"
  if [ "$b" = "$p" ]; then printf 'PASS  %-24s = %q\n' "$1" "$b"
  else FAIL=1; printf 'FAIL  %s\n  bash  : %q\n  python: %q\n' "$1" "$b" "$p"; fi
}

run_case "present single"   $'FOO=bar\nKEY=hello\nBAZ=qux\n'   KEY
run_case "absent"           $'FOO=bar\nBAZ=qux\n'              KEY
run_case "empty value"      $'FOO=bar\nKEY=\nBAZ=qux\n'        KEY
run_case "value with ="     $'KEY=a=b=c\n'                     KEY
run_case "value with space" $'KEY=hello world\n'              KEY
run_case "duplicate key"    $'KEY=one\nKEY=two\n'              KEY

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

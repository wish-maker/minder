#!/usr/bin/env bash
# One-shot verification: does python `env.get(KEY)` behave identically to bash
# env.sh `_env_get KEY`?  Operates on the REAL repo .env (both helpers read
# $ENV_FILE / config.ENV_FILE), so it backs it up first and ALWAYS restores it.
# Read-only w.r.t. the stack. Not a permanent artifact.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)
CENV="docker/compose/.env"
BAK="$(mktemp)"; HAD_ENV=0; CBAK="$(mktemp)"; HAD_CENV=0
[ -f .env ] && { cp .env "$BAK"; HAD_ENV=1; }
[ -f "$CENV" ] && { cp "$CENV" "$CBAK"; HAD_CENV=1; }
restore() {
  if [ "$HAD_ENV" = 1 ]; then cp "$BAK" .env; else rm -f .env; fi
  if [ "$HAD_CENV" = 1 ]; then cp "$CBAK" "$CENV"; else rm -f "$CENV"; fi
  rm -f "$BAK" "$CBAK"
}
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
# arbitrary-snippet variants (for gen_secret / sync_compose_env).
bshx() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"
  IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/env.sh
  '"$1"; }
pyix() { "$PY" -c "
from scripts.setup import env
$1"; }

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

# --- gen_secret: values are random, so compare FORMAT (length + hex charset) ---
gs_b() { bshx "s=\$(gen_secret $1); printf '%s %s' \"\${#s}\" \"\$(printf '%s' \"\$s\" | grep -qE '^[0-9a-f]+\$' && echo hex || echo nonhex)\""; }
gs_p() { pyix "s=env.gen_secret($1); print(f\"{len(s)} {'hex' if all(c in '0123456789abcdef' for c in s) else 'nonhex'}\", end='')"; }
for n in 16 32 40 64; do
  b="$(gs_b "$n")"; p="$(gs_p "$n")"; p="${p//$'\r'/}"
  if [ "$b" = "$p" ]; then printf 'PASS  %-24s = %q\n' "gen_secret $n" "$b"
  else FAIL=1; printf 'FAIL  %s\n  bash  : %q\n  python: %q\n' "gen_secret $n" "$b" "$p"; fi
done

# --- sync_compose_env: deterministic → byte-compare the written COMPOSE_ENV_FILE ---
sce_case() {  # $1=name  $2=.env-content
  printf '%s' "$2" > .env
  rm -f "$CENV"; bshx "_sync_compose_env"; local b; b="$(cat "$CENV" 2>/dev/null)"
  rm -f "$CENV"; pyix "env.sync_compose_env()";  local p; p="$(cat "$CENV" 2>/dev/null)"
  if [ "$b" = "$p" ]; then echo "PASS  sync_compose_env $1"
  else FAIL=1; echo "FAIL  sync_compose_env $1"; diff <(printf '%s' "$b") <(printf '%s' "$p") | sed 's/^/    /'; fi
}
sce_case "typical"      $'FOO=bar\nOLLAMA_BASE_URL=\nJWT_SECRET=abc123\n'
sce_case "no trailing newline" 'FOO=bar'
sce_case "empty file"   ''

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

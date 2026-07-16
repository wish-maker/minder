#!/usr/bin/env bash
# One-shot verification: does python `env.get(KEY)` behave identically to bash
# env.sh `_env_get KEY`?  Operates on the REAL repo .env (both helpers read
# $ENV_FILE / config.ENV_FILE), so it backs it up first and ALWAYS restores it.
# Read-only w.r.t. the stack. Not a permanent artifact.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)
# The fill/prepare tests below exercise the fill LOGIC, not the #57 live-stack guard,
# so allow regeneration globally; the dedicated guard test re-enables it (empty var).
export MINDER_ALLOW_SECRET_REGEN=1
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
# log-aware bash variant (fill/prepare/write_default emit via log_*). log.sh's EXIT
# trap noise (spinner \r\033[K + epilogue) is normalized away by lnorm.
bshl() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"
  IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  source scripts/lib/docker.sh >/dev/null 2>&1
  source scripts/lib/env.sh
  '"$1"; }
# normalize log output: strip-to-last-CR (spinner), ANSI, timestamps, the random
# backup filename ts, the _cleanup epilogue, blank lines.
lnorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                 -e 's/\.env\.backup-[0-9]{8}-[0-9]{6}/.env.backup-TS/g' \
                 -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

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

# --- fill_env_secrets: SELECTION + log are deterministic (values are random) ---
# Compare the log output (which keys, sorted, + backup + count) with the backup ts
# normalized. Reset .env between the two runs (bash mutates it), clean backups.
fill_case() {  # $1=name  $2=.env-content
  printf '%s' "$2" > .env
  local b; b="$(bshl "_fill_env_secrets" 2>&1)"
  printf '%s' "$2" > .env
  local p; p="$(pyix "env.fill_env_secrets()" 2>&1)"
  rm -f .env.backup-*
  local bn pn; bn="$(printf '%s' "$b" | lnorm)"; pn="$(printf '%s' "$p" | lnorm)"
  if [ "$bn" = "$pn" ]; then echo "PASS  fill_env_secrets $1"
  else FAIL=1; echo "FAIL  fill_env_secrets $1"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; fi
}
# POSTGRES_PASSWORD valid → skipped; REDIS placeholder, NEO4J bare-prefix, JWT empty,
# rest missing → all filled. FOO is non-spec → untouched (+ not logged).
fill_case "mixed (10 of 11 filled)" $'POSTGRES_PASSWORD=aRealPassword0123456789abcdefXY\nREDIS_PASSWORD=CHANGEME_me\nNEO4J_AUTH=neo4j/\nJWT_SECRET=\nFOO=bar\n'
# All valid → SILENT no-op (gate-critical: must print nothing).
FULLENV=$'POSTGRES_PASSWORD=v0000000000000000000000000000001\nREDIS_PASSWORD=v0000000000000000000000000000002\nRABBITMQ_PASSWORD=v0000000000000000000000000000003\nMINIO_ROOT_PASSWORD=v0000000000000000000000000000004\nJWT_SECRET=v0000000000000000000000000000005\nNEO4J_AUTH=neo4j/realsecretvalue\nINFLUXDB_TOKEN=v0000000000000000000000000000007\nAUTHELIA_STORAGE_ENCRYPTION_KEY=v008\nAUTHELIA_JWT_SECRET=v009\nGRAFANA_PASSWORD=v010\nWEBUI_SECRET_KEY=v011\n'
fill_case "full (silent no-op)" "$FULLENV"

# --- #57 guard: refuse secret regen on a running stack (override CLEARED) ---
# Only meaningful when a stateful core is live; otherwise the guard can't fire → SKIP.
# .env has placeholders → both impls must log_error + exit 1 and leave .env UNMUTATED.
if SCRIPT_DIR="$PWD" bash -c 'source scripts/lib/config.sh >/dev/null 2>&1; source scripts/lib/docker.sh >/dev/null 2>&1; container_running postgres' 2>/dev/null; then
  GP=$'POSTGRES_PASSWORD=\nREDIS_PASSWORD=CHANGEME\nFOO=bar\n'
  GPEXP="$(printf '%s' "$GP")"   # $()-stripped form, so the "unmutated" compare is apples-to-apples
  printf '%s' "$GP" > .env
  gb="$(MINDER_ALLOW_SECRET_REGEN= bshl "_fill_env_secrets" 2>&1)"; gbx=$?; gbmut="$(cat .env)"
  printf '%s' "$GP" > .env
  gp="$(MINDER_ALLOW_SECRET_REGEN= pyix "env.fill_env_secrets()" 2>&1)"; gpx=$?; gpmut="$(cat .env)"
  rm -f .env.backup-*
  gbn="$(printf '%s' "$gb" | lnorm)"; gpn="$(printf '%s' "$gp" | lnorm)"
  ok=1
  { [ "$gbx" = 1 ] && [ "$gpx" = 1 ]; } || { ok=0; echo "  exit: bash=$gbx python=$gpx (want 1/1)"; }
  [ "$gbn" = "$gpn" ] || { ok=0; echo "  msg DIFFERS:"; diff <(printf '%s\n' "$gbn") <(printf '%s\n' "$gpn")|sed 's/^/    /'; }
  { [ "$gbmut" = "$GPEXP" ] && [ "$gpmut" = "$GPEXP" ]; } || { ok=0; echo "  .env was MUTATED by an abort (must stay untouched)"; }
  [ "$ok" = 1 ] && echo "PASS  #57 guard aborts on live stack (exit 1, .env untouched)" || { FAIL=1; echo "FAIL  #57 guard"; }
else
  echo "SKIP  #57 guard (no stateful core running to trigger it)"
fi

# --- prepare_env: silent no-op on a fully-populated .env (gate-critical) ---
printf '%s' "$FULLENV" > .env
b="$(bshl "prepare_env" 2>&1)"; printf '%s' "$FULLENV" > .env; p="$(pyix "env.prepare_env()" 2>&1)"
rm -f .env.backup-*
bn="$(printf '%s' "$b" | lnorm)"; pn="$(printf '%s' "$p" | lnorm)"
if [ "$bn" = "$pn" ] && [ -z "$bn" ]; then echo "PASS  prepare_env full (silent)"
else FAIL=1; echo "FAIL  prepare_env full (silent)"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; fi

# --- write_default_env: structure is fixed; date + hex secrets are random ---
# Mask the Generated date and every 16+ hex run, then byte-compare the .env.
dnorm() { sed -E -e 's/# Generated: .*/# Generated: DATE/' -e 's/[0-9a-f]{16,}/HEX/g'; }
rm -f .env; bshl "_write_default_env" >/dev/null 2>&1; b="$(dnorm < .env)"
rm -f .env; pyix "env.write_default_env()" >/dev/null 2>&1; p="$(dnorm < .env)"
if [ "$b" = "$p" ]; then echo "PASS  write_default_env (structure)"
else FAIL=1; echo "FAIL  write_default_env (structure)"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

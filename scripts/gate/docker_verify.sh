#!/usr/bin/env bash
# Verify the ported docker helpers (scripts/setup/docker.py) behave identically
# to scripts/lib/docker.sh. Runs LIVE against whatever docker state exists, so
# positive branches are exercised when the minder stack is up. Read-only: it only
# inspects containers, never creates/removes them.
set -u
cd "$(dirname "$0")/../.." || exit 2   # repo root

# bash side: source the two modules in a subshell (SCRIPT_DIR must be set first).
bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/docker.sh
  '"$1"; }
# python side: eval a snippet with config/docker imported.
pyi() { python -c "
import sys
from scripts.setup import config, docker
$1"; }

# normalize: ANSI, CR, the compose-file abs path (OS-specific by design), and
# blank lines. The blank line matters for container_health on a MISSING container:
# docker 29 prints a stray empty line to stdout before erroring on a --format
# inspect of a non-existent object; bash's helper doesn't capture stdout so that
# blank leaks into its output ("\nn/a"), while the Python helper captures stdout
# and returns the clean semantic value ("n/a"). Same meaning; real services return
# "healthy" identically with or without this. No compared output has a meaningful
# blank line, so dropping them is safe.
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's#-f [^ ]*docker-compose\.yml#-f COMPOSE#g' -e '/^[[:space:]]*$/d'; }

FAIL=0
cmp() {  # $1=name  $2=bash-output  $3=python-output
  local b p; b="$(printf '%s' "$2" | norm)"; p="$(printf '%s' "$3" | norm)"
  if [ "$b" = "$p" ]; then printf 'PASS  %-34s = %s\n' "$1" "$b"
  else FAIL=1; printf 'FAIL  %s\n  bash  : %s\n  python: %s\n' "$1" "$b" "$p"; fi
}

# --- container_name (pure) ---
for s in postgres api-gateway graph-rag weird_name; do
  cmp "container_name $s" "$(bsh "container_name $s")" "$(pyi "print(docker.container_name('$s'))")"
done

# --- container_running / _exists / _health (LIVE) ---
for s in postgres api-gateway does-not-exist; do
  cmp "running $s"  "$(bsh "container_running $s && echo true || echo false")" \
                    "$(pyi "print('true' if docker.container_running('$s') else 'false')")"
  cmp "exists $s"   "$(bsh "container_exists $s && echo true || echo false")" \
                    "$(pyi "print('true' if docker.container_exists('$s') else 'false')")"
  cmp "health $s"   "$(bsh "container_health $s")" \
                    "$(pyi "print(docker.container_health('$s'))")"
done

# --- run() dry-run wrapper ---
cmp "run (dry)" "$(bsh "DRY_RUN=1 run docker compose ps --services")" \
                "$(DRY_RUN=1 pyi "config.DRY_RUN=True; docker.run('docker','compose','ps','--services')")"
# --- run() real passthrough exit code (true/false) ---
cmp "run true (exit)"  "$(bsh "run true;  echo \$?")"  "$(pyi "print(docker.run('true'))")"
cmp "run false (exit)" "$(bsh "run false; echo \$?")"  "$(pyi "print(docker.run('false'))")"

# --- compose() / compose_monitoring() dry-run command construction ---
cmp "compose (dry)"     "$(bsh "DRY_RUN=1 compose ps")" \
                        "$(DRY_RUN=1 pyi "config.DRY_RUN=True; docker.compose('ps')")"
cmp "compose_mon (dry)" "$(bsh "DRY_RUN=1 compose_monitoring up -d")" \
                        "$(DRY_RUN=1 pyi "config.DRY_RUN=True; docker.compose_monitoring('up','-d')")"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

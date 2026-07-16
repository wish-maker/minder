#!/usr/bin/env bash
# One-shot verification: does the ported `restore` (scripts/setup/restore.py) behave
# identically to bash `cmd_restore` (scripts/lib/commands.sh)?  Two levels:
#
#  A. CLI early-exit cases (no spinner) — compared at the verb level under CI=true:
#       • no-arg, empty backups/      -> "No backups found in <dir>"        (exit 1)
#       • no-arg, one backup present  -> lists it + "No backup archive ..." (exit 1)
#       • a nonexistent archive path  -> "File not found: <path>"           (exit 1)
#
#  B. Full restore of a crafted archive under DRY_RUN=1 — compared at the FUNCTION
#     level with the spinner STUBBED on both sides (the backup_verify pattern): the
#     per-backend "Restoring …" spinners animate on the same line the `run` dry-run
#     echo lands on, so a verb-level CLI capture is non-deterministic. This case
#     exercises the #55 fix (DRY_RUN now gates the destructive steps → echo-only, so
#     it is SAFE to run against the live stack) and the #56 fix (Qdrant copies in AND
#     extracts the same /tmp/qdrant.tar.gz).
#
# SAFETY: case A only reads/lists; case B runs under DRY_RUN=1 so every mutating step
# (.env cp, psql, docker cp/exec) is echo-only — nothing is written to the platform
# or to the real .env. A pre-existing backups/ is stashed aside for case A and
# restored afterward (trap-guarded); the crafted archive lives in a temp dir.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

STASH=""; TMPD=".verify-restore-tmp"
cleanup() {
    rm -rf "$TMPD"
    rm -rf backups
    [[ -n "$STASH" && -d "$STASH" ]] && { mv "$STASH" backups; STASH=""; }
}
trap cleanup EXIT INT TERM
if [[ -e backups ]]; then STASH="$(mktemp -d)/backups"; mv backups "$STASH"; fi

FAIL=0

# ── A. CLI early-exit cases ─────────────────────────────────────────────────
# Normalize: spinner CR residue + ANSI; HH:MM:SS; backups dir path (/ and \)
# -> BACKUPDIR; the `du -sh` size on a listing line -> SIZE; setup.sh's global
# `trap _cleanup EXIT` epilogue on the exit-1 cases (the Python module emits the
# ported cleanup epilogue too, but both are stripped for a stable comparison).
anorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                 -e 's#[^ ]*[/\\]backups#BACKUPDIR#g' \
                 -e '/^  \[[0-9]+\]/ s/  [^ ]+$/  SIZE/' \
                 -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
                 -e '/^[[:space:]]*$/d'; }

acase() {  # $1 = name; rest = args to restore
  local name="$1"; shift
  local bo bx po px
  bo="$(env CI=true NONINTERACTIVE=true SKIP_VERSION_CHECK=true bash setup.bash.sh restore "$@" 2>&1)"; bx=$?
  po="$(env CI=true NONINTERACTIVE=true SKIP_VERSION_CHECK=true "$PY" -m scripts.setup restore "$@" 2>&1)"; px=$?
  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  local bn pn; bn="$(printf '%s' "$bo" | anorm)"; pn="$(printf '%s' "$po" | anorm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  restore $name (exit $bx)"; else echo "FAIL  restore $name"; FAIL=1; fi
}

rm -rf backups; mkdir -p backups
acase "no-arg, empty backups"
printf 'dummy-archive-content\n' > backups/minder-20200101-000000.tar.gz
acase "no-arg, one backup listed"
rm -rf backups; mkdir -p backups
acase "nonexistent archive" nonexistent-archive.tar.gz

# ── B. Full DRY_RUN restore (function level, spinner stubbed) ────────────────
rm -rf "$TMPD"; mkdir -p "$TMPD/minder-DRYRUNTEST"
printf 'ENVDUMMY\n'  > "$TMPD/minder-DRYRUNTEST/env.backup"
printf 'SELECT 1;\n' > "$TMPD/minder-DRYRUNTEST/postgres.sql"
printf 'QDUMMY\n'    > "$TMPD/minder-DRYRUNTEST/qdrant.tar.gz"
printf '{}\n'        > "$TMPD/minder-DRYRUNTEST/rabbitmq-definitions.json"
( cd "$TMPD" && tar czf minder-DRYRUNTEST.tar.gz minder-DRYRUNTEST )
ARCHIVE="$TMPD/minder-DRYRUNTEST.tar.gz"

bsh() { SCRIPT_DIR="$PWD" CI=true NONINTERACTIVE=true DRY_RUN=1 bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1
  source scripts/lib/config.sh   >/dev/null 2>&1
  SCRIPT_NAME=setup.sh   # defined in setup.sh (not config.sh) → set it for the
                         # final "restart services: ./setup.sh start" line
  source scripts/lib/log.sh      >/dev/null 2>&1
  source scripts/lib/docker.sh   >/dev/null 2>&1
  source scripts/lib/env.sh      >/dev/null 2>&1
  source scripts/lib/commands.sh >/dev/null 2>&1
  spinner_start(){ :;}; spinner_stop(){ :;}
  cmd_restore "'"$ARCHIVE"'"'; }

pyi() { DRY_RUN=1 "$PY" -c "
from scripts.setup import config, docker, env, log, restore
config.DRY_RUN = True
config.INTERACTIVE = False
log.spinner_start = lambda *a, **k: None
log.spinner_stop = lambda *a, **k: None
restore.run(r'$ARCHIVE')"; }

# Normalize: ANSI/CR; HH:MM:SS; the temp restore_dir source args (each on its own
# line in the newline-joined dry-run echo) -> TMPSRC/<basename>; the .env dest
# (OS path) -> ENVFILE. The container-side paths (minder-*:/tmp/...) are identical
# on both sides and preserved — that is what proves the #56 fix.
bnorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                 -e 's#^.*(env\.backup|postgres\.sql|qdrant\.tar\.gz|rabbitmq-definitions\.json)$#TMPSRC/\1#' \
                 -e 's#^.*[/\\]\.env$#ENVFILE#' \
                 -e '/^[[:space:]]*$/d'; }

b="$(bsh 2>&1 | bnorm)"
p="$(pyi 2>&1 | bnorm)"
if [ "$b" = "$p" ]; then
    echo "PASS  restore full-dry-run (DRY_RUN, live stack)"
else
    FAIL=1; echo "FAIL  restore full-dry-run"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'
fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

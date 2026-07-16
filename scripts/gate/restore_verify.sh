#!/usr/bin/env bash
# One-shot verification: does `python -m scripts.setup restore [archive]` behave
# identically to `bash setup.sh restore [archive]`?  Compares (normalized stdout,
# exit code) at the CLI/verb level under CI=true (INTERACTIVE=false).
#
# SCOPE — only the NON-DESTRUCTIVE early exits are driven here:
#   • no-arg, empty backups/      -> "No backups found in <dir>"           (exit 1)
#   • no-arg, one backup present  -> lists it + "No backup archive ..."    (exit 1)
#   • a nonexistent archive path  -> "File not found: <path>"              (exit 1)
# cmd_restore's actual restore steps are BARE (un-gated) `docker`/`cp` and OVERWRITE
# live data even under DRY_RUN (see restore.py) — so the real restore is exercised by
# hand against a throwaway stack, NOT here. These early exits never reach the extract
# spinner, so a plain CLI capture is deterministic (no spinner-interleave noise).
#
# SAFETY: only reads/lists backups/. A pre-existing backups/ is stashed aside so the
# empty/one-backup states are deterministic, and restored afterward (trap-guarded).
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

STASH=""
restore_backups() {
    rm -rf backups
    [[ -n "$STASH" && -d "$STASH" ]] && { mv "$STASH" backups; STASH=""; }
}
trap restore_backups EXIT INT TERM
if [[ -e backups ]]; then STASH="$(mktemp -d)/backups"; mv backups "$STASH"; fi

# Normalize: spinner CR residue + ANSI; HH:MM:SS; the backups dir path (/ and \)
# -> BACKUPDIR; the `du -sh` size on a listing line ("  [N]  <ts>  <size>") ->
# SIZE; setup.sh's global `trap _cleanup EXIT` epilogue on the exit-1 cases (the
# Python module has no such trap).
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[^ ]*[/\\]backups#BACKUPDIR#g' \
                -e '/^  \[[0-9]+\]/ s/  [^ ]+$/  SIZE/' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
                -e '/^[[:space:]]*$/d'; }

FAIL=0
run_case() {  # $1 = name; rest = args to restore
  local name="$1"; shift
  local bo bx po px
  bo="$(env CI=true NONINTERACTIVE=true SKIP_VERSION_CHECK=true bash setup.sh restore "$@" 2>&1)"; bx=$?
  po="$(env CI=true NONINTERACTIVE=true SKIP_VERSION_CHECK=true "$PY" -m scripts.setup restore "$@" 2>&1)"; px=$?
  local ok=1
  [ "$bx" = "$px" ] || { ok=0; echo "  exit: bash=$bx python=$px"; }
  local bn pn; bn="$(printf '%s' "$bo" | norm)"; pn="$(printf '%s' "$po" | norm)"
  [ "$bn" = "$pn" ] || { ok=0; echo "  stdout DIFFERS:"; diff <(printf '%s\n' "$bn") <(printf '%s\n' "$pn") | sed 's/^/    /'; }
  if [ "$ok" = 1 ]; then echo "PASS  restore $name (exit $bx)"; else echo "FAIL  restore $name"; FAIL=1; fi
}

rm -rf backups; mkdir -p backups
run_case "no-arg, empty backups"

printf 'dummy-archive-content\n' > backups/minder-20200101-000000.tar.gz
run_case "no-arg, one backup listed"

rm -rf backups; mkdir -p backups
run_case "nonexistent archive" nonexistent-archive.tar.gz

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

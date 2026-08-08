#!/bin/bash
# One-off + reusable reaper for orphaned PTY `pager` processes on the Pi.
#
# Found live 2026-08-08: processes named `pager` (git's own pager, spawned by
# `git diff`/`git log`/etc, almost certainly via openclaw's exec tool running
# through a PTY -- see the "openclaw CLI hangs without --no-pty" gotcha in
# memory) left orphaned (reparented to PID 1) when their owning session ended
# without a clean teardown. The pager spins trying to write to a dead PTY
# instead of exiting, burning real CPU indefinitely instead of just hanging
# idle. Found 32 such pairs on this box, the oldest 9+ days old, driving load
# average to 33 on a 4-core Raspberry Pi 4 -- degrading both OpenClaw and
# Minder, which share this host.
#
# Safety: only ever targets a process literally named "pager" whose PARENT
# is *also* orphaned (its own PPid is 1) and has been running 5+ minutes -- a
# live interactive pager's parent shell is never reparented to init, and 5
# minutes is comfortably longer than any legitimate orphan-before-reparent
# race.
#
# Usage: bash pi_reap_orphaned_pagers.sh          # reap for real
#        bash pi_reap_orphaned_pagers.sh --dry-run # report only, kill nothing
set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

killed=0
while read -r pid ppid etime_s; do
    [ -z "$pid" ] && continue
    if [ "$etime_s" -lt 300 ]; then
        continue
    fi
    parent_ppid=$(ps -o ppid= -p "$ppid" 2>/dev/null | tr -d ' ')
    if [ "$parent_ppid" = "1" ]; then
        if [ "$DRY_RUN" = "1" ]; then
            echo "[dry-run] would reap orphaned pager pid=$pid (parent pid=$ppid, age ${etime_s}s)"
        else
            echo "Reaping orphaned pager pid=$pid (parent pid=$ppid, age ${etime_s}s)"
            kill "$pid" "$ppid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" "$ppid" 2>/dev/null || true
        fi
        killed=$((killed + 1))
    fi
done < <(ps -eo pid=,ppid=,etimes=,comm= | awk '$4=="pager"{print $1, $2, $3}')

if [ "$killed" -gt 0 ]; then
    [ "$DRY_RUN" = "1" ] && echo "Would reap $killed orphaned pager process pair(s)" \
                         || echo "Reaped $killed orphaned pager process pair(s)"
else
    echo "No orphaned pager processes found"
fi

#!/usr/bin/env bash
# One-shot verification: does the ported `backup` (scripts/setup/backup.py) behave
# identically to bash `cmd_backup` (scripts/lib/commands.sh)?  Compares normalized
# stdout under DRY_RUN=1 against the LIVE stack, at the FUNCTION level with the
# spinner stubbed on both sides (the infra_verify.sh pattern) — a verb-level CLI
# capture is non-deterministic here because the async spinner frames interleave
# with the `run` dry-run echoes differently between the bash subshell and the
# Python daemon thread. Stubbing the spinner removes that cosmetic noise; what is
# compared is the section, the per-backend success/warn/skip lines, and the exact
# dry-run `docker` command echoes.
#
# SAFETY / determinism:
#  - cmd_backup is READ-ONLY w.r.t. the platform: it dumps/reads and writes only
#    into backups/ (+ ephemeral container /tmp). Under DRY_RUN the Neo4j/InfluxDB/
#    Qdrant/RabbitMQ steps are `run`-gated (echo only), but the PostgreSQL
#    `pg_dumpall` and the final `tar` are BARE (un-gated) in bash — they run for
#    real even under DRY_RUN — so this verify really dumps Postgres and really
#    writes an archive. That is faithful (the port must match), so we stash any
#    existing backups/ aside first, run against an EMPTY backups/ (so the keep-7
#    prune can never touch real archives), then delete the gate's archives and
#    restore the original backups/ (trap-guarded).
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

STASH=""
restore_backups() {
    rm -rf backups
    [[ -n "$STASH" && -d "$STASH" ]] && { mv "$STASH" backups; STASH=""; }
}
trap restore_backups EXIT INT TERM

# Stash a pre-existing backups/ aside so the run starts empty (deterministic +
# prune-safe), and is fully restored afterward.
if [[ -e backups ]]; then STASH="$(mktemp -d)/backups"; mv backups "$STASH"; fi

bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; DRY_RUN=1
  source scripts/lib/config.sh   >/dev/null 2>&1
  source scripts/lib/log.sh      >/dev/null 2>&1
  source scripts/lib/docker.sh   >/dev/null 2>&1
  source scripts/lib/env.sh      >/dev/null 2>&1
  source scripts/lib/commands.sh >/dev/null 2>&1
  spinner_start() { :; }; spinner_stop() { :; }
  cmd_backup'; }

pyi() { DRY_RUN=1 "$PY" -c "
from scripts.setup import config, backup, log
config.DRY_RUN = True
log.spinner_start = lambda *a, **k: None
log.spinner_stop = lambda *a, **k: None
backup.run()"; }

# Normalize away run-to-run noise, PRESERVE structure:
#  spinner CR residue + ANSI; HH:MM:SS; the timestamped backups/minder-<ts> path
#  (both / and \ separators) -> BACKUP; bash's `du: cannot access` stderr for the
#  Qdrant file that docker-cp never created under DRY_RUN (Python skips it
#  silently, both then print an empty "()"); the `du -sh` size annotation (block
#  rounding is host/impl-specific) -> (SIZE).
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[^ ]*backups[/\\]minder-[0-9-]+#BACKUP#g' \
                -e '/du:.*(No such file|cannot access)/d' \
                -e 's/\(([0-9][^)]*)\)/(SIZE)/g' \
                -e '/^[[:space:]]*$/d'; }

FAIL=0
b="$(bsh 2>&1 | norm)"; rm -rf backups
p="$(pyi 2>&1 | norm)"; rm -rf backups
if [ "$b" = "$p" ]; then
    echo "PASS  backup (DRY_RUN, live stack)"
else
    FAIL=1; echo "FAIL  backup"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'
fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

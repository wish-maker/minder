#!/usr/bin/env bash
# ============================================================================
# Minder — quick backup verification (#430)
# ============================================================================
# Verifies the LATEST database backups produced by backups/backup-databases.sh
# (postgres / redis / neo4j / snapshots) are actually usable — for each kind,
# the newest artifact must:
#   1. EXIST      (a file matching the expected pattern is present)
#   2. be RECENT  (< BACKUP_MAX_AGE_HOURS old — else the daily backup has stopped)
#   3. be NON-EMPTY (> BACKUP_MIN_BYTES — catches a truncated / failed dump)
#   4. be a VALID archive (gzip -t / tar -tzf integrity — catches corruption)
#
# This is the fast integrity pass (--quick), NOT a full restore test. It catches
# the failure modes that silently rot backups: the cron stopped producing them,
# a dump got truncated, or an archive is corrupt.
#
# Exit 0 = every latest backup present, recent, and valid.
# Exit 1 = at least one is missing / stale / empty / corrupt.
# Exit 2 = usage error.
#
# Wired from the Pi's crontab:
#   0 2 * * * /root/minder/scripts/backup-test.sh --quick >> /root/minder/logs/backup-test.log 2>&1
# Lives in git (unlike the host-local backups/backup-databases.sh) precisely so
# it can't silently vanish and turn the cron line into a no-op again — which is
# exactly the bug this closes (#430).
set -u

BACKUP_DIR="${MINDER_BACKUP_DIR:-/root/minder/backups}"
MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-26}" # daily backup → newest must be < ~26h
MIN_BYTES="${BACKUP_MIN_BYTES:-100}"        # a truncated/empty dump is smaller

case "${1:-}" in
  "" | --quick) ;; # bare invocation and --quick both run the quick pass
  -h | --help)
    echo "usage: $0 [--quick]   (verify the latest postgres/redis/neo4j/snapshot backups)"
    exit 0
    ;;
  *)
    echo "usage: $0 [--quick]"
    exit 2
    ;;
esac

now="$(date +%s)"
fail=0

verify_gzip() { gzip -t "$1" 2>/dev/null; }
# --force-local: never treat a path containing a colon (e.g. a Windows drive
# letter, or an odd backup path) as a remote host:path spec.
verify_targz() { tar --force-local -tzf "$1" >/dev/null 2>&1; }

check() {
  # $1 label · $2 dir · $3 glob · $4 integrity-verifier
  local label="$1" dir="$2" glob="$3" verify="$4" newest bytes mtime age_h
  # shellcheck disable=SC2086  # glob must expand
  newest="$(ls -1t $dir/$glob 2>/dev/null | head -1)"
  if [[ -z "$newest" ]]; then
    echo "[FAIL] $label: no backup matching $dir/$glob"
    fail=1
    return
  fi
  bytes="$(stat -c%s "$newest" 2>/dev/null || echo 0)"
  mtime="$(stat -c%Y "$newest" 2>/dev/null || echo 0)"
  age_h=$(((now - mtime) / 3600))
  if ((bytes < MIN_BYTES)); then
    echo "[FAIL] $label: newest ($newest) is only ${bytes}B (< ${MIN_BYTES}B)"
    fail=1
    return
  fi
  if ((age_h > MAX_AGE_HOURS)); then
    echo "[FAIL] $label: newest ($newest) is ${age_h}h old (> ${MAX_AGE_HOURS}h) — daily backup may have stopped"
    fail=1
    return
  fi
  if ! "$verify" "$newest"; then
    echo "[FAIL] $label: newest ($newest) failed integrity check ($verify)"
    fail=1
    return
  fi
  echo "[ OK ] $label: $(basename "$newest") (${bytes}B, ${age_h}h old)"
}

echo "=== backup-test --quick @ $(date -Is) (dir=$BACKUP_DIR) ==="
check "postgres" "$BACKUP_DIR/postgres" "minder_postgres_*.sql.gz" verify_gzip
check "redis" "$BACKUP_DIR/redis" "minder_redis_*.rdb.gz" verify_gzip
check "neo4j" "$BACKUP_DIR/neo4j" "neo4j_*.tar.gz" verify_targz
check "snapshot" "$BACKUP_DIR/snapshots" "minder_snapshot_*.tar.gz" verify_targz

if ((fail)); then
  echo "=== RESULT: FAIL — one or more backups are missing / stale / empty / corrupt ==="
  exit 1
fi
echo "=== RESULT: OK — all latest backups present, recent, and valid ==="

#!/bin/bash
# ============================================================================
# Minder Platform - Automated Database Backup Script
# Backs up PostgreSQL, Redis, and Neo4j databases with retention
# ============================================================================
#
# Wired from the Pi's crontab:
#   0 2 * * * /root/minder/backups/backup-databases.sh full >> /var/log/minder-backup.log 2>&1
# Lives in git (previously host-local-only, silently un-reviewable and prone to
# drift) for the same reason backup-test.sh does: it can't be edited on the
# host and forgotten. backup-test.sh runs 20 minutes later (not the same
# minute) specifically so it always checks a FINISHED backup, not one still
# mid-write.

set -eo pipefail
# `pipefail` matters here specifically: backup_postgres's `pg_dump | gzip`
# pipeline, without it, reports the exit code of `gzip` (the LAST command),
# not `pg_dump` -- so a failed pg_dump (bad creds, DB down) still produces an
# empty-but-valid gzip stream, `[ $? -eq 0 ]` sees gzip's success, and the
# "backup" is logged as complete before cleanup_old_backups() deletes the
# last 7 days of GOOD backups out from under it.

# Configuration
BACKUP_DIR="/root/minder/backups"
POSTGRES_BACKUP_DIR="$BACKUP_DIR/postgres"
REDIS_BACKUP_DIR="$BACKUP_DIR/redis"
NEO4J_BACKUP_DIR="$BACKUP_DIR/neo4j"
SNAPSHOT_DIR="$BACKUP_DIR/snapshots"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# PostgreSQL Backup
# ============================================================================

backup_postgres() {
    log_info "Starting PostgreSQL backup..."

    local backup_file="$POSTGRES_BACKUP_DIR/minder_postgres_$TIMESTAMP.sql.gz"

    # Create backup using pg_dump
    docker exec minder-postgres pg_dump -U minder -d minder | gzip > "$backup_file"

    if [ $? -eq 0 ]; then
        log_info "✓ PostgreSQL backup completed: $backup_file"

        # Get file size
        local size=$(du -h "$backup_file" | cut -f1)
        log_info "  Backup size: $size"
    else
        log_error "✗ PostgreSQL backup failed"
        return 1
    fi
}

# ============================================================================
# Redis Backup
# ============================================================================

backup_redis() {
    log_info "Starting Redis backup..."

    local backup_file="$REDIS_BACKUP_DIR/minder_redis_$TIMESTAMP.rdb"

    # Trigger Redis BGSAVE -- authenticated: this container requires a
    # password (confirmed live, 2026-08-19), and an unauthenticated BGSAVE
    # fails with "NOAUTH Authentication required" while the script pressed on
    # regardless (no exit-code check at all), silently copying whatever STALE
    # dump.rdb happened to already exist from Redis's own last periodic
    # auto-save instead of a fresh one. Read the password from the container's
    # own env rather than duplicating the secret into this script.
    local redis_password
    redis_password="$(docker exec minder-redis printenv REDIS_PASSWORD 2>/dev/null || echo "")"
    if [ -n "$redis_password" ]; then
        docker exec minder-redis redis-cli --no-auth-warning -a "$redis_password" BGSAVE
    else
        docker exec minder-redis redis-cli BGSAVE
    fi

    # Wait for BGSAVE to complete
    sleep 5

    # Copy RDB file from container
    docker cp minder-redis:/data/dump.rdb "$backup_file" 2>/dev/null || {
        log_warn "Redis RDB file not found (might be empty)"
        return 0
    }

    if [ -f "$backup_file" ]; then
        # Compress backup
        gzip "$backup_file"
        local compressed="${backup_file}.gz"
        log_info "✓ Redis backup completed: $compressed"

        local size=$(du -h "$compressed" | cut -f1)
        log_info "  Backup size: $size"
    fi
}

# ============================================================================
# Neo4j Backup
# ============================================================================

backup_neo4j() {
    log_info "Starting Neo4j backup..."

    local backup_dir="$NEO4J_BACKUP_DIR/neo4j_$TIMESTAMP"
    mkdir -p "$backup_dir"

    # For Neo4j Community Edition, we'll copy the data directory
    # First, flush the Neo4j data to ensure consistency
    docker exec minder-neo4j cypher-shell -u neo4j -p neo4test "CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Page cache')" >/dev/null 2>&1 || true

    # Copy the data directory from the container
    docker cp minder-neo4j:/data "$backup_dir/" 2>/dev/null || {
        log_warn "Neo4j data directory copy failed"
        return 0
    }

    # Compress the backup
    tar czf "$NEO4J_BACKUP_DIR/neo4j_$TIMESTAMP.tar.gz" -C "$NEO4J_BACKUP_DIR" "neo4j_$TIMESTAMP" 2>/dev/null
    rm -rf "$backup_dir"

    if [ -f "$NEO4J_BACKUP_DIR/neo4j_$TIMESTAMP.tar.gz" ]; then
        log_info "✓ Neo4j backup completed: $NEO4J_BACKUP_DIR/neo4j_$TIMESTAMP.tar.gz"

        local size=$(du -h "$NEO4J_BACKUP_DIR/neo4j_$TIMESTAMP.tar.gz" | cut -f1)
        log_info "  Backup size: $size"
    fi
}

# ============================================================================
# Snapshot Creation
# ============================================================================

create_snapshot() {
    log_info "Creating system snapshot..."

    local snapshot_file="$SNAPSHOT_DIR/minder_snapshot_$TIMESTAMP.tar.gz"

    # Backup critical volumes using correct volume names
    docker run --rm -v docker_postgres_data:/data/postgres \
                  -v docker_redis_data:/data/redis \
                  -v docker_neo4j_data:/data/neo4j \
                  -v "$BACKUP_DIR:/backup" \
                  alpine tar czf "/backup/snapshots/minder_snapshot_$TIMESTAMP.tar.gz" \
                  -C /data postgres redis neo4j 2>/dev/null || {
        log_warn "Snapshot creation failed (volumes might not exist)"
        return 0
    }

    if [ -f "$snapshot_file" ]; then
        log_info "✓ System snapshot created: $snapshot_file"

        local size=$(du -h "$snapshot_file" | cut -f1)
        log_info "  Snapshot size: $size"
    fi
}

# ============================================================================
# Cleanup Old Backups
# ============================================================================

cleanup_old_backups() {
    log_info "Cleaning up old backups (retention: $RETENTION_DAYS days)..."

    # Find and delete backups older than retention period
    find "$POSTGRES_BACKUP_DIR" -name "minder_postgres_*.sql.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    find "$REDIS_BACKUP_DIR" -name "minder_redis_*.rdb.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    find "$NEO4J_BACKUP_DIR" -name "neo4j_*.tar.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    find "$SNAPSHOT_DIR" -name "minder_snapshot_*.tar.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

    log_info "✓ Old backups cleaned up"
}

# ============================================================================
# Backup Statistics
# ============================================================================

show_backup_stats() {
    log_info "Backup Statistics:"

    echo ""
    echo "PostgreSQL Backups:"
    ls -lh "$POSTGRES_BACKUP_DIR" 2>/dev/null | tail -5 || echo "  No backups found"

    echo ""
    echo "Redis Backups:"
    ls -lh "$REDIS_BACKUP_DIR" 2>/dev/null | tail -5 || echo "  No backups found"

    echo ""
    echo "Neo4j Backups:"
    ls -lh "$NEO4J_BACKUP_DIR" 2>/dev/null | tail -5 || echo "  No backups found"

    echo ""
    echo "Snapshots:"
    ls -lh "$SNAPSHOT_DIR" 2>/dev/null | tail -5 || echo "  No snapshots found"

    # Calculate total size
    local total_size=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    echo ""
    echo "Total Backup Size: $total_size"
}

# ============================================================================
# Main Backup Function
# ============================================================================

main() {
    local backup_type=${1:-full}

    log_info "=== Minder Platform Database Backup ==="
    log_info "Timestamp: $TIMESTAMP"
    log_info "Backup Type: $backup_type"
    echo ""

    case "$backup_type" in
        postgres)
            backup_postgres
            ;;
        redis)
            backup_redis
            ;;
        neo4j)
            backup_neo4j
            ;;
        snapshot)
            create_snapshot
            ;;
        full)
            backup_postgres
            backup_redis
            backup_neo4j
            create_snapshot
            ;;
        stats)
            show_backup_stats
            ;;
        cleanup)
            cleanup_old_backups
            ;;
        *)
            echo "Usage: $0 [postgres|redis|neo4j|snapshot|full|stats|cleanup]"
            echo ""
            echo "Commands:"
            echo "  postgres   - Backup PostgreSQL database only"
            echo "  redis     - Backup Redis database only"
            echo "  neo4j     - Backup Neo4j graph database only"
            echo "  snapshot  - Create system snapshot"
            echo "  full      - Backup all databases (default)"
            echo "  stats     - Show backup statistics"
            echo "  cleanup   - Clean up old backups"
            exit 1
            ;;
    esac

    # Cleanup old backups after successful backup
    if [ "$backup_type" != "stats" ] && [ "$backup_type" != "cleanup" ]; then
        cleanup_old_backups
    fi

    echo ""
    log_info "=== Backup Complete ==="
    log_info "Next scheduled backup: $(date -d '+1 hour' '+%Y-%m-%d %H:%M:%S')"
}

# ============================================================================
# Script Entry Point
# ============================================================================

main "$@"

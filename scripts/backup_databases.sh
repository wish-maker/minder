#!/bin/bash
#
# Minder Database Backup Script
# Backs up all databases: PostgreSQL, InfluxDB, Qdrant, Redis
#

set -e

# Configuration
BACKUP_DIR="/var/backups/minder"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=7

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "=================================================="
echo "MINDER DATABASE BACKUP - $TIMESTAMP"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print status
print_status() {
    local status=$1
    local message=$2
    if [ "$status" = "SUCCESS" ]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [ "$status" = "FAILED" ]; then
        echo -e "${RED}✗${NC} $message"
    else
        echo -e "${YELLOW}⚠${NC} $message"
    fi
}

# Counters
SUCCESS_COUNT=0
FAILED_COUNT=0

# ============================================
# 1. PostgreSQL Backup
# ============================================
echo ""
echo "1. PostgreSQL Backup"
echo "----------------------------"

POSTGRES_BACKUP="$BACKUP_DIR/postgres_$TIMESTAMP.sql.gz"

if docker exec postgres pg_dumpall -U postgres | gzip > "$POSTGRES_BACKUP"; then
    SIZE=$(du -h "$POSTGRES_BACKUP" | cut -f1)
    print_status "SUCCESS" "PostgreSQL backup created: $POSTGRES_BACKUP ($SIZE)"
    ((SUCCESS_COUNT++))
else
    print_status "FAILED" "PostgreSQL backup failed"
    ((FAILED_COUNT++))
fi

# ============================================
# 2. InfluxDB Backup
# ============================================
echo ""
echo "2. InfluxDB Backup"
echo "----------------------------"

INFLUX_BACKUP_DIR="$BACKUP_DIR/influxdb_$TIMESTAMP"
mkdir -p "$INFLUX_BACKUP_DIR"

if docker exec influxdb influx backup "$INFLUX_BACKUP_DIR" -t minder-token -o minder; then
    SIZE=$(du -sh "$INFLUX_BACKUP_DIR" | cut -f1)
    print_status "SUCCESS" "InfluxDB backup created: $INFLUX_BACKUP_DIR ($SIZE)"
    ((SUCCESS_COUNT++))
else
    # Alternative: Use influx backup command
    if docker exec influxdb influx backup "$INFLUX_BACKUP_DIR" --org minder --token minder-token; then
        SIZE=$(du -sh "$INFLUX_BACKUP_DIR" | cut -f1)
        print_status "SUCCESS" "InfluxDB backup created: $INFLUX_BACKUP_DIR ($SIZE)"
        ((SUCCESS_COUNT++))
    else
        print_status "FAILED" "InfluxDB backup failed"
        ((FAILED_COUNT++))
        # Remove empty directory
        rm -rf "$INFLUX_BACKUP_DIR"
    fi
fi

# ============================================
# 3. Qdrant Backup
# ============================================
echo ""
echo "3. Qdrant Backup"
echo "----------------------------"

QDRANT_BACKUP="$BACKUP_DIR/qdrant_$TIMESTAMP.json"

if docker exec qdrant curl -s http://localhost:6333/collections | jq '.' > "$QDRANT_BACKUP"; then
    # Backup each collection
    QDRANT_COLLECTIONS=$(docker exec qdrant curl -s http://localhost:6333/collections | jq -r '.result.collections[].name' 2>/dev/null || echo "")

    if [ -n "$QDRANT_COLLECTIONS" ]; then
        mkdir -p "$BACKUP_DIR/qdrant_$TIMESTAMP"
        for collection in $QDRANT_COLLECTIONS; do
            docker exec qdrant curl -s "http://localhost:6333/collections/$collection" | jq '.' > "$BACKUP_DIR/qdrant_$TIMESTAMP/${collection}.json"
            echo "  - Backed up collection: $collection"
        done
        SIZE=$(du -sh "$BACKUP_DIR/qdrant_$TIMESTAMP" | cut -f1)
        print_status "SUCCESS" "Qdrant backup created: $BACKUP_DIR/qdrant_$TIMESTAMP ($SIZE)"
        ((SUCCESS_COUNT++))
    else
        print_status "WARNING" "No Qdrant collections found"
        # Still count as success (empty backup)
        ((SUCCESS_COUNT++))
    fi
else
    print_status "FAILED" "Qdrant backup failed"
    ((FAILED_COUNT++))
fi

# ============================================
# 4. Redis Backup
# ============================================
echo ""
echo "4. Redis Backup"
echo "----------------------------"

REDIS_BACKUP="$BACKUP_DIR/redis_$TIMESTAMP.rdb"

if docker exec redis redis-cli --rdb "$REDIS_BACKUP" 2>/dev/null; then
    # Alternative: Copy RDB file
    if docker exec redis bash -c "cp /var/lib/redis/dump.rdb /tmp/dump_$TIMESTAMP.rdb" && \
       docker cp redis:/tmp/dump_$TIMESTAMP.rdb "$BACKUP_DIR/redis_$TIMESTAMP.rdb"; then
        SIZE=$(du -h "$BACKUP_DIR/redis_$TIMESTAMP.rdb" | cut -f1)
        print_status "SUCCESS" "Redis backup created: $BACKUP_DIR/redis_$TIMESTAMP.rdb ($SIZE)"
        ((SUCCESS_COUNT++))
    else
        print_status "FAILED" "Redis backup failed"
        ((FAILED_COUNT++))
    fi
else
    # Try direct copy
    if docker exec redis bash -c "test -f /data/dump.rdb && cp /data/dump.rdb /tmp/dump_$TIMESTAMP.rdb" && \
       docker cp redis:/tmp/dump_$TIMESTAMP.rdb "$BACKUP_DIR/redis_$TIMESTAMP.rdb"; then
        SIZE=$(du -h "$BACKUP_DIR/redis_$TIMESTAMP.rdb" | cut -f1)
        print_status "SUCCESS" "Redis backup created: $BACKUP_DIR/redis_$TIMESTAMP.rdb ($SIZE)"
        ((SUCCESS_COUNT++))
    else
        print_status "FAILED" "Redis backup failed"
        ((FAILED_COUNT++))
    fi
fi

# ============================================
# 5. Cleanup Old Backups
# ============================================
echo ""
echo "5. Cleanup Old Backups (older than $RETENTION_DAYS days)"
echo "----------------------------"

REMOVED_COUNT=0
for backup in $(find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS 2>/dev/null); do
    rm -f "$backup"
    ((REMOVED_COUNT++))
done

if [ $REMOVED_COUNT -gt 0 ]; then
    print_status "SUCCESS" "Removed $REMOVED_COUNT old backup files"
else
    echo "  - No old backups to remove"
fi

# ============================================
# Summary
# ============================================
echo ""
echo "=================================================="
echo "BACKUP SUMMARY"
echo "=================================================="
echo "Successful: $SUCCESS_COUNT"
echo "Failed: $FAILED_COUNT"
echo "Backup directory: $BACKUP_DIR"
echo ""

if [ $FAILED_COUNT -eq 0 ]; then
    print_status "SUCCESS" "All backups completed successfully!"
    exit 0
else
    print_status "FAILED" "Some backups failed. Check logs above."
    exit 1
fi

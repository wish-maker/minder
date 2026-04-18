#!/bin/bash
#
# Minder Database Restore Script
# Restores databases from backup
#

set -e

# Configuration
BACKUP_DIR="/var/backups/minder"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

echo "=================================================="
echo "MINDER DATABASE RESTORE"
echo "=================================================="

# Check backup directory
if [ ! -d "$BACKUP_DIR" ]; then
    print_status "FAILED" "Backup directory not found: $BACKUP_DIR"
    exit 1
fi

# List available backups
echo ""
echo "Available backups:"
echo "----------------------------"

echo "PostgreSQL:"
ls -lh "$BACKUP_DIR"/postgres_*.sql.gz 2>/dev/null || echo "  No PostgreSQL backups found"

echo ""
echo "InfluxDB:"
ls -ld "$BACKUP_DIR"/influxdb_* 2>/dev/null || echo "  No InfluxDB backups found"

echo ""
echo "Qdrant:"
ls -ld "$BACKUP_DIR"/qdrant_* 2>/dev/null || echo "  No Qdrant backups found"

echo ""
echo "Redis:"
ls -lh "$BACKUP_DIR"/redis_*.rdb 2>/dev/null || echo "  No Redis backups found"

# Ask which backup to restore
echo ""
echo "Enter backup timestamp to restore (format: YYYYMMDD_HHMMSS)"
read -p "Or press Ctrl+C to cancel: " TIMESTAMP

if [ -z "$TIMESTAMP" ]; then
    print_status "FAILED" "No timestamp provided"
    exit 1
fi

# ============================================
# Restore Functions
# ============================================

restore_postgres() {
    local backup="$BACKUP_DIR/postgres_$TIMESTAMP.sql.gz"

    if [ ! -f "$backup" ]; then
        print_status "FAILED" "PostgreSQL backup not found: $backup"
        return 1
    fi

    echo ""
    echo "Restoring PostgreSQL..."
    echo "----------------------------"

    if gunzip < "$backup" | docker exec -i postgres psql -U postgres; then
        print_status "SUCCESS" "PostgreSQL restored from $backup"
        return 0
    else
        print_status "FAILED" "PostgreSQL restore failed"
        return 1
    fi
}

restore_influxdb() {
    local backup_dir="$BACKUP_DIR/influxdb_$TIMESTAMP"

    if [ ! -d "$backup_dir" ]; then
        print_status "FAILED" "InfluxDB backup not found: $backup_dir"
        return 1
    fi

    echo ""
    echo "Restoring InfluxDB..."
    echo "----------------------------"

    if docker exec influxdb influx restore "$backup_dir" -t minder-token -o minder; then
        print_status "SUCCESS" "InfluxDB restored from $backup_dir"
        return 0
    else
        print_status "FAILED" "InfluxDB restore failed"
        return 1
    fi
}

restore_qdrant() {
    local backup_dir="$BACKUP_DIR/qdrant_$TIMESTAMP"

    if [ ! -d "$backup_dir" ]; then
        print_status "FAILED" "Qdrant backup not found: $backup_dir"
        return 1
    fi

    echo ""
    echo "Restoring Qdrant..."
    echo "----------------------------"

    # This is a simplified restore - full restore would require recreating collections
    print_status "WARNING" "Qdrant restore requires manual intervention"
    echo "  Backup files are in: $backup_dir"
    echo "  Each .json file contains collection configuration and data"
    return 0
}

restore_redis() {
    local backup="$BACKUP_DIR/redis_$TIMESTAMP.rdb"

    if [ ! -f "$backup" ]; then
        print_status "FAILED" "Redis backup not found: $backup"
        return 1
    fi

    echo ""
    echo "Restoring Redis..."
    echo "----------------------------"

    # Stop Redis, copy RDB file, start Redis
    docker-compose stop redis
    docker cp "$backup" redis:/data/dump.rdb
    docker-compose start redis

    print_status "SUCCESS" "Redis restored from $backup"
    return 0
}

# ============================================
# Interactive Restore
# ============================================

echo ""
echo "Which databases do you want to restore?"
echo "1) PostgreSQL only"
echo "2) InfluxDB only"
echo "3) Qdrant only"
echo "4) Redis only"
echo "5) All databases"
read -p "Enter choice (1-5): " CHOICE

case $CHOICE in
    1) restore_postgres ;;
    2) restore_influxdb ;;
    3) restore_qdrant ;;
    4) restore_redis ;;
    5)
        restore_postgres
        restore_influxdb
        restore_qdrant
        restore_redis
        ;;
    *)
        print_status "FAILED" "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "=================================================="
print_status "SUCCESS" "Restore operation completed"
echo "=================================================="

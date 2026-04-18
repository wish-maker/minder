#!/bin/bash
#
# Minder Database Cleanup Script
# Removes old data to free up space
#

set -e

# Configuration
BACKUP_DIR="/var/backups/minder"
RETENTION_DAYS=7
LOG_RETENTION_DAYS=30

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
echo "MINDER DATABASE CLEANUP"
echo "=================================================="
echo ""
echo "Retention policy:"
echo "  - Backups: $RETENTION_DAYS days"
echo "  - Logs: $LOG_RETENTION_DAYS days"
echo "----------------------------"

REMOVED_BACKUPS=0
REMOVED_LOGS=0

# ============================================
# 1. Clean Old Backups
# ============================================
echo ""
echo "1. Cleaning old backups..."
echo "----------------------------"

if [ -d "$BACKUP_DIR" ]; then
    REMOVED_BACKUPS=$(find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS 2>/dev/null | wc -l)

    if [ $REMOVED_BACKUPS -gt 0 ]; then
        find "$BACKUP_DIR" -type f -mtime +$RETENTION_DAYS -delete
        print_status "SUCCESS" "Removed $REMOVED_BACKUPS old backup files"
    else
        echo "  - No old backups to remove"
    fi

    # Clean empty directories
    find "$BACKUP_DIR" -type d -empty -delete 2>/dev/null || true
else
    print_status "WARNING" "Backup directory not found: $BACKUP_DIR"
fi

# ============================================
# 2. Clean Old Logs
# ============================================
echo ""
echo "2. Cleaning old logs..."
echo "----------------------------"

LOG_DIR="/var/log/minder"

if [ -d "$LOG_DIR" ]; then
    REMOVED_LOGS=$(find "$LOG_DIR" -type f -name "*.log" -mtime +$LOG_RETENTION_DAYS 2>/dev/null | wc -l)

    if [ $REMOVED_LOGS -gt 0 ]; then
        find "$LOG_DIR" -type f -name "*.log" -mtime +$LOG_RETENTION_DAYS -delete
        print_status "SUCCESS" "Removed $REMOVED_LOGS old log files"
    else
        echo "  - No old logs to remove"
    fi
else
    print_status "WARNING" "Log directory not found: $LOG_DIR"
fi

# ============================================
# 3. Clean Docker Logs
# ============================================
echo ""
echo "3. Cleaning Docker container logs..."
echo "----------------------------"

# Get all Minder containers
CONTAINERS=$(docker ps -q --filter "name=minder" 2>/dev/null || echo "")

if [ -n "$CONTAINERS" ]; then
    for container in $CONTAINERS; do
        CONTAINER_NAME=$(docker inspect --format='{{.Name}}' "$container" | sed 's/\///')
        echo "  - Trimming logs for: $CONTAINER_NAME"

        # Limit log size to 10MB
        docker inspect --format='{{.LogPath}}' "$container" 2>/dev/null | while read log_file; do
            if [ -f "$log_file" ]; then
                # Truncate log file to last 10MB
                tail -c 10M "$log_file" > "${log_file}.tmp" 2>/dev/null || true
                mv "${log_file}.tmp" "$log_file" 2>/dev/null || true
            fi
        done
    done

    print_status "SUCCESS" "Docker logs trimmed"
else
    echo "  - No Minder containers found"
fi

# ============================================
# 4. Clean Temp Files
# ============================================
echo ""
echo "4. Cleaning temporary files..."
echo "----------------------------"

TEMP_DIRS="/tmp /var/tmp"

REMOVED_TEMP=0
for temp_dir in $TEMP_DIRS; do
    if [ -d "$temp_dir" ]; then
        # Remove temp files older than 1 day
        COUNT=$(find "$temp_dir" -type f -name "minder_*" -mtime +1 2>/dev/null | wc -l)
        if [ $COUNT -gt 0 ]; then
            find "$temp_dir" -type f -name "minder_*" -mtime +1 -delete
            ((REMOVED_TEMP += COUNT))
        fi
    fi
done

if [ $REMOVED_TEMP -gt 0 ]; then
    print_status "SUCCESS" "Removed $REMOVED_TEMP temporary files"
else
    echo "  - No temporary files to remove"
fi

# ============================================
# 5. Disk Space Summary
# ============================================
echo ""
echo "5. Disk space usage:"
echo "----------------------------"

df -h | grep -E "(Filesystem|/$|/var)" | head -5

# ============================================
# Summary
# ============================================
echo ""
echo "=================================================="
echo "CLEANUP SUMMARY"
echo "=================================================="
echo "Backups removed: $REMOVED_BACKUPS"
echo "Logs removed: $REMOVED_LOGS"
echo "Temp files removed: $REMOVED_TEMP"
echo ""

if [ $REMOVED_BACKUPS -eq 0 ] && [ $REMOVED_LOGS -eq 0 ] && [ $REMOVED_TEMP -eq 0 ]; then
    print_status "SUCCESS" "No files needed cleanup (system clean)"
else
    print_status "SUCCESS" "Cleanup completed successfully"
fi

echo ""
echo "Next scheduled cleanup: $(date -d '+1 day' +'%Y-%m-%d %H:%M:%S')"

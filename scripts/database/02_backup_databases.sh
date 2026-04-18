#!/bin/bash
###############################################################################
# Minder Database Backup Script
# Version: 1.0.0
# Description: Backs up all Minder databases with timestamp
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/minder}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS="${RETENTION_DAYS:-7}"  # Keep backups for 7 days

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}Error: POSTGRES_PASSWORD environment variable not set${NC}"
    exit 1
fi

echo -e "${GREEN}=== Minder Database Backup ===${NC}"
echo "Timestamp: $TIMESTAMP"
echo "Backup Dir: $BACKUP_DIR"
echo "Retention: $RETENTION_DAYS days"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Export PGPASSWORD
export PGPASSWORD="$POSTGRES_PASSWORD"

# Databases to backup
databases=(
    "fundmind"
    "minder_news"
    "minder_weather"
    "minder_crypto"
    "minder_network"
)

echo -e "${YELLOW}Backing up databases...${NC}"

for db in "${databases[@]}"; do
    backup_file="$BACKUP_DIR/${db}_${TIMESTAMP}.sql.gz"

    echo -n "  Backing up '$db'... "

    # Dump and compress
    pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
            -d "$db" --clean --if-exists | gzip > "$backup_file"

    # Verify backup was created
    if [ -f "$backup_file" ] && [ -s "$backup_file" ]; then
        size=$(du -h "$backup_file" | cut -f1)
        echo -e "${GREEN}✓ $size${NC}"
    else
        echo -e "${RED}✗ failed${NC}"
        exit 1
    fi
done

echo ""

# Clean up old backups
echo -e "${YELLOW}Cleaning up old backups (older than $RETENTION_DAYS days)...${NC}"

find "$BACKUP_DIR" -name "*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete

old_count=$(find "$BACKUP_DIR" -name "*.sql.gz" -type f | wc -l)
echo -e "${GREEN}✓ Cleanup complete. $old_count backups retained.${NC}"

echo ""
echo -e "${GREEN}=== Backup Complete ===${NC}"
echo "Backup location: $BACKUP_DIR"
echo ""

# Unset PGPASSWORD
unset PGPASSWORD

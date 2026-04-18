#!/bin/bash
###############################################################################
# Minder Database Restore Script
# Version: 1.0.0
# Description: Restores databases from backup files
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

if [ -z "$POSTGRES_PASSWORD" ]; then
    echo -e "${RED}Error: POSTGRES_PASSWORD environment variable not set${NC}"
    exit 1
fi

# Check if backup file specified
if [ -z "$1" ]; then
    echo -e "${YELLOW}Usage: $0 <backup_file.sql.gz>${NC}"
    echo ""
    echo "Available backups in $BACKUP_DIR:"
    ls -lh "$BACKUP_DIR"/*.sql.gz 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"

# Check if backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Error: Backup file not found: $BACKUP_FILE${NC}"
    exit 1
fi

echo -e "${YELLOW}=== Minder Database Restore ===${NC}"
echo "Backup file: $BACKUP_FILE"
echo "Target host: $POSTGRES_HOST:$POSTGRES_PORT"
echo ""

# Confirm restore
read -p "$(echo -e ${RED}This will DELETE all existing data. Continue? (yes/no): ${NC})" confirm

if [ "$confirm" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""

# Export PGPASSWORD
export PGPASSWORD="$POSTGRES_PASSWORD"

# Extract database name from backup file
backup_filename=$(basename "$BACKUP_FILE")
db_name=$(echo "$backup_filename" | cut -d_ -f1)

echo -e "${YELLOW}Restoring database '$db_name'...${NC}"

# Decompress and restore
gunzip -c "$BACKUP_FILE" | psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$db_name"

echo ""
echo -e "${GREEN}=== Restore Complete ===${NC}"
echo "Database '$db_name' restored successfully!"
echo ""

# Unset PGPASSWORD
unset PGPASSWORD

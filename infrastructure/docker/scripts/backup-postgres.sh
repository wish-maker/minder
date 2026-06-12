#!/bin/bash
# PostgreSQL Backup Script for Minder Platform
# Usage: ./backup-postgres.sh

set -e  # Exit on error

BACKUP_DIR="/backup/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="minder-postgres"
LOG_FILE="/var/log/backup.log"

# Function to log messages
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to handle errors
error_exit() {
    log "ERROR: $1"
    exit 1
}

log "Starting PostgreSQL backup..."

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    error_exit "Container ${CONTAINER_NAME} is not running"
fi

# Create backup directory
mkdir -p "$BACKUP_DIR" || error_exit "Failed to create backup directory"

# Backup filename
BACKUP_FILE="$BACKUP_DIR/minder_${DATE}.sql"
COMPRESSED_FILE="${BACKUP_FILE}.gz"

# Perform PostgreSQL dump
log "Dumping PostgreSQL database..."
if docker exec "$CONTAINER_NAME" pg_dump -U minder -d minder > "$BACKUP_FILE" 2>> "$LOG_FILE"; then
    log "PostgreSQL dump completed successfully"
else
    error_exit "PostgreSQL dump failed"
fi

# Compress the backup
log "Compressing backup file..."
if gzip "$BACKUP_FILE"; then
    BACKUP_SIZE=$(du -h "$COMPRESSED_FILE" | cut -f1)
    log "Backup compressed: $COMPRESSED_FILE ($BACKUP_SIZE)"
else
    error_exit "Failed to compress backup file"
fi

# Remove backups older than 7 days
log "Cleaning up old backups (older than 7 days)..."
DELETED=$(find "$BACKUP_DIR" -name "minder_*.sql.gz" -mtime +7 -delete -print | wc -l)
log "Deleted $DELETED old backup(s)"

# Verify backup was created
if [ -f "$COMPRESSED_FILE" ]; then
    log "✅ PostgreSQL backup completed successfully: $COMPRESSED_FILE ($BACKUP_SIZE)"
else
    error_exit "Backup file was not created"
fi

# List current backups
log "Current backups in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR" | tail -10 | tee -a "$LOG_FILE"

exit 0

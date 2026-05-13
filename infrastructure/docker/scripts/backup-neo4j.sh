#!/bin/bash
# Neo4j Backup Script for Minder Platform
# Usage: ./backup-neo4j.sh

set -e  # Exit on error

BACKUP_DIR="/backup/neo4j"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="minder-neo4j"
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

log "Starting Neo4j backup..."

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    error_exit "Container ${CONTAINER_NAME} is not running"
fi

# Create backup directory
mkdir -p "$BACKUP_DIR" || error_exit "Failed to create backup directory"

# Use neo4j-admin to perform backup
log "Performing Neo4j backup using neo4j-admin..."

# Try alternative approach using tar (more reliable)
log "Creating backup using tar method..."

# Alternative: Direct file copy
docker exec "$CONTAINER_NAME" tar czf /tmp/neo4j_backup_${DATE}.tar.gz /data/ 2>&1 | tee -a "$LOG_FILE" || {
  error_exit "Tar backup method failed"
}

# Copy backup from container
docker cp "$CONTAINER_NAME:/tmp/neo4j_backup_${DATE}.tar.gz" "$BACKUP_DIR/" || error_exit "Failed to copy backup from container"

# Cleanup temp backup in container
docker exec "$CONTAINER_NAME" rm -f "/tmp/neo4j_backup_${DATE}.tar.gz"

BACKUP_FILE="$BACKUP_DIR/neo4j_backup_${DATE}.tar.gz"

# If we used neo4j-admin, find the backup directory
if [ ! -f "$BACKUP_FILE" ]; then
  BACKUP_FILE=$(find "$BACKUP_DIR" -name "minder_${DATE}*" -type d | head -1)
fi

# Calculate backup size
if [ -d "$BACKUP_FILE" ]; then
  BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
elif [ -f "$BACKUP_FILE" ]; then
  BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
else
  error_exit "Backup file/directory was not created"
fi

# Remove backups older than 7 days
log "Cleaning up old backups (older than 7 days)..."
DELETED=$(find "$BACKUP_DIR" -name "minder_*" -o -name "neo4j_backup_*" 2>/dev/null | while read backup; do
  if [ -f "$backup" ]; then
    find "$backup" -mtime +7 -delete -print 2>/dev/null
  elif [ -d "$backup" ]; then
    find "$backup" -type d -mtime +7 -exec rm -rf {} + 2>/dev/null && echo "$backup"
  fi
done | wc -l)
log "Deleted $DELETED old backup(s)"

log "✅ Neo4j backup completed successfully: $BACKUP_FILE ($BACKUP_SIZE)"

# List current backups
log "Current backups in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR" | tail -10 | tee -a "$LOG_FILE"

exit 0

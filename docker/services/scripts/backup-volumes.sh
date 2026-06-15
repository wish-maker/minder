#!/bin/bash
# Docker Volume Backup Script for Minder Platform
# Usage: ./backup-volumes.sh

set -e  # Exit on error

VOLUMES=(
  "minder_postgres_data"
  "minder_redis_data"
  "docker_neo4j_data"
  "docker_openwebui_data"
  "docker_qdrant_data"
  "docker_rabbitmq_data"
)

BACKUP_DIR="/backup/volumes"
DATE=$(date +%Y%m%d_%H%M%S)
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

log "Starting Docker volume backup..."

# Check if docker is available
if ! command -v docker &> /dev/null; then
    error_exit "Docker command not found"
fi

# Create backup directory
mkdir -p "$BACKUP_DIR" || error_exit "Failed to create backup directory"

# Backup each volume
SUCCESS_COUNT=0
FAILED_COUNT=0

for volume in "${VOLUMES[@]}"; do
  log "Processing volume: $volume"

  # Check if volume exists
  if ! docker volume inspect "$volume" &> /dev/null; then
    log "WARNING: Volume $volume does not exist, skipping..."
    continue
  fi

  # Create temporary container to access volume
  BACKUP_FILE="$BACKUP_DIR/${volume}_${DATE}.tar.gz"

  log "Creating backup for $volume..."

  if docker run --rm \
    -v "$volume:/data:ro" \
    -v "$BACKUP_DIR:/backup" \
    alpine tar czf "/backup/${volume}_${DATE}.tar.gz" -C /data . 2>&1 | tee -a "$LOG_FILE"; then

    # Calculate backup size
    if [ -f "$BACKUP_FILE" ]; then
      BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
      log "✅ Backup completed: ${volume}_${DATE}.tar.gz ($BACKUP_SIZE)"
      SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
      log "WARNING: Backup file was not created for $volume"
      FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
  else
    log "ERROR: Failed to backup volume $volume"
    FAILED_COUNT=$((FAILED_COUNT + 1))
  fi
done

# Remove backups older than 30 days
log "Cleaning up old volume backups (older than 30 days)..."
DELETED=$(find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete -print | wc -l)
log "Deleted $DELETED old backup(s)"

# Create backup manifest
cat > "$BACKUP_DIR/backup_manifest_${DATE}.txt" << EOF
Minder Platform Volume Backup
Date: $(date)
Hostname: $(hostname)
User: $(whoami)
Working Directory: $(pwd)
Docker Version: $(docker --version)

Volumes Backed: $SUCCESS_COUNT/${#VOLUMES[@]}
Volumes Failed: $FAILED_COUNT/${#VOLUMES[@]}

Backup Files:
$(ls -lh "$BACKUP_DIR"/*_${DATE}.tar.gz 2>/dev/null | awk '{print $9, $5}')

Total Backup Size: $(du -sh "$BACKUP_DIR" | cut -f1)

EOF

log "Backup manifest created: backup_manifest_${DATE}.txt"

# Summary
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "Volume Backup Summary:"
log "  Successful: $SUCCESS_COUNT/${#VOLUMES[@]}"
log "  Failed: $FAILED_COUNT/${#VOLUMES[@]}"
log "  Total Time: $SECONDS seconds"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAILED_COUNT -gt 0 ]; then
  log "⚠️  WARNING: Some backups failed. Check logs for details."
  exit 1
else
  log "✅ All volume backups completed successfully!"
fi

# List current backups
log "Current volume backups in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR" | tail -15 | tee -a "$LOG_FILE"

exit 0

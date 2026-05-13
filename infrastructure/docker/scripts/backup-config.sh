#!/bin/bash
# Config Backup Script for Minder Platform
# Usage: ./backup-config.sh

set -e  # Exit on error

CONFIG_DIR="/backup/config"
DATE=$(date +%Y%m%d_%H%M%S)
SOURCE_DIR="/root/minder/infrastructure/docker"
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

log "Starting config backup..."

# Create backup directory
mkdir -p "$CONFIG_DIR" || error_exit "Failed to create backup directory"

# Create timestamped backup directory
BACKUP_PATH="$CONFIG_DIR/$DATE"
mkdir -p "$BACKUP_PATH" || error_exit "Failed to create timestamped backup directory"

# Backup docker-compose.yml files
log "Backing up Docker Compose files..."
cp -r "$SOURCE_DIR/docker-compose.yml" "$BACKUP_PATH/" 2>/dev/null || {
  log "WARNING: docker-compose.yml not found or cannot be copied"
}

# Backup .env file (if exists)
if [ -f "$SOURCE_DIR/.env" ]; then
  log "Backing up .env file..."
  cp "$SOURCE_DIR/.env" "$BACKUP_PATH/.env.backup"

  # Sanitize .env (remove sensitive data for backup)
  grep -v "PASSWORD\|SECRET\|KEY" "$SOURCE_DIR/.env" > "$BACKUP_PATH/.env.sanitized" 2>/dev/null || true
fi

# Backup configuration directories
log "Backing up configuration directories..."
for config_dir in traefik authelia prometheus telegraf; do
  if [ -d "$SOURCE_DIR/$config_dir" ]; then
    log "Backing up $config_dir configuration..."
    cp -r "$SOURCE_DIR/$config_dir" "$BACKUP_PATH/" 2>/dev/null || {
      log "WARNING: Failed to backup $config_dir"
    }
  fi
done

# Backup scripts
log "Backing up scripts directory..."
if [ -d "$SOURCE_DIR/../scripts" ]; then
  cp -r "$SOURCE_DIR/../scripts" "$BACKUP_PATH/" 2>/dev/null || {
    log "WARNING: Failed to backup scripts"
  }
fi

# Create backup manifest
cat > "$BACKUP_PATH/manifest.txt" << EOF
Minder Platform Config Backup
Date: $(date)
Hostname: $(hostname)
User: $(whoami)
Working Directory: $(pwd)
Git Commit: $(cd /root/minder && git rev-parse HEAD 2>/dev/null || echo "N/A")
Git Branch: $(cd /root/minder && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "N/A")

Files Included:
$(find "$BACKUP_PATH" -type f | sed "s|$BACKUP_PATH/||" | sort)

EOF

# Compress the backup
log "Compressing backup..."
cd "$CONFIG_DIR"
tar czf "config_backup_${DATE}.tar.gz" "$DATE" 2>/dev/null || error_exit "Failed to compress backup"

# Calculate backup size
BACKUP_SIZE=$(du -h "$CONFIG_DIR/config_backup_${DATE}.tar.gz" | cut -f1)
log "Config backup compressed: config_backup_${DATE}.tar.gz ($BACKUP_SIZE)"

# Remove uncompressed directory
rm -rf "$BACKUP_PATH"

# Remove backups older than 30 days
log "Cleaning up old backups (older than 30 days)..."
DELETED=$(find "$CONFIG_DIR" -name "config_backup_*.tar.gz" -mtime +30 -delete -print | wc -l)
log "Deleted $DELETED old backup(s)"

# Verify backup was created
if [ -f "$CONFIG_DIR/config_backup_${DATE}.tar.gz" ]; then
  log "✅ Config backup completed successfully: config_backup_${DATE}.tar.gz ($BACKUP_SIZE)"
else
  error_exit "Backup file was not created"
fi

# List current backups
log "Current backups in $CONFIG_DIR:"
ls -lh "$CONFIG_DIR" | tail -10 | tee -a "$LOG_FILE"

exit 0

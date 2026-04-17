#!/bin/bash
###############################################################################
# Minder Automated Backup Script
# Performs comprehensive backup of all databases and configurations
###############################################################################

set -e  # Exit on any error

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/backup/minder}"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7
LOG_FILE="/var/log/minder-backup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Create backup directory
log "Creating backup directory..."
mkdir -p "$BACKUP_DIR/$DATE"

# Check if Docker containers are running
check_container() {
    if ! docker ps --format '{{.Names}}' | grep -q "^$1$"; then
        log_error "Container $1 is not running"
        return 1
    fi
    return 0
}

###############################################################################
# Backup Functions
###############################################################################

backup_postgres() {
    log "Backing up PostgreSQL..."

    if ! check_container "postgres"; then
        return 1
    fi

    # Backup all databases
    docker exec postgres pg_dumpall -U postgres | gzip > "$BACKUP_DIR/$DATE/postgres_all.sql.gz"

    # Backup individual plugin databases
    for db in fundmind minder_news minder_tefas minder_weather minder_crypto; do
        if docker exec postgres psql -U postgres -lqt | cut -d \| -f 1 | grep -qw "$db"; then
            log "  - Backing up database: $db"
            docker exec postgres pg_dump -U postgres "$db" | gzip > "$BACKUP_DIR/$DATE/postgres_${db}.sql.gz"
        fi
    done

    log_success "PostgreSQL backup completed"
}

backup_influxdb() {
    log "Backing up InfluxDB..."

    if ! check_container "influxdb"; then
        log_warning "InfluxDB container not running, skipping..."
        return 0
    fi

    # Create backup directory
    docker exec influxdb influx backup /tmp/$DATE/influxdb
    docker cp influxdb:/tmp/$DATE/influxdb "$BACKUP_DIR/$DATE/influxdb"
    docker exec influxdb rm -rf /tmp/$DATE

    log_success "InfluxDB backup completed"
}

backup_qdrant() {
    log "Backing up Qdrant..."

    if ! check_container "qdrant"; then
        log_warning "Qdrant container not running, skipping..."
        return 0
    fi

    # Backup Qdrant storage
    docker cp qdrant:/qdrant/storage "$BACKUP_DIR/$DATE/qdrant"

    log_success "Qdrant backup completed"
}

backup_configurations() {
    log "Backing up configurations..."

    # Backup environment variables
    if [ -f .env ]; then
        cp .env "$BACKUP_DIR/$DATE/.env"
        log "  - Backed up .env file"
    fi

    # Backup configuration files
    if [ -f config.yaml ]; then
        cp config.yaml "$BACKUP_DIR/$DATE/config.yaml"
        log "  - Backed up config.yaml"
    fi

    # Backup docker-compose configuration
    if [ -f docker-compose.yml ]; then
        cp docker-compose.yml "$BACKUP_DIR/$DATE/docker-compose.yml"
        log "  - Backed up docker-compose.yml"
    fi

    # Backup monitoring configurations
    mkdir -p "$BACKUP_DIR/$DATE/monitoring"
    [ -f prometheus.yml ] && cp prometheus.yml "$BACKUP_DIR/$DATE/monitoring/"
    [ -f alertmanager.yml ] && cp alertmanager.yml "$BACKUP_DIR/$DATE/monitoring/"

    log_success "Configuration backup completed"
}

backup_logs() {
    log "Backing up logs..."

    if [ -d logs ]; then
        mkdir -p "$BACKUP_DIR/$DATE/logs"
        tar -czf "$BACKUP_DIR/$DATE/logs.tar.gz" logs/
        log "  - Backed up application logs"
    fi

    # Backup Docker logs (last 24 hours)
    docker logs --since 24h minder-api > "$BACKUP_DIR/$DATE/minder-api.log" 2>&1 || true
    docker logs --since 24h postgres > "$BACKUP_DIR/$DATE/postgres.log" 2>&1 || true

    log_success "Logs backup completed"
}

backup_plugins() {
    log "Backing up plugin data..."

    # Backup plugin configurations and data
    if [ -d plugins ]; then
        mkdir -p "$BACKUP_DIR/$DATE/plugins"
        tar -czf "$BACKUP_DIR/$DATE/plugins.tar.gz" plugins/
        log "  - Backed up plugin directory"
    fi

    log_success "Plugin backup completed"
}

cleanup_old_backups() {
    log "Cleaning up old backups (older than $RETENTION_DAYS days)..."

    # Find and remove old backup directories
    find "$BACKUP_DIR" -maxdepth 1 -type d -mtime +$RETENTION_DAYS -exec rm -rf {} +

    # Also clean up old log files
    find "$LOG_FILE" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

    log_success "Old backups cleaned up"
}

calculate_backup_size() {
    local size=$(du -sh "$BACKUP_DIR/$DATE" | cut -f1)
    log "Total backup size: $size"
}

verify_backup() {
    log "Verifying backup integrity..."

    # Check if backup files exist and are not empty
    critical_files=(
        "$BACKUP_DIR/$DATE/postgres_all.sql.gz"
        "$BACKUP_DIR/$DATE/config.yaml"
    )

    for file in "${critical_files[@]}"; do
        if [ ! -f "$file" ]; then
            log_error "Critical backup file missing: $file"
            return 1
        fi

        if [ ! -s "$file" ]; then
            log_error "Critical backup file is empty: $file"
            return 1
        fi
    done

    log_success "Backup verification completed"
}

###############################################################################
# Main Execution
###############################################################################

main() {
    log "========================================"
    log "  Minder Backup Process Started"
    log "========================================"
    log "Backup ID: $DATE"
    log "Backup Location: $BACKUP_DIR/$DATE"
    log ""

    # Run backup functions
    backup_postgres
    backup_influxdb
    backup_qdrant
    backup_configurations
    backup_logs
    backup_plugins

    # Verify backup
    verify_backup

    # Calculate backup size
    calculate_backup_size

    # Cleanup old backups
    cleanup_old_backups

    log ""
    log "========================================"
    log "  Minder Backup Process Completed"
    log "========================================"
    log "Backup Location: $BACKUP_DIR/$DATE"
    log "Retention Period: $RETENTION_DAYS days"
    log ""

    # Generate backup manifest
    cat > "$BACKUP_DIR/$DATE/manifest.txt" <<EOF
Backup ID: $DATE
Date: $(date)
Host: $(hostname)
Backup Size: $(du -sh "$BACKUP_DIR/$DATE" | cut -f1)
Components:
  - PostgreSQL (all databases)
  - InfluxDB (time-series data)
  - Qdrant (vector embeddings)
  - Configurations (.env, config.yaml)
  - Logs (application and Docker)
  - Plugins (plugin code and data)
Retention: $RETENTION_DAYS days
EOF

    log_success "Backup manifest created: $BACKUP_DIR/$DATE/manifest.txt"

    # Exit successfully
    exit 0
}

# Trap errors
trap 'log_error "Backup process failed at line $LINENO"; exit 1' ERR

# Run main function
main "$@"

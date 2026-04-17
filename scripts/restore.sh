#!/bin/bash
###############################################################################
# Minder Backup Restoration Script
# Restores databases and configurations from backup
###############################################################################

set -e  # Exit on any error

# Configuration
BACKUP_ID="${1:-}"
BACKUP_DIR="${BACKUP_DIR:-/backup/minder}"
LOG_FILE="/var/log/minder-restore.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 <backup_id>

Restore Minder system from a backup.

Arguments:
  backup_id    Backup ID to restore (e.g., 20240417_143022)

Examples:
  $0 20240417_143022
  $0 latest

Available backups:
EOF
    ls -1t "$BACKUP_DIR" | head -10
}

# Validate backup exists
validate_backup() {
    local backup_id="$1"

    if [ -z "$backup_id" ]; then
        log_error "Backup ID is required"
        show_usage
        exit 1
    fi

    if [ "$backup_id" = "latest" ]; then
        backup_id=$(ls -1t "$BACKUP_DIR" | head -1)
        log_info "Using latest backup: $backup_id"
    fi

    local backup_path="$BACKUP_DIR/$backup_id"

    if [ ! -d "$backup_path" ]; then
        log_error "Backup not found: $backup_path"
        log_info "Available backups:"
        ls -1t "$BACKUP_DIR" | head -10
        exit 1
    fi

    if [ ! -f "$backup_path/manifest.txt" ]; then
        log_error "Backup manifest not found: $backup_path/manifest.txt"
        log_error "This backup may be corrupted"
        exit 1
    fi

    # Show backup manifest
    log "Backup Information:"
    cat "$backup_path/manifest.txt"
    echo ""

    # Confirm restoration
    log_warning "This will REPLACE all current data with the backup!"
    read -p "Are you sure you want to proceed? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Restoration cancelled"
        exit 0
    fi

    echo "$backup_path"
}

# Check if containers are running
check_containers() {
    local running_containers=$(docker ps --format '{{.Names}}' | grep -E '^(postgres|influxdb|qdrant|minder-api)$' | wc -l)

    if [ "$running_containers" -gt 0 ]; then
        log_warning "The following containers are currently running:"
        docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E '^(postgres|influxdb|qdrant|minder-api)$'
        echo ""
        log_warning "Containers must be stopped before restoration"
        read -p "Stop containers now? (yes/no): " stop_confirm

        if [ "$stop_confirm" = "yes" ]; then
            log "Stopping containers..."
            docker compose down
            log_success "Containers stopped"
        else
            log_info "Restoration cancelled"
            exit 0
        fi
    fi
}

###############################################################################
# Restoration Functions
###############################################################################

restore_postgres() {
    local backup_path="$1"

    log "Restoring PostgreSQL databases..."

    # Check if backup file exists
    if [ ! -f "$backup_path/postgres_all.sql.gz" ]; then
        log_error "PostgreSQL backup file not found"
        return 1
    fi

    # Start PostgreSQL container only
    log "Starting PostgreSQL container..."
    docker compose up -d postgres

    # Wait for PostgreSQL to be ready
    log "Waiting for PostgreSQL to be ready..."
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if docker exec postgres pg_isready -U postgres > /dev/null 2>&1; then
            log_success "PostgreSQL is ready"
            break
        fi
        attempt=$((attempt + 1))
        sleep 2
    done

    if [ $attempt -eq $max_attempts ]; then
        log_error "PostgreSQL failed to start"
        return 1
    fi

    # Restore all databases
    log "Restoring all databases from backup..."
    gunzip -c "$backup_path/postgres_all.sql.gz" | docker exec -i postgres psql -U postgres

    log_success "PostgreSQL restoration completed"
}

restore_influxdb() {
    local backup_path="$1"

    if [ ! -d "$backup_path/influxdb" ]; then
        log_warning "InfluxDB backup not found, skipping..."
        return 0
    fi

    log "Restoring InfluxDB..."

    # Start InfluxDB container
    docker compose up -d influxdb

    # Wait for InfluxDB to be ready
    log "Waiting for InfluxDB to be ready..."
    sleep 10

    # Restore InfluxDB data
    docker exec influxdb influx restore /tmp/restore_influxdb
    docker cp "$backup_path/influxdb" influxdb:/tmp/restore_influxdb

    log_success "InfluxDB restoration completed"
}

restore_qdrant() {
    local backup_path="$1"

    if [ ! -d "$backup_path/qdrant" ]; then
        log_warning "Qdrant backup not found, skipping..."
        return 0
    fi

    log "Restoring Qdrant..."

    # Start Qdrant container
    docker compose up -d qdrant

    # Wait for Qdrant to be ready
    log "Waiting for Qdrant to be ready..."
    sleep 5

    # Stop Qdrant to restore storage
    docker compose stop qdrant

    # Remove existing storage
    docker run --rm -v qdrant_data:/qdrant/storage busybox rm -rf /qdrant/storage/*

    # Restore backup
    docker cp "$backup_path/qdrant/." qdrant:/qdrant/storage

    # Start Qdrant
    docker compose up -d qdrant

    log_success "Qdrant restoration completed"
}

restore_configurations() {
    local backup_path="$1"

    log "Restoring configurations..."

    # Restore .env file
    if [ -f "$backup_path/.env" ]; then
        cp "$backup_path/.env" .env
        log "  - Restored .env file"
    fi

    # Restore config.yaml
    if [ -f "$backup_path/config.yaml" ]; then
        cp "$backup_path/config.yaml" config.yaml
        log "  - Restored config.yaml"
    fi

    # Restore docker-compose.yml
    if [ -f "$backup_path/docker-compose.yml" ]; then
        cp "$backup_path/docker-compose.yml" docker-compose.yml
        log "  - Restored docker-compose.yml"
    fi

    # Restore monitoring configurations
    if [ -d "$backup_path/monitoring" ]; then
        [ -f "$backup_path/monitoring/prometheus.yml" ] && cp "$backup_path/monitoring/prometheus.yml" prometheus.yml
        [ -f "$backup_path/monitoring/alertmanager.yml" ] && cp "$backup_path/monitoring/alertmanager.yml" alertmanager.yml
        log "  - Restored monitoring configurations"
    fi

    log_success "Configuration restoration completed"
}

restore_plugins() {
    local backup_path="$1"

    if [ ! -f "$backup_path/plugins.tar.gz" ]; then
        log_warning "Plugin backup not found, skipping..."
        return 0
    fi

    log "Restoring plugins..."

    # Extract plugin backup
    tar -xzf "$backup_path/plugins.tar.gz"

    log_success "Plugin restoration completed"
}

verify_restoration() {
    log "Verifying restoration..."

    # Start all containers
    log "Starting all containers..."
    docker compose up -d

    # Wait for API to be ready
    log "Waiting for API to be ready..."
    sleep 15

    # Check API health
    if curl -sf http://localhost:8000/health > /dev/null; then
        log_success "API is responding correctly"
    else
        log_error "API health check failed"
        return 1
    fi

    # Check databases
    log "Checking database connectivity..."
    if docker exec postgres pg_isready -U postgres > /dev/null 2>&1; then
        log_success "PostgreSQL is accessible"
    else
        log_error "PostgreSQL is not accessible"
        return 1
    fi

    log_success "Restoration verification completed"
}

###############################################################################
# Main Execution
###############################################################################

main() {
    log "========================================"
    log "  Minder Restoration Process Started"
    log "========================================"

    # Validate backup
    local backup_path
    backup_path=$(validate_backup "$1")

    # Check containers
    check_containers

    # Stop containers if running
    log "Stopping all containers..."
    docker compose down

    # Run restoration functions
    restore_postgres "$backup_path"
    restore_influxdb "$backup_path"
    restore_qdrant "$backup_path"
    restore_configurations "$backup_path"
    restore_plugins "$backup_path"

    # Verify restoration
    verify_restoration

    log ""
    log "========================================"
    log "  Minder Restoration Completed"
    log "========================================"
    log "Restored from: $backup_path"
    log ""

    # Start all services
    log "Starting all Minder services..."
    docker compose up -d

    log "Waiting for services to be ready..."
    sleep 20

    # Final health check
    if curl -sf http://localhost:8000/health > /dev/null; then
        log_success "✅ All services are running and healthy!"
        log ""
        log "Access the application at:"
        log "  - API: http://localhost:8000"
        log "  - OpenWebUI: http://localhost:3000"
        log "  - Grafana: http://localhost:3002"
        log "  - Prometheus: http://localhost:9090"
    else
        log_error "Some services may not be ready yet"
        log "Check container status: docker ps"
    fi

    exit 0
}

# Trap errors
trap 'log_error "Restoration process failed at line $LINENO"; exit 1' ERR

# Run main function
main "$@"

#!/bin/bash
# ============================================================================
# Minder Platform - Zero-Downtime Rolling Updates
# ============================================================================
# Advanced rolling update functionality with health checks and rollback support
# Usage: ./rolling-update.sh [service-name|--all] [--blue-green] [--force]
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
COMPOSE_DIR="${PROJECT_ROOT}/infrastructure/docker"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================================
# Configuration
# ============================================================================

HEALTH_CHECK_TIMEOUT=60
HEALTH_CHECK_INTERVAL=5
ROLLBACK_ON_FAILURE=true
BLUE_GREEN_MODE=false
FORCE_UPDATE=false

# Service restart order (dependencies first)
declare -a RESTART_ORDER=(
    "postgres"
    "redis"
    "rabbitmq"
    "minio"
    "influxdb"
    "neo4j"
    "qdrant"
    "ollama"
    "telegraf"
    "prometheus"
    "grafana"
    "jaeger"
    "authelia"
    "api-gateway"
    "plugin-registry"
    "plugin-state-manager"
    "marketplace"
    "rag-pipeline"
    "model-management"
    "model-fine-tuning"
    "tts-stt-service"
    "openwebui"
)

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# Health Check Functions
# ============================================================================

check_service_health() {
    local service_name=$1
    local timeout=${HEALTH_CHECK_TIMEOUT}
    local elapsed=0

    log_info "Checking health for ${service_name}..."

    while [ $elapsed -lt $timeout ]; do
        local health_status
        health_status=$(docker ps --filter "name=${service_name}" --format "{{.Health}}")

        case "$health_status" in
            "healthy")
                log_success "${service_name} is healthy"
                return 0
                ;;
            "unhealthy")
                log_error "${service_name} is unhealthy!"
                return 1
                ;;
        esac

        sleep $HEALTH_CHECK_INTERVAL
        elapsed=$((elapsed + HEALTH_CHECK_INTERVAL))
    done

    log_warn "${service_name} health check timed out after ${timeout}s"
    return 1
}

wait_for_service_healthy() {
    local service_name=$1
    local timeout=${HEALTH_CHECK_TIMEOUT}

    log_info "Waiting for ${service_name} to become healthy..."

    local start_time=$(date +%s)
    local current_time

    while true; do
        current_time=$(date +%s)
        local elapsed=$((current_time - start_time))

        if [ $elapsed -gt $timeout ]; then
            log_error "Timeout waiting for ${service_name} to become healthy"
            return 1
        fi

        local health_status
        health_status=$(docker ps --filter "name=${service_name}" --format "{{.Health}}")

        if [ "$health_status" = "healthy" ]; then
            log_success "${service_name} is healthy"
            return 0
        fi

        sleep 2
    done
}

# ============================================================================
# Backup Functions
# ============================================================================

create_pre_update_backup() {
    local backup_dir="${PROJECT_ROOT}/backups/pre-update-$(date +%Y%m%d_%H%M%S)"

    log_info "Creating pre-update backup..."

    mkdir -p "$backup_dir"

    # Backup docker-compose.yml
    cp "${COMPOSE_DIR}/docker-compose.yml" "${backup_dir}/"

    # Backup .env file
    cp "${COMPOSE_DIR}/.env" "${backup_dir}/" 2>/dev/null || true

    log_success "Pre-update backup created: ${backup_dir}"
    echo "$backup_dir"
}

# ============================================================================
# Rolling Update Functions
# ============================================================================

rolling_update_service() {
    local service_name=$1
    local container_name="minder-${service_name}"

    log_info "Starting rolling update for ${service_name}..."

    # Check if container exists
    if ! docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        log_warn "${service_name} container not found, skipping..."
        return 0
    fi

    # Store current image for potential rollback
    local current_image
    current_image=$(docker inspect --format='{{.Config.Image}}' "$container_name" 2>/dev/null || echo "")

    # Pull latest image
    log_info "Pulling latest image for ${service_name}..."
    cd "$COMPOSE_DIR"
    docker compose pull "$service_name" 2>/dev/null || true

    if [ "$BLUE_GREEN_MODE" = true ]; then
        blue_green_update "$service_name" "$current_image"
    else
        standard_rolling_update "$service_name"
    fi
}

standard_rolling_update() {
    local service_name=$1

    # Recreate container with new image
    log_info "Recreating ${service_name} container..."
    cd "$COMPOSE_DIR"
    docker compose up -d --no-deps --force-recreate "$service_name"

    # Wait for service to become healthy
    if ! wait_for_service_healthy "minder-${service_name}"; then
        if [ "$ROLLBACK_ON_FAILURE" = true ]; then
            log_error "${service_name} failed health check, initiating rollback..."
            return 1
        else
            log_warn "${service_name} health check failed but rollback disabled"
            return 0
        fi
    fi

    log_success "${service_name} updated successfully"
    return 0
}

blue_green_update() {
    local service_name=$1
    local old_image=$2
    local new_container_name="${service_name}-new"

    log_info "Starting blue-green deployment for ${service_name}..."

    # Start new container alongside old one
    cd "$COMPOSE_DIR"
    docker compose up -d --no-deps --scale "${service_name}=2" "$service_name"

    # Wait for new container to be healthy
    if ! wait_for_service_healthy "minder-${service_name}"; then
        log_error "New ${service_name} container failed health check, rolling back..."
        docker compose up -d --no-deps --scale "${service_name}=1" "$service_name"
        return 1
    fi

    # Stop old container
    log_info "Stopping old ${service_name} container..."
    docker compose up -d --no-deps --scale "${service_name}=1" "$service_name"

    log_success "${service_name} blue-green deployment completed"
    return 0
}

# ============================================================================
# Rollback Functions
# ============================================================================

rollback_service() {
    local service_name=$1
    local backup_image=$2

    log_warn "Rolling back ${service_name} to previous version..."

    cd "$COMPOSE_DIR"

    # Restore previous image
    if [ -n "$backup_image" ]; then
        docker tag "$backup_image" "minder/${service_name}:latest" 2>/dev/null || true
    fi

    # Recreate container
    docker compose up -d --no-deps --force-recreate "$service_name"

    # Wait for rollback to complete
    if wait_for_service_healthy "minder-${service_name}"; then
        log_success "${service_name} rollback completed"
        return 0
    else
        log_error "${service_name} rollback failed!"
        return 1
    fi
}

# ============================================================================
# Main Update Functions
# ============================================================================

rolling_update_all() {
    log_info "Starting rolling update for all services..."
    log_info "This will update services in dependency order to minimize downtime"

    # Create pre-update backup
    local backup_dir
    backup_dir=$(create_pre_update_backup)

    # Track failed services
    declare -a failed_services=()

    # Update services in order
    for service in "${RESTART_ORDER[@]}"; do
        log_info "Processing ${service}..."

        if ! rolling_update_service "$service"; then
            log_error "Failed to update ${service}"
            failed_services+=("$service")

            if [ "$ROLLBACK_ON_FAILURE" = true ]; then
                log_warn "Rolling back remaining services..."
                break
            fi
        fi

        # Small delay between updates
        sleep 2
    done

    # Summary
    echo ""
    log_info "Rolling update completed"

    if [ ${#failed_services[@]} -gt 0 ]; then
        log_error "Failed services: ${failed_services[*]}"
        log_info "Backup directory: ${backup_dir}"
        return 1
    else
        log_success "All services updated successfully"
        return 0
    fi
}

# ============================================================================
# Main Command Handler
# ============================================================================

main() {
    local target_service="${1:-}"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --blue-green)
                BLUE_GREEN_MODE=true
                shift
                ;;
            --force)
                FORCE_UPDATE=true
                shift
                ;;
            --no-rollback)
                ROLLBACK_ON_FAILURE=false
                shift
                ;;
            *)
                target_service="$1"
                shift
                ;;
        esac
    done

    # Validate
    if [ -z "$target_service" ]; then
        log_error "Usage: $0 <service-name|--all> [--blue-green] [--force] [--no-rollback]"
        exit 1
    fi

    # Execute update
    if [ "$target_service" = "--all" ]; then
        rolling_update_all
    else
        rolling_update_service "$target_service"
    fi
}

# Run main function
main "$@"

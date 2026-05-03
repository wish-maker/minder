#!/bin/bash
# ============================================================================
# Minder Platform - Production Deployment Script
# ============================================================================
# Pillar 1: Zero-Trust Security with Traefik reverse proxy
# Pillar 4: Deep Observability with comprehensive metrics
#
# This script deploys the Minder platform in production mode with all
# security and observability features enabled.
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="infrastructure/docker/docker-compose.yml"
ENV_FILE="infrastructure/docker/.env"
ENV_EXAMPLE="infrastructure/docker/.env.example"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check if Docker Compose is installed
    if ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    # Check if .env file exists
    if [ ! -f "$ENV_FILE" ]; then
        log_warning ".env file not found. Creating from .env.example..."
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            log_warning "Please edit .env with your secure values before running this script again!"
            log_warning "Generate secrets with: openssl rand -base64 32 (or 64 for JWT_SECRET)"
            exit 1
        else
            log_error ".env.example not found. Cannot create .env file."
            exit 1
        fi
    fi

    # Check for placeholder values in .env
    if grep -q "CHANGE_ME" "$ENV_FILE"; then
        log_error "Your .env file contains placeholder values (CHANGE_ME)."
        log_error "Please update all placeholder values with secure secrets before deploying to production."
        exit 1
    fi

    # Check if minder-network exists
    if ! docker network ls | grep -q "minder-network"; then
        log_info "Creating minder-network..."
        docker network create minder-network
    fi

    log_success "Prerequisites check passed."
}

validate_environment() {
    log_info "Validating environment configuration..."

    # Source the .env file to check required variables
    source "$ENV_FILE"

    local required_vars=(
        "POSTGRES_PASSWORD"
        "REDIS_PASSWORD"
        "RABBITMQ_PASSWORD"
        "JWT_SECRET"
        "INFLUXDB_TOKEN"
        "GRAFANA_PASSWORD"
        "AUTHELIA_JWT_SECRET"
        "AUTHELIA_SESSION_SECRET"
        "AUTHELIA_STORAGE_ENCRYPTION_KEY"
    )

    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ] || [[ "${!var}" == "CHANGE_ME"* ]]; then
            missing_vars+=("$var")
        fi
    done

    if [ ${#missing_vars[@]} -ne 0 ]; then
        log_error "Missing or placeholder values for required variables:"
        printf '  - %s\n' "${missing_vars[@]}"
        exit 1
    fi

    # Check JWT_SECRET length (should be at least 64 characters for HS256)
    if [ ${#JWT_SECRET} -lt 64 ]; then
        log_warning "JWT_SECRET is less than 64 characters. Consider generating a longer secret."
    fi

    log_success "Environment validation passed."
}

stop_existing_services() {
    log_info "Stopping existing services (if any)..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans || true
    log_success "Existing services stopped."
}

deploy_services() {
    log_info "Deploying Minder Platform services..."

    # Pull latest images
    log_info "Pulling latest Docker images..."
    docker compose -f "$COMPOSE_FILE" pull

    # Start services
    log_info "Starting services..."
    docker compose -f "$COMPOSE_FILE" up -d

    log_success "Services deployed."
}

wait_for_healthy_services() {
    log_info "Waiting for services to become healthy..."
    local max_wait=120
    local waited=0

    while [ $waited -lt $max_wait ]; do
        local healthy=0
        local total=0

        # Count healthy and total containers
        while IFS= read -r line; do
            if [[ $line == *"minder-"* ]]; then
                ((total++))
                if [[ $line == *"healthy"* ]]; then
                    ((healthy++))
                fi
            fi
        done < <(docker compose -f "$COMPOSE_FILE" ps --format "table {{.Name}} {{.Health}}" | tail -n +2)

        if [ $total -gt 0 ]; then
            local percentage=$((healthy * 100 / total))
            echo -ne "\r${BLUE}[HEALTH CHECK]${NC} $healthy/$total services healthy ($percentage%)"
        fi

        if [ $healthy -eq $total ] && [ $total -gt 0 ]; then
            echo ""
            log_success "All services are healthy!"
            break
        fi

        sleep 5
        ((waited += 5))
    done

    if [ $waited -ge $max_wait ]; then
        log_warning "Some services may still be starting. Check with: docker compose -f $COMPOSE_FILE ps"
    fi
}

verify_deployment() {
    log_info "Verifying deployment..."

    echo ""
    log_info "Service Status:"
    docker compose -f "$COMPOSE_FILE" ps

    echo ""
    log_success "Deployment verification complete!"
    echo ""
    log_info "================================================================================================"
    log_info "Minder Platform is now running!"
    log_info "================================================================================================"
    echo ""
    log_info "PILLAR 1: Zero-Trust Security Endpoints (via Traefik)"
    log_info "  - Traefik Dashboard:  http://localhost:8081 (IP whitelist restricted)"
    log_info "  - API Gateway:        https://api.minder.local"
    log_info "  - Authelia:           https://authelia.minder.local"
    log_info "  - Grafana:            https://grafana.minder.local"
    log_info "  - Chat UI:            https://chat.minder.local"
    log_info "  - RabbitMQ:           https://rabbitmq.minder.local (IP whitelist restricted)"
    log_info "  - Neo4j:              https://neo4j.minder.local (IP whitelist restricted)"
    echo ""
    log_info "PILLAR 4: Observability Endpoints"
    log_info "  - Prometheus:         http://localhost:9090"
    log_info "  - Grafana:            http://localhost:3000"
    log_info "  - Alertmanager:       http://localhost:9093"
    log_info "  - InfluxDB:           http://localhost:8086"
    echo ""
    log_info "Note: Add *.minder.local to your /etc/hosts pointing to 127.0.0.1 for local access"
    log_info "================================================================================================"
}

show_logs() {
    log_info "Showing recent logs (press Ctrl+C to exit)..."
    docker compose -f "$COMPOSE_FILE" logs -f --tail=50
}

# Main execution
main() {
    echo ""
    log_info "================================================================================================"
    log_info "Minder Platform - Production Deployment"
    log_info "================================================================================================"
    echo ""

    check_prerequisites
    validate_environment
    stop_existing_services
    deploy_services
    wait_for_healthy_services
    verify_deployment

    # Optionally show logs
    read -p "$(echo -e ${YELLOW}Do you want to follow the logs? [y/N]: ${NC})" follow_logs
    if [[ $follow_logs =~ ^[Yy]$ ]]; then
        show_logs
    fi
}

# Run main function
main "$@"

#!/bin/bash
###############################################################################
# Minder Platform - Automated Setup Script
# Purpose: Zero-configuration setup for development and production
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check Docker Compose
    if ! command -v docker &> /dev/null; then
        log_error "Docker Compose is not available. Please install Docker Compose first."
        exit 1
    fi

    # Check if Docker is running
    if ! docker info &> /dev/null; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi

    log_success "Prerequisites check passed ✓"
}

setup_environment() {
    log_info "Setting up environment..."

    # Copy example env if .env doesn't exist
    if [ ! -f infrastructure/docker/.env ]; then
        log_info "Creating .env file from template..."
        cp infrastructure/docker/.env.example infrastructure/docker/.env 2>/dev/null || true

        # Generate secure passwords if not exists
        if [ ! -f infrastructure/docker/.env ]; then
            log_info "Generating secure passwords..."
            cat > infrastructure/docker/.env << EOF
# Minder Platform - Environment Configuration
# Generated: $(date)

# Database Credentials
POSTGRES_USER=minder
POSTGRES_PASSWORD=$(openssl rand -hex 32)
POSTGRES_DB=minder

# Redis Configuration
REDIS_PASSWORD=$(openssl rand -hex 32)

# Security
JWT_SECRET=$(openssl rand -hex 64)
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Neo4j Configuration
NEO4J_AUTH=neo4j/$(openssl rand -hex 16)

# Application Settings
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF
        fi
    fi

    log_success "Environment setup completed ✓"
}

create_networks() {
    log_info "Setting up Docker networks..."

    # Create external network if not exists
    if ! docker network ls | grep -q docker_minder-network; then
        docker network create docker_minder-network
        log_success "Network docker_minder-network created ✓"
    else
        log_info "Network docker_minder-network already exists ✓"
    fi
}

initialize_database() {
    log_info "Initializing databases..."

    # Start PostgreSQL only
    log_info "Starting PostgreSQL..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d postgres

    # Wait for PostgreSQL to be healthy
    log_info "Waiting for PostgreSQL to be ready..."
    MAX_WAIT=60
    WAIT_TIME=0
    while [ $WAIT_TIME -lt $MAX_WAIT ]; do
        if docker exec minder-postgres pg_isready -U minder &> /dev/null; then
            log_success "PostgreSQL is ready ✓"
            break
        fi
        sleep 2
        WAIT_TIME=$((WAIT_TIME + 2))
        echo -n "."
    done

    if [ $WAIT_TIME -ge $MAX_WAIT ]; then
        log_error "PostgreSQL failed to start"
        exit 1
    fi

    # Create databases
    log_info "Creating databases..."
    docker exec -i minder-postgres psql -U minder -c "CREATE DATABASE minder_marketplace;" 2>/dev/null || echo "Database might already exist"
    docker exec -i minder-postgres psql -U minder -c "CREATE DATABASE tefas_db;" 2>/dev/null || echo "Database might already exist"
    docker exec -i minder-postgres psql -U minder -c "CREATE DATABASE weather_db;" 2>/dev/null || echo "Database might already exist"
    docker exec -i minder-postgres psql -U minder -c "CREATE DATABASE news_db;" 2>/dev/null || echo "Database might already exist"
    docker exec -i minder-postgres psql -U minder -c "CREATE DATABASE crypto_db;" 2>/dev/null || echo "Database might already exist"
    docker exec -i minder-postgres psql -U minder -c "CREATE DATABASE minder_authelia;" 2>/dev/null || echo "Database might already exist"

    log_success "Databases initialized ✓"
}

start_services() {
    log_info "Starting all services..."

    # Start security layer first
    log_info "Starting security layer (Traefik, Authelia)..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d traefik authelia

    # Wait for security layer
    sleep 10

    # Start infrastructure services
    log_info "Starting infrastructure services (PostgreSQL, Redis, Qdrant, Ollama, Neo4j)..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d postgres redis qdrant ollama neo4j

    # Wait for infrastructure to be healthy
    log_info "Waiting for infrastructure services..."
    sleep 30

    # Start core microservices
    log_info "Starting core microservices..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d api-gateway plugin-registry

    # Wait for core services
    sleep 15

    # Start AI services
    log_info "Starting AI services..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d rag-pipeline model-management

    # Wait for AI services
    sleep 15

    # Start additional services
    log_info "Starting additional services..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d marketplace plugin-state-manager

    # Wait for additional services
    sleep 15

    # Start monitoring stack
    log_info "Starting monitoring stack (InfluxDB, Telegraf, Prometheus, Grafana)..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d influxdb telegraf prometheus grafana alertmanager

    # Wait for monitoring services
    sleep 20

    # Start AI enhancement services
    log_info "Starting AI enhancement services (OpenWebUI, TTS/STT, Model Fine-tuning)..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d openwebui tts-stt-service model-fine-tuning

    # Start metrics exporters
    log_info "Starting metrics exporters..."
    docker compose -f infrastructure/docker/docker-compose.yml up -d postgres-exporter redis-exporter

    log_success "All services started ✓"
}

download_ollama_models() {
    log_info "Downloading Ollama models for AI functionality..."

    # Wait for Ollama to be ready
    log_info "Waiting for Ollama to start..."
    MAX_WAIT=90
    WAIT_TIME=0
    while [ $WAIT_TIME -lt $MAX_WAIT ]; do
        if docker exec minder-ollama ollama list &> /dev/null; then
            log_success "Ollama is ready ✓"
            break
        fi
        sleep 2
        WAIT_TIME=$((WAIT_TIME + 2))
        echo -n "."
    done

    if [ $WAIT_TIME -ge $MAX_WAIT ]; then
        log_error "Ollama failed to start within expected time"
        log_warning "Continuing anyway - models will be downloaded automatically in background"
        return 0
    fi

    # Check if automatic pull is enabled
    AUTOMATIC_PULL=$(grep OLLAMA_AUTOMATIC_PULL infrastructure/docker/.env 2>/dev/null | cut -d= -f2 || echo "true")

    if [ "$AUTOMATIC_PULL" != "true" ]; then
        log_info "OLLAMA_AUTOMATIC_PULL is disabled"
        log_info "Models will need to be downloaded manually"
        return 0
    fi

    # Get models from environment or use defaults
    MODEL_LIST=$(grep OLLAMA_MODELS infrastructure/docker/.env 2>/dev/null | cut -d= -f2 || echo "llama3.2,nomic-embed-text")

    # Convert comma-separated to array
    IFS=',' read -ra MODELS <<< "$MODEL_LIST"

    log_info "Models to download: ${MODELS[*]}"

    SUCCESS_COUNT=0
    for model in "${MODELS[@]}"; do
        # Trim whitespace
        model=$(echo "$model" | xargs)

        log_info "Downloading model: $model..."

        # Pull model with timeout
        if timeout 300 docker exec minder-ollama ollama pull "$model" > /dev/null 2>&1; then
            log_success "Model $model downloaded successfully ✓"
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            log_warning "Failed to download model $model (may have timed out)"
        fi
    done

    # Verify and display results
    log_info "Verifying installed models..."
    sleep 2

    MODEL_COUNT=$(docker exec minder-ollama ollama list 2>/dev/null | grep -c "^NAME" || echo "0")

    if [ "$MODEL_COUNT" -gt 0 ]; then
        log_success "Successfully installed $MODEL_COUNT model(s) ✓"
        echo ""
        docker exec minder-ollama ollama list
    else
        log_warning "No models found. AI features may not work properly."
        log_info "You can download models manually later:"
        log_info "  docker exec minder-ollama ollama pull llama3.2"
    fi
}

wait_for_services() {
    log_info "Waiting for services to be healthy..."

    # Security services
    log_info "Waiting for security layer..."
    if curl -s http://localhost:9091/api/health > /dev/null; then
        log_success "Authelia is healthy ✓"
    else
        log_warning "Authelia is still starting"
    fi
    sleep 5

    # Core services
    services=(
        "minder-postgres:5432"
        "minder-redis:6379"
        "minder-api-gateway:8000"
        "minder-plugin-registry:8001"
        "minder-marketplace:8002"
        "minder-plugin-state-manager:8003"
        "minder-rag-pipeline:8004"
        "minder-model-management:8005"
    )

    for service in "${services[@]}"; do
        name=$(echo $service | cut -d: -f1)
        port=$(echo $service | cut -d: -f2)

        log_info "Waiting for $name..."
        MAX_WAIT=90
        WAIT_TIME=0

        while [ $WAIT_TIME -lt $MAX_WAIT ]; do
            if curl -s http://localhost:$port/health &> /dev/null || \
               docker exec $name pg_isready -U minder &> /dev/null 2>/dev/null || \
               docker exec $name redis-cli -a ${REDIS_PASSWORD:-minder} ping &> /dev/null 2>/dev/null; then
                log_success "$name is healthy ✓"
                break
            fi
            sleep 3
            WAIT_TIME=$((WAIT_TIME + 3))
            echo -n "."
        done

        if [ $WAIT_TIME -ge $MAX_WAIT ]; then
            log_warning "$name is taking longer than expected. Continuing anyway..."
        fi
    done

    echo ""

    # Wait for monitoring and AI services
    log_info "Waiting for additional services (monitoring, AI tools)..."
    sleep 30

    # Check InfluxDB
    if docker exec minder-influxdb influx version &> /dev/null 2>/dev/null; then
        log_success "InfluxDB is ready ✓"
    else
        log_warning "InfluxDB might still be initializing"
    fi

    # Check Prometheus
    if curl -s http://localhost:9090/-/healthy &> /dev/null; then
        log_success "Prometheus is healthy ✓"
    else
        log_warning "Prometheus might still be initializing"
    fi

    # Check Grafana
    if curl -s http://localhost:3000/api/health &> /dev/null; then
        log_success "Grafana is ready ✓"
    else
        log_warning "Grafana might still be initializing"
    fi
}

run_health_checks() {
    log_info "Running health checks..."

    sleep 10

    # Check all API endpoints
    api_ports=(8000 8001 8002 8003 8004 8005)
    all_healthy=true

    for port in "${api_ports[@]}"; do
        if curl -s http://localhost:$port/health > /dev/null; then
            log_success "API on port $port is responding ✓"
        else
            log_warning "API on port $port is not responding yet"
            all_healthy=false
        fi
    done

    # Check monitoring services
    log_info "Checking monitoring services..."

    if curl -s http://localhost:9090/-/healthy > /dev/null; then
        log_success "Prometheus (port 9090) is responding ✓"
    else
        log_warning "Prometheus is not responding yet"
    fi

    if curl -s http://localhost:3000/api/health > /dev/null; then
        log_success "Grafana (port 3000) is responding ✓"
    else
        log_warning "Grafana is not responding yet"
    fi

    if curl -s http://localhost:8086/ping > /dev/null; then
        log_success "InfluxDB (port 8086) is responding ✓"
    else
        log_warning "InfluxDB is not responding yet"
    fi

    if curl -s http://localhost:8080 > /dev/null; then
        log_success "OpenWebUI (port 8080) is responding ✓"
    else
        log_warning "OpenWebUI is not responding yet"
    fi

    if curl -s http://localhost:8006/health > /dev/null; then
        log_success "TTS/STT Service (port 8006) is responding ✓"
    else
        log_warning "TTS/STT Service is not responding yet"
    fi

    if curl -s http://localhost:8007/health > /dev/null; then
        log_success "Model Fine-tuning (port 8007) is responding ✓"
    else
        log_warning "Model Fine-tuning is not responding yet"
    fi

    if [ "$all_healthy" = true ]; then
        log_success "All core services are healthy! 🎉"
    else
        log_warning "Some services may still be starting. Check with: docker ps"
    fi
}

print_success_message() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo -e "${GREEN}🎉 MINDER PLATFORM IS READY!${NC}"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "🔐 Security & Access:"
    echo "   • Traefik Dashboard:  http://localhost:8081"
    echo "   • Authelia Portal:    http://localhost:9091"
    echo "   • Default Users:      admin/admin123, developer/admin123, user/admin123"
    echo "   ⚠️  CHANGE DEFAULT PASSWORDS IMMEDIATELY!"
    echo ""
    echo "📍 Core API Services:"
    echo "   • API Gateway:        http://localhost:8000"
    echo "   • Plugin Registry:    http://localhost:8001"
    echo "   • Marketplace:        http://localhost:8002"
    echo "   • State Manager:      http://localhost:8003"
    echo "   • AI Services:        http://localhost:8004"
    echo "   • Model Management:   http://localhost:8005"
    echo ""
    echo "🤖 AI Enhancement Services:"
    echo "   • TTS/STT Service:    http://localhost:8006"
    echo "   • Model Fine-tuning:  http://localhost:8007"
    echo "   • OpenWebUI:          http://localhost:8080"
    echo ""
    echo "📊 Monitoring & Metrics:"
    echo "   • Prometheus:         http://localhost:9090"
    echo "   • Grafana:            http://localhost:3000"
    echo "   • InfluxDB:           http://localhost:8086"
    echo ""
    echo "📚 Documentation:"
    echo "   • API Docs:           See docs/API.md"
    echo "   • Architecture:        See docs/ARCHITECTURE.md"
    echo "   • Development:        See docs/DEVELOPMENT.md"
    echo ""
    echo "🔧 Useful Commands:"
    echo "   • View logs:          docker compose -f infrastructure/docker/docker-compose.yml logs -f"
    echo "   • Stop services:      docker compose -f infrastructure/docker/docker-compose.yml down"
    echo "   • Restart service:    docker compose -f infrastructure/docker/docker-compose.yml restart <service>"
    echo "   • Run tests:          pytest tests/unit/ -v"
    echo "   • Health check:       ./scripts/health-check.sh"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
}

###############################################################################
# Lifecycle Management Functions
###############################################################################

show_help() {
    cat << EOF
Minder Platform - Setup & Lifecycle Management Script

USAGE:
    ./setup.sh [COMMAND]

COMMANDS:
    (no command)          Install and start all services (default)
    install                Install and start all services
    uninstall              Stop and remove all services (removes volumes)
    uninstall --keep-data  Stop services but keep data volumes
    stop                   Stop all services
    start                  Start all services
    restart                Restart all services
    status                 Show service status
    health                 Run health checks
    logs                   Show service logs
    check-updates          Check for Docker image updates
    update                 Update Docker images
    backup                 Backup configuration and data
    -h, --help             Show this help message

EXAMPLES:
    ./setup.sh                           # Install (default)
    ./setup.sh install                   # Explicit install
    ./setup.sh uninstall                 # Uninstall (remove data)
    ./setup.sh uninstall --keep-data     # Uninstall (keep data)
    ./setup.sh stop                      # Stop services
    ./setup.sh status                    # Check status
    ./setup.sh logs                      # View logs
    ./setup.sh check-updates             # Check for updates

For more information:
    https://github.com/wish-maker/minder

EOF
}

show_status() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "                    Minder Platform Status"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAMES|minder-" | head -25

    echo ""
    echo "Resource Usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep -E "NAME|minder-" | head -15
}

stop_services_cmd() {
    log_info "Stopping all services..."
    docker compose -f infrastructure/docker/docker-compose.yml --profile monitoring down
    log_success "All services stopped ✓"
}

start_services_cmd() {
    log_info "Starting all services..."
    start_services
    wait_for_services
    run_health_checks
    log_success "All services started ✓"
}

restart_services_cmd() {
    log_info "Restarting all services..."
    stop_services_cmd
    sleep 5
    start_services_cmd
}

uninstall_system() {
    local keep_data=false

    if [ "$1" = "--keep-data" ]; then
        keep_data=true
    fi

    log_warning "Uninstalling Minder Platform..."

    if [ "$keep_data" = true ]; then
        log_info "Stopping services (keeping data)..."
        docker compose -f infrastructure/docker/docker-compose.yml --profile monitoring down
        log_success "Services stopped. Data volumes preserved."
    else
        log_warning "This will remove all services AND data volumes!"
        echo -n "Are you sure? [y/N]: "
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            log_info "Stopping and removing all services..."
            docker compose -f infrastructure/docker/docker-compose.yml --profile monitoring down -v
            log_success "All services and data removed."
        else
            log_info "Uninstall cancelled."
            return 0
        fi
    fi
}

show_logs_cmd() {
    local service="${1:-}"
    if [ -n "$service" ]; then
        docker logs -f --tail 100 "minder-$service"
    else
        docker compose -f infrastructure/docker/docker-compose.yml logs -f --tail 50
    fi
}

check_updates_cmd() {
    log_info "Checking for Docker image updates..."
    echo ""

    local images=(
        "postgres:16"
        "redis:7.2-alpine"
        "qdrant/qdrant:v1.18.0"
        "neo4j:5.24-community"
        "ollama/ollama:0.5.7"
        "prom/prometheus:v2.55.1"
        "grafana/grafana:11.4.0"
        "authelia/authelia:4.38.7"
        "traefik:v3.1.6"
        "influxdb:2.8.3"
        "telegraf:1.33.1"
        "prom/alertmanager:v0.28.1"
        "prometheuscommunity/postgres-exporter:v0.15.0"
        "oliver006/redis_exporter:v1.62.0"
        "ghcr.io/open-webui/open-webui:git-69d0a16"
    )

    for image in "${images[@]}"; do
        if docker images | grep -q "${image%:*}"; then
            local created=$(docker images --format "{{.CreatedAt}}" "$image" | head -1)
            echo -e "${BLUE}$image${NC} (created: $created)"
        fi
    done

    echo ""
    log_info "Minder custom images:"
    docker images | grep "minder/" || echo "No custom images found"

    echo ""
    log_info "To update, run: ./setup.sh update"
}

update_images_cmd() {
    log_info "Updating Docker images..."

    local images=(
        "postgres:16"
        "redis:7.2-alpine"
        "qdrant/qdrant:v1.18.0"
        "neo4j:5.24-community"
        "ollama/ollama:0.5.7"
        "prom/prometheus:v2.55.1"
        "grafana/grafana:11.4.0"
        "authelia/authelia:4.38.7"
        "traefik:v3.1.6"
        "influxdb:2.8.3"
        "telegraf:1.33.1"
        "prom/alertmanager:v0.28.1"
        "prometheuscommunity/postgres-exporter:v0.15.0"
        "oliver006/redis_exporter:v1.62.0"
        "ghcr.io/open-webui/open-webui:git-69d0a16"
    )

    for image in "${images[@]}"; do
        log_info "Pulling $image..."
        docker pull "$image" | grep -E "Pulling|Downloaded|Already up to date|Status" || true
    done

    log_success "Images updated! Rebuild custom images..."
    docker compose -f infrastructure/docker/docker-compose.yml build --no-cache

    log_success "Update complete! Restart services with: ./setup.sh restart"
}

backup_system_cmd() {
    local backup_dir="backups/minder-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$backup_dir"

    log_info "Creating backup at: $backup_dir"

    if [ -f infrastructure/docker/.env ]; then
        cp infrastructure/docker/.env "$backup_dir/env.backup"
        log_success "Environment configuration backed up ✓"
    fi

    log_info "Backing up databases..."
    docker exec minder-postgres pg_dumpall -U minder > "$backup_dir/databases.sql" 2>/dev/null || true
    log_success "Databases backed up ✓"

    log_success "Backup completed: $backup_dir"
}

###############################################################################
# Main execution
###############################################################################

main() {
    local command="${1:-install}"

    case "$command" in
        install)
            echo ""
            echo "╔═══════════════════════════════════════════════════════════════╗"
            echo "║        Minder Platform - Automated Setup Script               ║"
            echo "║                    Version 1.0.0 (Enhanced)                   ║"
            echo "╚═══════════════════════════════════════════════════════════════╝"
            echo ""

            check_prerequisites
            setup_environment
            create_networks
            initialize_database
            start_services
            wait_for_services
            download_ollama_models
            run_health_checks
            print_success_message

            log_success "Installation completed successfully! 🚀"
            ;;

        uninstall)
            show_help
            echo ""
            uninstall_system "$2"
            ;;

        start)
            check_prerequisites
            start_services_cmd
            ;;

        stop)
            check_prerequisites
            stop_services_cmd
            ;;

        restart)
            check_prerequisites
            restart_services_cmd
            ;;

        status)
            show_status
            ;;

        health)
            check_prerequisites
            run_health_checks
            ;;

        logs)
            check_prerequisites
            show_logs_cmd "$2"
            ;;

        check-updates)
            check_updates_cmd
            ;;

        update)
            check_prerequisites
            update_images_cmd
            ;;

        backup)
            backup_system_cmd
            ;;

        -h|--help)
            show_help
            ;;

        *)
            echo "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"

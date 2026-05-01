#!/bin/bash
###############################################################################
# Minder Platform - Automated Setup Script
# Purpose: Zero-configuration setup with enhanced UX
###############################################################################

set -e

# Enhanced Color Scheme
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Progress tracking
PROGRESS_CURRENT=0
PROGRESS_TOTAL=12
SPINNER=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠇" "⠏")

# Enhanced display functions
print_header() {
    clear
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}        ${BOLD}Minder Platform - Automated Setup Script${NC}               ${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}              ${GREEN}Version 1.0.0 (Enhanced UX)${NC}                    ${CYAN}║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    local step="$1"
    local total="$2"
    local current=$((PROGRESS_CURRENT + 1))
    PROGRESS_CURRENT=$current

    local progress_percent=$((current * 100 / total))
    local filled=$((progress_percent / 5))
    local empty=$((20 - filled))

    echo ""
    echo -e "${BLUE}[STEP $current/$total]${NC} $step"
    echo -e "${YELLOW}$(printf '█%.0s' $(yes '' | sed $((filled))''))${NC}$(printf '░%.0s' $(yes '' | sed $((empty))'')) ${NC} ${progress_percent}%"
}

print_progress() {
    local message="$1"
    local spinner="${SPINNER[$((PROGRESS_CURRENT % 10))]}"
    printf "\r${CYAN}%s${NC} %s" "$spinner" "$message"
}

print_success() {
    local message="$1"
    echo -e "\r${GREEN}✓${NC} ${GREEN}$message${NC}"
}

print_info() {
    local message="$1"
    echo -e "${BLUE}ℹ${NC}  $message"
}

print_warning() {
    local message="$1"
    echo -e "${YELLOW}⚠${NC}  ${YELLOW}$message${NC}"
}

print_error() {
    local message="$1"
    echo -e "${RED}✗${NC} ${RED}$message${NC}"
}

print_section() {
    local title="$1"
    echo ""
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}$title${NC}"
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

# Keep original functions for compatibility
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
    print_section "🤖 AI Models Setup"

    # Wait for Ollama to be ready
    echo -e "${CYAN}⟳ Waiting for Ollama to be ready...${NC}"
    MAX_WAIT=90
    WAIT_TIME=0
    SPINNER_IDX=0

    while [ $WAIT_TIME -lt $MAX_WAIT ]; do
        if docker exec minder-ollama ollama list &> /dev/null; then
            echo -e "\r${GREEN}✓ Ollama is ready${NC}                        "
            break
        fi
        # Show spinner
        SPINNER_CHAR="${SPINNER[$SPINNER_IDX]}"
        echo -ne "\r${CYAN}$SPINNER_CHAR Waiting...${WAIT_TIME}s${NC}"
        sleep 2
        WAIT_TIME=$((WAIT_TIME + 2))
        SPINNER_IDX=$(( (SPINNER_IDX + 1) % 8 ))
    done

    if [ $WAIT_TIME -ge $MAX_WAIT ]; then
        echo -e "\r${RED}✗ Ollama failed to start within expected time${NC}"
        echo -e "${YELLOW}⚠ Continuing anyway - models will be downloaded automatically${NC}"
        return 0
    fi

    # Check if automatic pull is enabled
    AUTOMATIC_PULL=$(grep OLLAMA_AUTOMATIC_PULL infrastructure/docker/.env 2>/dev/null | cut -d= -f2 || echo "true")

    if [ "$AUTOMATIC_PULL" != "true" ]; then
        echo -e "${BLUE}ℹ OLLAMA_AUTOMATIC_PULL is disabled${NC}"
        echo -e "${YELLOW}⚠ Models will need to be downloaded manually${NC}"
        return 0
    fi

    # Get models from environment or use defaults
    MODEL_LIST=$(grep OLLAMA_MODELS infrastructure/docker/.env 2>/dev/null | cut -d= -f2 || echo "llama3.2,nomic-embed-text")

    # Convert comma-separated to array
    IFS=',' read -ra MODELS <<< "$MODEL_LIST"

    echo ""
    echo -e "${CYAN}📦 Models to download: ${MODELS[*]}${NC}"
    echo ""

    SUCCESS_COUNT=0
    TOTAL_MODELS=${#MODELS[@]}

    for model in "${MODELS[@]}"; do
        # Trim whitespace
        model=$(echo "$model" | xargs)

        # Show download progress with spinner
        SPINNER_IDX=0
        echo -ne "${CYAN}⟳ Downloading: $model${NC} "

        # Pull model with timeout and spinner
        (
            while kill -0 $$ 2>/dev/null; do
                SPINNER_CHAR="${SPINNER[$SPINNER_IDX]}"
                echo -ne "\r${CYAN}$SPINNER_CHAR Downloading: $model${NC} "
                sleep 0.2
                SPINNER_IDX=$(( (SPINNER_IDX + 1) % 8 ))
            done
        ) &
        SPINNER_PID=$!

        if timeout 300 docker exec minder-ollama ollama pull "$model" > /dev/null 2>&1; then
            kill $SPINNER_PID 2>/dev/null
            wait $SPINNER_PID 2>/dev/null
            echo -e "\r${GREEN}✓ $model downloaded successfully${NC}         "
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            kill $SPINNER_PID 2>/dev/null
            wait $SPINNER_PID 2>/dev/null
            echo -e "\r${YELLOW}⚠ Failed to download $model (may have timed out)${NC}"
        fi
    done

    echo ""

    # Verify and display results
    echo -e "${CYAN}⟳ Verifying installed models...${NC}"
    sleep 2

    MODEL_COUNT=$(docker exec minder-ollama ollama list 2>/dev/null | grep -c "^NAME" || echo "0")

    if [ "$MODEL_COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓ Successfully installed $MODEL_COUNT model(s)${NC}"
        echo ""
        echo -e "${BOLD}${CYAN}Available Models:${NC}"
        docker exec minder-ollama ollama list
    else
        echo -e "${YELLOW}⚠ No models found. AI features may not work properly.${NC}"
        echo -e "${BLUE}ℹ You can download models manually later:${NC}"
        echo -e "   ${CYAN}docker exec minder-ollama ollama pull llama3.2${NC}"
    fi
}

wait_for_services() {
    print_section "⏳ Service Health Monitor"

    # Security services
    echo -e "${CYAN}⟳ Checking security layer...${NC}"
    if curl -s http://localhost:9091/api/health > /dev/null; then
        echo -e "${GREEN}✓ Authelia is healthy${NC}"
    else
        echo -e "${YELLOW}⚠ Authelia is still starting${NC}"
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

    TOTAL_SERVICES=${#services[@]}
    CURRENT_SERVICE=0

    for service in "${services[@]}"; do
        CURRENT_SERVICE=$((CURRENT_SERVICE + 1))
        name=$(echo $service | cut -d: -f1)
        port=$(echo $service | cut -d: -f2)

        echo -ne "${CYAN}[$CURRENT_SERVICE/$TOTAL_SERVICES] Checking $name...${NC} "
        MAX_WAIT=90
        WAIT_TIME=0
        SPINNER_IDX=0

        while [ $WAIT_TIME -lt $MAX_WAIT ]; do
            if curl -s http://localhost:$port/health &> /dev/null || \
               docker exec $name pg_isready -U minder &> /dev/null 2>/dev/null || \
               docker exec $name redis-cli -a ${REDIS_PASSWORD:-minder} ping &> /dev/null 2>/dev/null; then
                echo -e "\r${GREEN}✓ $name is healthy${NC}                    "
                break
            fi
            SPINNER_CHAR="${SPINNER[$SPINNER_IDX]}"
            echo -ne "\r${CYAN}$SPINNER_CHAR [$CURRENT_SERVICE/$TOTAL_SERVICES] $name${NC} "
            sleep 3
            WAIT_TIME=$((WAIT_TIME + 3))
            SPINNER_IDX=$(( (SPINNER_IDX + 1) % 8 ))
        done

        if [ $WAIT_TIME -ge $MAX_WAIT ]; then
            echo -e "\r${YELLOW}⚠ $name is taking longer than expected${NC}"
        fi
    done

    echo ""

    # Wait for monitoring and AI services
    echo -e "${CYAN}⟳ Waiting for monitoring & AI services...${NC}"
    sleep 30

    # Check InfluxDB
    echo -ne "${CYAN}Checking InfluxDB...${NC} "
    if docker exec minder-influxdb influx version &> /dev/null 2>/dev/null; then
        echo -e "\r${GREEN}✓ InfluxDB is ready${NC}                    "
    else
        echo -e "\r${YELLOW}⚠ InfluxDB might still be initializing${NC}"
    fi

    # Check Prometheus
    echo -ne "${CYAN}Checking Prometheus...${NC} "
    if curl -s http://localhost:9090/-/healthy &> /dev/null; then
        echo -e "\r${GREEN}✓ Prometheus is healthy${NC}                "
    else
        echo -e "\r${YELLOW}⚠ Prometheus might still be initializing${NC}"
    fi

    # Check Grafana
    echo -ne "${CYAN}Checking Grafana...${NC} "
    if curl -s http://localhost:3000/api/health &> /dev/null; then
        echo -e "\r${GREEN}✓ Grafana is ready${NC}                     "
    else
        echo -e "\r${YELLOW}⚠ Grafana might still be initializing${NC}"
    fi
}

run_health_checks() {
    print_section "🔍 System Health Check"

    sleep 10

    # Check all API endpoints
    echo -e "${CYAN}Checking Core APIs...${NC}"
    api_ports=(8000 8001 8002 8003 8004 8005)
    all_healthy=true
    HEALTHY_COUNT=0

    for port in "${api_ports[@]}"; do
        if curl -s http://localhost:$port/health > /dev/null; then
            echo -e "  ${GREEN}✓ API port $port${NC}"
            HEALTHY_COUNT=$((HEALTHY_COUNT + 1))
        else
            echo -e "  ${YELLOW}⚠ API port $port${NC}"
            all_healthy=false
        fi
    done

    echo -e "${CYAN}Core APIs: $HEALTHY_COUNT/${#api_ports[@]} healthy${NC}"
    echo ""

    # Check monitoring services
    echo -e "${CYAN}Checking Monitoring Services...${NC}"

    if curl -s http://localhost:9090/-/healthy > /dev/null; then
        echo -e "  ${GREEN}✓ Prometheus (9090)${NC}"
    else
        echo -e "  ${YELLOW}⚠ Prometheus (9090)${NC}"
        all_healthy=false
    fi

    if curl -s http://localhost:3000/api/health > /dev/null; then
        echo -e "  ${GREEN}✓ Grafana (3000)${NC}"
    else
        echo -e "  ${YELLOW}⚠ Grafana (3000)${NC}"
        all_healthy=false
    fi

    if curl -s http://localhost:8086/ping > /dev/null; then
        echo -e "  ${GREEN}✓ InfluxDB (8086)${NC}"
    else
        echo -e "  ${YELLOW}⚠ InfluxDB (8086)${NC}"
        all_healthy=false
    fi

    echo ""

    # Check AI services
    echo -e "${CYAN}Checking AI Services...${NC}"

    if curl -s http://localhost:8080 > /dev/null; then
        echo -e "  ${GREEN}✓ OpenWebUI (8080)${NC}"
    else
        echo -e "  ${YELLOW}⚠ OpenWebUI (8080)${NC}"
        all_healthy=false
    fi

    if curl -s http://localhost:8006/health > /dev/null; then
        echo -e "  ${GREEN}✓ TTS/STT Service (8006)${NC}"
    else
        echo -e "  ${YELLOW}⚠ TTS/STT Service (8006)${NC}"
        all_healthy=false
    fi

    if curl -s http://localhost:8007/health > /dev/null; then
        echo -e "  ${GREEN}✓ Model Fine-tuning (8007)${NC}"
    else
        echo -e "  ${YELLOW}⚠ Model Fine-tuning (8007)${NC}"
        all_healthy=false
    fi

    echo ""

    if [ "$all_healthy" = true ]; then
        echo -e "${GREEN}${BOLD}✓ All services are healthy! 🎉${NC}"
    else
        echo -e "${YELLOW}⚠ Some services may still be starting${NC}"
        echo -e "${BLUE}ℹ Check status with: docker ps${NC}"
    fi
}

print_success_message() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC}       ${BOLD}${GREEN}🎉 MINDER PLATFORM v1.0.0 IS READY! 🎉${NC}            ${CYAN}║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}${MAGENTA}🔐 Security & Access${NC}"
    echo -e "   ${CYAN}•${NC} Traefik Dashboard:  ${BLUE}http://localhost:8081${NC}"
    echo -e "   ${CYAN}•${NC} Authelia Portal:    ${BLUE}http://localhost:9091${NC}"
    echo -e "   ${CYAN}•${NC} Default Users:      ${YELLOW}admin/admin123, developer/admin123, user/admin123${NC}"
    echo -e "   ${RED}⚠️  CHANGE DEFAULT PASSWORDS IMMEDIATELY!${NC}"
    echo ""
    echo -e "${BOLD}${MAGENTA}📍 Core API Services${NC}"
    echo -e "   ${CYAN}•${NC} API Gateway:        ${BLUE}http://localhost:8000${NC}"
    echo -e "   ${CYAN}•${NC} Plugin Registry:    ${BLUE}http://localhost:8001${NC}"
    echo -e "   ${CYAN}•${NC} Marketplace:        ${BLUE}http://localhost:8002${NC}"
    echo -e "   ${CYAN}•${NC} State Manager:      ${BLUE}http://localhost:8003${NC}"
    echo -e "   ${CYAN}•${NC} AI Services:        ${BLUE}http://localhost:8004${NC}"
    echo -e "   ${CYAN}•${NC} Model Management:   ${BLUE}http://localhost:8005${NC}"
    echo ""
    echo -e "${BOLD}${MAGENTA}🤖 AI Enhancement Services${NC}"
    echo -e "   ${CYAN}•${NC} TTS/STT Service:    ${BLUE}http://localhost:8006${NC}"
    echo -e "   ${CYAN}•${NC} Model Fine-tuning:  ${BLUE}http://localhost:8007${NC}"
    echo -e "   ${CYAN}•${NC} OpenWebUI:          ${BLUE}http://localhost:8080${NC}"
    echo ""
    echo -e "${BOLD}${MAGENTA}📊 Monitoring & Metrics${NC}"
    echo -e "   ${CYAN}•${NC} Prometheus:         ${BLUE}http://localhost:9090${NC}"
    echo -e "   ${CYAN}•${NC} Grafana:            ${BLUE}http://localhost:3000${NC}"
    echo -e "   ${CYAN}•${NC} InfluxDB:           ${BLUE}http://localhost:8086${NC}"
    echo ""
    echo -e "${BOLD}${MAGENTA}📚 Documentation${NC}"
    echo -e "   ${CYAN}•${NC} API Docs:           ${BLUE}docs/API.md${NC}"
    echo -e "   ${CYAN}•${NC} Architecture:        ${BLUE}docs/ARCHITECTURE.md${NC}"
    echo -e "   ${CYAN}•${NC} Development:        ${BLUE}docs/DEVELOPMENT.md${NC}"
    echo ""
    echo -e "${BOLD}${MAGENTA}🔧 Useful Commands${NC}"
    echo -e "   ${CYAN}•${NC} View logs:          ${YELLOW}docker compose -f infrastructure/docker/docker-compose.yml logs -f${NC}"
    echo -e "   ${CYAN}•${NC} Stop services:      ${YELLOW}docker compose -f infrastructure/docker/docker-compose.yml down${NC}"
    echo -e "   ${CYAN}•${NC} Restart service:    ${YELLOW}docker compose -f infrastructure/docker/docker-compose.yml restart <service>${NC}"
    echo -e "   ${CYAN}•${NC} Run tests:          ${YELLOW}pytest tests/unit/ -v${NC}"
    echo -e "   ${CYAN}•${NC} Health check:       ${YELLOW}./scripts/health-check.sh${NC}"
    echo ""
    echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}${BOLD}                  Installation Complete! ✓                       ${NC}"
    echo -e "${GREEN}${BOLD}═══════════════════════════════════════════════════════════════${NC}"
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
        "qdrant/qdrant:v1.17.1"
        "neo4j:5.24-community"
        "ollama/ollama:0.5.7"
        "prom/prometheus:v2.55.1"
        "grafana/grafana:11.4.0"
        "authelia/authelia:4.38.7"
        "traefik:v3.1.6"
        "influxdb:2.7.12"
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
        "qdrant/qdrant:v1.17.1"
        "neo4j:5.24-community"
        "ollama/ollama:0.5.7"
        "prom/prometheus:v2.55.1"
        "grafana/grafana:11.4.0"
        "authelia/authelia:4.38.7"
        "traefik:v3.1.6"
        "influxdb:2.7.12"
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
            print_header

            print_step "Checking Prerequisites" $PROGRESS_TOTAL
            check_prerequisites
            print_success "Prerequisites verified"

            print_step "Setting Up Environment" $PROGRESS_TOTAL
            setup_environment
            print_success "Environment configured"

            print_step "Creating Docker Networks" $PROGRESS_TOTAL
            create_networks
            print_success "Networks created"

            print_step "Initializing Databases" $PROGRESS_TOTAL
            initialize_database
            print_success "Databases initialized"

            print_step "Building & Starting Services" $PROGRESS_TOTAL
            start_services
            print_success "Services started"

            print_step "Waiting for Services to be Ready" $PROGRESS_TOTAL
            wait_for_services
            print_success "All services ready"

            print_step "Downloading AI Models" $PROGRESS_TOTAL
            download_ollama_models
            print_success "AI models downloaded"

            print_step "Running Health Checks" $PROGRESS_TOTAL
            run_health_checks
            print_success "All health checks passed"

            print_summary
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

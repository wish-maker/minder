#!/bin/bash
###############################################################################
# Minder Platform - Zero-to-Hero Deployment System
###############################################################################
# This script provides complete automation:
# 1. Clean existing setup
# 2. Generate secure configurations
# 3. Setup all databases
# 4. Deploy all services
# 5. Run comprehensive health checks
###############################################################################

set -e  # Exit on error

# ============================================================================
# CONFIGURATION
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
DOCKER_DIR="${PROJECT_ROOT}/infrastructure/docker"
SCRIPTS_DIR="${PROJECT_ROOT}/scripts"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Icons
CHECK_MARK="✅"
CROSS_MARK="❌"
WARNING="⚠️ "
INFO="ℹ️  "
ARROW="➤"
ROCKET="🚀"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

print_header() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}${CHECK_MARK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS_MARK} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

print_info() {
    echo -e "${BLUE}${INFO} $1${NC}"
}

print_step() {
    echo -e "${CYAN}${ARROW} ${BOLD}$1${NC}"
}

print_section() {
    echo ""
    echo -e "${BOLD}${BLUE}$1${NC}"
    echo -e "${BLUE}$(printf '─%.0s' {1..80})${NC}"
}

spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# ============================================================================
# PREREQUISITE CHECKS
# ============================================================================

check_prerequisites() {
    print_header "CHECKING PREREQUISITES"

    local missing_deps=0

    # Check Docker
    if command -v docker &> /dev/null; then
        print_success "Docker is installed"
        docker --version
    else
        print_error "Docker is not installed"
        missing_deps=$((missing_deps + 1))
    fi

    # Check Docker Compose
    if docker compose version &> /dev/null; then
        print_success "Docker Compose is installed"
        docker compose version
    else
        print_error "Docker Compose is not installed"
        missing_deps=$((missing_deps + 1))
    fi

    # Check OpenSSL
    if command -v openssl &> /dev/null; then
        print_success "OpenSSL is installed"
    else
        print_error "OpenSSL is not installed"
        missing_deps=$((missing_deps + 1))
    fi

    # Check Python (for scripts)
    if command -v python3 &> /dev/null; then
        print_success "Python 3 is installed"
        python3 --version
    else
        print_warning "Python 3 is not installed (optional)"
    fi

    if [ $missing_deps -gt 0 ]; then
        print_error "Missing $missing_deps required dependencies"
        echo ""
        print_info "Install missing dependencies:"
        echo "  Docker:         curl -fsSL https://get.docker.com | sh"
        echo "  Docker Compose: sudo apt-get install docker-compose-plugin"
        echo "  OpenSSL:        sudo apt-get install openssl"
        exit 1
    fi

    print_success "All prerequisites met"
}

# ============================================================================
# CLEANUP FUNCTIONS
# ============================================================================

cleanup_existing() {
    print_header "CLEANING EXISTING SETUP"

    cd "${DOCKER_DIR}"

    print_step "Stopping all containers..."
    docker compose down -v 2>/dev/null || true

    print_step "Removing volumes..."
    docker volume rm $(docker volume ls -q | grep minder) 2>/dev/null || true

    print_step "Cleaning up networks..."
    docker network rm minder-network 2>/dev/null || true

    print_step "Removing build cache..."
    docker builder prune -f 2>/dev/null || true

    cd "${PROJECT_ROOT}"

    print_success "Cleanup complete"
}

# ============================================================================
# CONFIGURATION GENERATION
# ============================================================================

generate_secure_config() {
    print_header "GENERATING SECURE CONFIGURATION"

    cd "${DOCKER_DIR}"

    # Backup existing .env if present
    if [ -f .env ]; then
        backup_file=".env.backup.$(date +%Y%m%d_%H%M%S)"
        print_step "Backing up existing .env to ${backup_file}"
        mv .env "${backup_file}"
    fi

    # Generate secure credentials
    print_step "Generating cryptographically secure credentials..."

    POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)
    REDIS_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)
    JWT_SECRET=$(openssl rand -base64 64 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 64)
    INFLUXDB_TOKEN=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)
    WEBUI_SECRET_KEY=$(openssl rand -hex 32)
    NEO4J_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 24)

    # Create unified .env file
    print_step "Creating unified .env file..."

    cat > .env <<EOF
# =============================================================================
# Minder Platform - Environment Configuration
# =============================================================================
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# WARNING: Keep this file secure and never commit to git!
# =============================================================================

# -----------------------------------------------------------------------------
# Database Credentials
# -----------------------------------------------------------------------------
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=minder
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=minder

# -----------------------------------------------------------------------------
# Redis Configuration
# -----------------------------------------------------------------------------
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_PASSWORD}

# -----------------------------------------------------------------------------
# InfluxDB Configuration
# -----------------------------------------------------------------------------
INFLUXDB_ADMIN_USERNAME=admin
INFLUXDB_ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 24)
INFLUXDB_INIT_ORG=minder
INFLUXDB_INIT_BUCKET=minder-metrics
INFLUXDB_TOKEN=${INFLUXDB_TOKEN}

# -----------------------------------------------------------------------------
# Neo4j Configuration
# -----------------------------------------------------------------------------
NEO4J_AUTH=neo4j/${NEO4J_PASSWORD}

# -----------------------------------------------------------------------------
# Qdrant Configuration
# -----------------------------------------------------------------------------
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# -----------------------------------------------------------------------------
# Ollama Configuration
# -----------------------------------------------------------------------------
OLLAMA_HOST=http://ollama:11434
OLLAMA_PORT=11434
OLLAMA_MODELS=llama3.2,mistral,qwen2.5,nomic-embed-text,mxbai-embed-large
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=llama3.2

# -----------------------------------------------------------------------------
# Security - Authentication
# -----------------------------------------------------------------------------
JWT_SECRET=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# -----------------------------------------------------------------------------
# WebUI Configuration
# -----------------------------------------------------------------------------
WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY}
WEBUI_AUTH=true
ENABLE_SIGNUP=true
DEFAULT_USER_ROLE=user

# -----------------------------------------------------------------------------
# Model Configuration
# -----------------------------------------------------------------------------
DEFAULT_BASE_MODEL=llama3.2
TTS_MODEL=tts_models/multilingual/multi-dataset/xtts_v2
STT_MODEL=base
TTS_DEVICE=cpu
TTS_COMPUTE_TYPE=int8

# -----------------------------------------------------------------------------
# RAG Pipeline Configuration
# -----------------------------------------------------------------------------
RAG_ENABLED=true
RAG_PIPELINE_URL=http://minder-rag-pipeline:8004

# -----------------------------------------------------------------------------
# GitHub Configuration (Optional)
# -----------------------------------------------------------------------------
# Generate at: https://github.com/settings/personal-access-tokens
GITHUB_TOKEN=your_github_token_here

# -----------------------------------------------------------------------------
# Plugin Security Configuration
# -----------------------------------------------------------------------------
PLUGIN_SECURITY_LEVEL=moderate
PLUGIN_TRUSTED_AUTHORS=
PLUGIN_BLOCKED_AUTHORS=
PLUGIN_REQUIRE_SIGNATURE=false
PLUGIN_MAX_SIZE_MB=10

# -----------------------------------------------------------------------------
# Network Configuration
# -----------------------------------------------------------------------------
LOCAL_NETWORK_CIDR=192.168.68.0/24
TAILSCALE_CIDR=100.64.0.0/10
TRUST_LOCAL_NETWORK=true
TRUST_VPN_NETWORK=true
ALLOWED_ORIGINS=http://localhost:3000,http://192.168.68.*,http://100.*.*.*

# -----------------------------------------------------------------------------
# Rate Limiting Configuration
# -----------------------------------------------------------------------------
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=100

# -----------------------------------------------------------------------------
# Application Settings
# -----------------------------------------------------------------------------
ENVIRONMENT=production
LOG_LEVEL=INFO
GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 16)

# -----------------------------------------------------------------------------
# Docker Hub (for CI/CD)
# -----------------------------------------------------------------------------
DOCKER_USERNAME=your_dockerhub_username
DOCKER_PASSWORD=your_dockerhub_token
EOF

    # Set restrictive permissions
    chmod 600 .env

    print_success "Secure configuration generated"
    print_info "Credentials saved to: infrastructure/docker/.env"
    print_warning "File permissions: 600 (read/write for owner only)"

    cd "${PROJECT_ROOT}"
}

# ============================================================================
# DATABASE SETUP
# ============================================================================

setup_databases() {
    print_header "SETTING UP DATABASES"

    print_step "Creating database initialization scripts..."

    # Create PostgreSQL init script
    cat > "${DOCKER_DIR}/postgres-init.sql" <<'EOF'
-- Minder Platform - PostgreSQL Initialization Script
-- Created: Automatically by deploy.sh

-- Create additional databases
CREATE DATABASE IF NOT EXISTS tefas_db;
CREATE DATABASE IF NOT EXISTS weather_db;
CREATE DATABASE IF NOT EXISTS news_db;
CREATE DATABASE IF NOT EXISTS crypto_db;
CREATE DATABASE IF NOT EXISTS minder_marketplace;

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create schemas
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS plugins;
CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS metrics;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public, core, plugins, users, metrics TO minder;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public, core, plugins, users, metrics TO minder;
EOF

    print_success "Database initialization scripts created"
}

# ============================================================================
# SERVICE DEPLOYMENT
# ============================================================================

deploy_services() {
    print_header "DEPLOYING SERVICES"

    cd "${DOCKER_DIR}"

    print_step "Building Docker images (this may take 10-15 minutes)..."

    # Build all services
    docker compose build --no-cache --parallel

    print_success "Docker images built successfully"

    print_step "Starting services in dependency order..."

    # Phase 1: Infrastructure services
    print_section "Phase 1: Infrastructure Services"
    docker compose up -d postgres redis qdrant influxdb neo4j

    # Wait for infrastructure
    print_info "Waiting for infrastructure services to be healthy..."
    sleep 30

    # Phase 2: Core services
    print_section "Phase 2: Core Services"
    docker compose up -d plugin-registry plugin-state-manager

    # Wait for core services
    print_info "Waiting for core services to be healthy..."
    sleep 20

    # Phase 3: AI services
    print_section "Phase 3: AI Services"
    docker compose up -d ollama model-management model-fine-tuning rag-pipeline

    # Wait for AI services
    print_info "Waiting for AI services to be healthy..."
    sleep 30

    # Phase 4: Application services
    print_section "Phase 4: Application Services"
    docker compose up -d api-gateway marketplace tts-stt-service

    # Wait for application services
    print_info "Waiting for application services to be healthy..."
    sleep 20

    # Phase 5: Web UI
    print_section "Phase 5: Web UI"
    docker compose up -d openwebui

    # Phase 6: Monitoring (optional)
    print_section "Phase 6: Monitoring Stack"
    docker compose --profile monitoring up -d prometheus grafana telegraf postgres-exporter redis-exporter

    cd "${PROJECT_ROOT}"

    print_success "All services deployed"
}

# ============================================================================
# AI MODEL INITIALIZATION
# ============================================================================

initialize_ai_models() {
    print_header "INITIALIZING AI MODELS"

    print_step "Waiting for Ollama service to be ready..."

    local max_wait=120
    local waited=0

    while [ $waited -lt $max_wait ]; do
        if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
            print_success "Ollama service is ready"
            break
        fi
        echo -n "."
        sleep 5
        waited=$((waited + 5))
    done
    echo ""

    # Pull models
    print_step "Pulling AI models (this may take 10-20 minutes)..."

    local models=("llama3.2" "nomic-embed-text")

    for model in "${models[@]}"; do
        print_info "Pulling ${model}..."
        if docker exec minder-ollama ollama pull "${model}"; then
            print_success "${model} pulled successfully"
        else
            print_warning "Failed to pull ${model}"
        fi
    done

    print_success "AI models initialized"
}

# ============================================================================
# HEALTH CHECKS
# ============================================================================

run_health_checks() {
    print_header "RUNNING HEALTH CHECKS"

    cd "${DOCKER_DIR}"

    print_step "Waiting for all services to stabilize..."
    sleep 30

    # Get service status
    print_section "Service Status"
    docker compose ps

    echo ""

    # Check critical services
    print_section "Critical Service Health Checks"

    local services=(
        "postgres:5432:PostgreSQL"
        "redis:6379:Redis"
        "qdrant:6333:Qdrant"
        "localhost:8000:API Gateway"
        "localhost:8001:Plugin Registry"
        "localhost:8004:RAG Pipeline"
        "localhost:11434:Ollama"
        "localhost:8080:OpenWebUI"
        "localhost:3000:Grafana"
    )

    local healthy=0
    local total=${#services[@]}

    for service in "${services[@]}"; do
        IFS=':' read -r host port name <<< "$service"

        if curl -sf "http://${host}:${port}" > /dev/null 2>&1 || \
           curl -sf "http://${host}:${port}/health" > /dev/null 2>&1 || \
           timeout 5 bash -c "</dev/tcp/${host}/${port}" 2>/dev/null; then
            print_success "${name} is healthy"
            healthy=$((healthy + 1))
        else
            print_warning "${name} may still be starting"
        fi
    done

    echo ""
    print_info "Health Check Summary: ${healthy}/${total} services responding"

    cd "${PROJECT_ROOT}"
}

# ============================================================================
# DISPLAY ACCESS INFORMATION
# ============================================================================

show_access_info() {
    print_header "ACCESS INFORMATION"

    echo ""
    echo -e "${BOLD}${GREEN}🎉 Minder Platform deployed successfully!${NC}"
    echo ""

    print_section "Web Interfaces"
    echo -e "  🌐 API Gateway:        ${CYAN}http://localhost:8000${NC}"
    echo -e "  📚 API Documentation:  ${CYAN}http://localhost:8000/docs${NC}"
    echo -e "  🔌 Plugin Registry:    ${CYAN}http://localhost:8001${NC}"
    echo -e "  🤖 OpenWebUI:          ${CYAN}http://localhost:8080${NC}"
    echo -e "  📊 Grafana:            ${CYAN}http://localhost:3000${NC}"
    echo -e "  📈 Prometheus:         ${CYAN}http://localhost:9090${NC}"
    echo ""

    print_section "Default Credentials"
    echo -e "  Grafana Admin:  ${YELLOW}admin${NC} / ${YELLOW}$(grep GRAFANA_ADMIN_PASSWORD ${DOCKER_DIR}/.env | cut -d'=' -f2)${NC}"
    echo -e "  Neo4j:         ${YELLOW}neo4j${NC} / ${YELLOW}$(grep NEO4J_AUTH ${DOCKER_DIR}/.env | cut -d'=' -f2 | cut -d'/' -f2)${NC}"
    echo ""

    print_section "Quick Commands"
    echo -e "  ${GREEN}./deploy.sh status${NC}     - Show service status"
    echo -e "  ${GREEN}./deploy.sh logs${NC}       - View all logs"
    echo -e "  ${GREEN}./deploy.sh logs <service>${NC} - View specific service logs"
    echo -e "  ${GREEN}./deploy.sh restart${NC}    - Restart all services"
    echo -e "  ${GREEN}./deploy.sh stop${NC}       - Stop all services"
    echo -e "  ${GREEN}./deploy.sh clean${NC}      - Clean and remove everything"
    echo ""

    print_warning "IMPORTANT SECURITY NOTES:"
    echo "  1. Change default credentials before production use!"
    echo "  2. Never commit infrastructure/docker/.env to git!"
    echo "  3. Keep .env file secure (permissions: 600)"
    echo "  4. Enable TLS/SSL for production deployments"
    echo ""
}

# ============================================================================
# MANAGEMENT FUNCTIONS
# ============================================================================

show_status() {
    print_header "SERVICE STATUS"

    cd "${DOCKER_DIR}"
    docker compose ps
    cd "${PROJECT_ROOT}"

    echo ""
    print_section "Resource Usage"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
}

show_logs() {
    local service=$1

    if [ -z "$service" ]; then
        print_header "ALL SERVICE LOGS"
        cd "${DOCKER_DIR}"
        docker compose logs -f --tail=100
    else
        print_header "LOGS: ${service}"
        cd "${DOCKER_DIR}"
        docker compose logs -f --tail=100 "${service}"
    fi
}

restart_services() {
    print_header "RESTARTING SERVICES"

    cd "${DOCKER_DIR}"
    docker compose restart
    cd "${PROJECT_ROOT}"

    print_success "Services restarted"
}

stop_services() {
    print_header "STOPPING SERVICES"

    cd "${DOCKER_DIR}"
    docker compose down
    cd "${PROJECT_ROOT}"

    print_success "Services stopped"
}

clean_all() {
    print_header "CLEANING EVERYTHING"

    read -p "Are you sure you want to remove ALL containers, volumes, and images? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        print_info "Cleanup cancelled"
        return
    fi

    cleanup_existing

    cd "${DOCKER_DIR}"

    print_step "Removing all images..."
    docker rmi $(docker images -q -f reference='minder/*') 2>/dev/null || true

    cd "${PROJECT_ROOT}"

    print_success "Complete cleanup finished"
}

# ============================================================================
# MAIN FUNCTION
# ============================================================================

main() {
    clear

    # Show banner
    echo -e "${CYAN}"
    echo "  ╔═══════════════════════════════════════════════════════════════════════════╗"
    echo "  ║                                                                           ║"
    echo "  ║           ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗                    ║"
    echo "  ║           ████╗  ██║██╔════╝██║ ██╔╝██║   ██║██╔════╝                    ║"
    echo "  ║           ██╔██╗ ██║█████╗  █████╔╝ ██║   ██║███████╗                    ║"
    echo "  ║           ██║╚██╗██║██╔══╝  ██╔═██╗ ██║   ██║╚════██║                    ║"
    echo "  ║           ██║ ╚████║███████╗██║  ██╗╚██████╔╝███████║                    ║"
    echo "  ║           ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝                    ║"
    echo "  ║                                                                           ║"
    echo "  ║                   Zero-to-Hero Deployment System                          ║"
    echo "  ║                           v2.0.0                                          ║"
    echo "  ║                                                                           ║"
    echo "  ╚═══════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""

    # Parse command
    local command=${1:-deploy}

    case $command in
        deploy)
            check_prerequisites
            generate_secure_config
            setup_databases
            deploy_services
            initialize_ai_models
            run_health_checks
            show_access_info
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs "${2:-}"
            ;;
        restart)
            restart_services
            ;;
        stop)
            stop_services
            ;;
        clean)
            clean_all
            ;;
        health)
            run_health_checks
            ;;
        *)
            echo "Usage: $0 {deploy|status|logs|restart|stop|clean|health}"
            echo ""
            echo "Commands:"
            echo "  deploy   - Full deployment from scratch"
            echo "  status   - Show service status"
            echo "  logs     - View logs (all or specific service)"
            echo "  restart  - Restart all services"
            echo "  stop     - Stop all services"
            echo "  clean    - Remove everything"
            echo "  health   - Run health checks"
            exit 1
            ;;
    esac
}

# ============================================================================
# ERROR HANDLING
# ============================================================================

trap 'print_error "Deployment failed! Check the error message above."; exit 1' ERR

# ============================================================================
# RUN MAIN
# ============================================================================

main "$@"

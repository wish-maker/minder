#!/bin/bash
###############################################################################
# Minder Platform - One-Click Installation Script
###############################################################################
# This script automates the entire setup process:
# 1. Generate secure credentials
# 2. Configure environment
# 3. Start all services
# 4. Verify deployment
# 5. Run health checks
###############################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if Docker is installed
check_docker() {
    print_header "Checking Prerequisites"

    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed!"
        echo "Please install Docker first:"
        echo "  - Ubuntu/Debian: curl -fsSL https://get.docker.com | sh"
        echo "  - Or visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    print_success "Docker is installed"

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_error "Docker Compose is not installed!"
        echo "Please install Docker Compose first:"
        echo "  - Ubuntu/Debian: sudo apt-get install docker-compose-plugin"
        echo "  - Or visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    print_success "Docker Compose is installed"
}

# Generate secure credentials
generate_credentials() {
    print_header "Generating Secure Credentials"

    cd infrastructure/docker

    # Check if openssl is available
    if ! command -v openssl &> /dev/null; then
        print_error "openssl is required but not installed!"
        echo "Install with: sudo apt-get install openssl"
        exit 1
    fi

    # Check if .env already exists
    if [ -f .env ]; then
        print_warning ".env file already exists!"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Keeping existing .env file"
            cd ../..
            return
        fi
        mv .env .env.backup.$(date +%Y%m%d_%H%M%S)
        print_info "Backed up existing .env file"
    fi

    print_info "Generating cryptographically secure credentials..."

    # Generate PostgreSQL password (32 chars)
    POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)

    # Generate Redis password (32 chars)
    REDIS_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)

    # Generate JWT secret (64 chars)
    JWT_SECRET=$(openssl rand -base64 64 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 64)

    # Generate InfluxDB token (32 chars)
    INFLUXDB_TOKEN=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)

    # Create .env file
    cat > .env <<EOF
# Minder Platform - Environment Configuration
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# WARNING: Keep this file secure and never commit to git!

POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
JWT_SECRET=${JWT_SECRET}
INFLUXDB_TOKEN=${INFLUXDB_TOKEN}
ENVIRONMENT=production
LOG_LEVEL=INFO
ADMIN_USERS=admin
EOF

    # Set restrictive permissions
    chmod 600 .env

    cd ../..

    print_success "Secure credentials generated"
    print_info "Credentials saved to: infrastructure/docker/.env"
}

# Start services
start_services() {
    print_header "Starting Minder Platform"

    cd infrastructure/docker

    # Stop any existing services
    print_info "Stopping any existing services..."
    docker compose down 2>/dev/null || true

    # Start services
    print_info "Starting all services (this may take a few minutes)..."
    docker compose up -d

    cd ../..

    print_success "Services started"
}

# Initialize AI Model
initialize_ai_model() {
    print_header "Initializing AI Model"

    print_info "Waiting for Ollama service to be ready..."
    local max_wait=60
    local waited=0

    while [ $waited -lt $max_wait ]; do
        if curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
            break
        fi
        echo -n "."
        sleep 5
        waited=$((waited + 5))
    done
    echo ""

    # Check if models already exist
    print_info "Checking for existing models..."
    if curl -sf http://localhost:11434/api/tags 2>/dev/null | grep -q "llama3.2"; then
        print_success "Llama 3.2 model already exists"
        return 0
    fi

    # Pull llama3.2 model
    print_info "Pulling Llama 3.2 model (this may take 5-10 minutes)..."
    if docker exec minder-ollama ollama pull llama3.2 2>&1 | tail -5; then
        print_success "Model pulled successfully"
    else
        print_error "Failed to pull model"
        return 1
    fi

    # Run the model
    print_info "Starting Llama 3.2 model in background..."
    docker exec minder-ollama ollama run llama3.2 &

    # Wait for model to be ready
    print_info "Waiting for model to initialize..."
    sleep 10

    # Verify model is running
    if curl -sf http://localhost:11434/api/tags 2>/dev/null | grep -q "llama3.2"; then
        print_success "AI Model (Llama 3.2) is ready!"
    else
        print_warning "Model may still be initializing. Check with:"
        echo "  curl http://localhost:11434/api/tags"
    fi
}

# Wait for services to be healthy
wait_for_services() {
    print_header "Waiting for Services to be Healthy"

    local max_wait=300  # 5 minutes
    local waited=0
    local interval=10

    print_info "Waiting for services to initialize (max ${max_wait}s)..."

    while [ $waited -lt $max_wait ]; do
        # Check if all services are healthy
        healthy_count=$(docker compose -f infrastructure/docker/docker-compose.yml ps \
            | grep -c "healthy" || true)

        total_services=$(docker compose -f infrastructure/docker/docker-compose.yml ps \
            | grep -c "Up" || true)

        if [ $healthy_count -ge 15 ]; then
            print_success "All services are healthy!"
            return 0
        fi

        echo -n "."
        sleep $interval
        waited=$((waited + interval))
    done

    echo ""
    print_warning "Some services may still be initializing..."
    print_info "Run 'docker compose ps' to check status"
}

# Verify deployment
verify_deployment() {
    print_header "Verifying Deployment"

    cd infrastructure/docker

    # Get service status
    print_info "Service Status:"
    echo ""
    docker compose ps
    echo ""

    # Check for unhealthy services
    unhealthy=$(docker compose ps | grep -v "healthy" | grep "Up" || true)

    if [ -n "$unhealthy" ]; then
        print_warning "Some services are not yet healthy:"
        echo "$unhealthy"
        echo ""
        print_info "This is normal during first startup. Services will become healthy shortly."
        print_info "Monitor with: docker compose ps"
    else
        print_success "All services are healthy!"
    fi

    cd ../..
}

# Display access information
show_access_info() {
    print_header "Access Information"

    echo ""
    echo "🌐 Minder Platform is now running!"
    echo ""
    echo -e "${GREEN}Web Interfaces:${NC}"
    echo "  • API Gateway:        http://localhost:8000"
    echo "  • API Documentation:  http://localhost:8000/docs"
    echo "  • Plugin Registry:    http://localhost:8001"
    echo "  • Grafana:           http://localhost:3000"
    echo "  • Prometheus:        http://localhost:9090"
    echo ""
    echo -e "${GREEN}Default Credentials:${NC}"
    echo "  • Username: admin"
    echo "  • Password: (anything 8+ characters for testing)"
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANT:${NC}"
    echo "  1. Change default credentials before production use!"
    echo "  2. Never commit infrastructure/docker/.env to git!"
    echo "  3. Keep .env file secure (permissions: 600)"
    echo ""
    echo -e "${GREEN}Useful Commands:${NC}"
    echo "  • View logs:          docker compose -f infrastructure/docker/docker-compose.yml logs -f [service]"
    echo "  • Stop all:           docker compose -f infrastructure/docker/docker-compose.yml down"
    echo "  • Restart:            docker compose -f infrastructure/docker/docker-compose.yml restart"
    echo "  • Check status:       docker compose -f infrastructure/docker/docker-compose.yml ps"
    echo ""
}

# Run health checks
run_health_checks() {
    print_header "Running Health Checks"

    # Check API Gateway
    print_info "Checking API Gateway..."
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        print_success "API Gateway is responding"
    else
        print_warning "API Gateway not yet responding (may still be starting)"
    fi

    # Check Plugin Registry
    print_info "Checking Plugin Registry..."
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        print_success "Plugin Registry is responding"
    else
        print_warning "Plugin Registry not yet responding (may still be starting)"
    fi

    echo ""
    print_info "For detailed health status, run:"
    echo "  curl http://localhost:8000/health"
    echo "  curl http://localhost:8001/health"
}

# Main installation flow
main() {
    clear

    echo -e "${BLUE}"
    echo "  ╔═══════════════════════════════════════════════════════════════════════════╗"
    echo "  ║                                                                           ║"
    echo "  ║           ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗                    ║"
    echo "  ║           ████╗  ██║██╔════╝██║ ██╔╝██║   ██║██╔════╝                    ║"
    echo "  ║           ██╔██╗ ██║█████╗  █████╔╝ ██║   ██║███████╗                    ║"
    echo "  ║           ██║╚██╗██║██╔══╝  ██╔═██╗ ██║   ██║╚════██║                    ║"
    echo "  ║           ██║ ╚████║███████╗██║  ██╗╚██████╔╝███████║                    ║"
    echo "  ║           ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝                    ║"
    echo "  ║                                                                           ║"
    echo "  ║                   One-Click Installation Script                          ║"
    echo "  ║                           v2.0.0                                          ║"
    echo "  ║                                                                           ║"
    echo "  ╚═══════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""

    # Installation steps
    check_docker
    generate_credentials
    start_services
    initialize_ai_model
    wait_for_services
    verify_deployment
    run_health_checks
    show_access_info

    # Final message
    print_header "Installation Complete!"

    echo -e "${GREEN}"
    echo "  ┌─────────────────────────────────────────────────────────────────┐"
    echo "  │                                                                 │"
    echo "  │  ✅  Minder Platform installed successfully!                   │"
    echo "  │                                                                 │"
    echo "  │  Next steps:                                                    │"
    echo "  │  1. Open http://localhost:8000/docs in your browser            │"
    echo "  │  2. Login with username: admin                                 │"
    echo "  │  3. Explore the API and plugins                                │"
    echo "  │                                                                 │"
    echo "  └─────────────────────────────────────────────────────────────────┘"
    echo -e "${NC}"
    echo ""

    # Create quick-start script
    cat > start.sh <<'EOF'
#!/bin/bash
# Quick start script for Minder Platform

cd infrastructure/docker
docker compose up -d
echo "✅ Minder Platform starting..."
echo "Open http://localhost:8000/docs in your browser"
EOF
    chmod +x start.sh
    print_info "Created 'start.sh' for quick startup next time"

    # Create stop script
    cat > stop.sh <<'EOF'
#!/bin/bash
# Stop script for Minder Platform

cd infrastructure/docker
docker compose down
echo "✅ Minder Platform stopped"
EOF
    chmod +x stop.sh
    print_info "Created 'stop.sh' for quick stop"

    echo ""
    print_info "For troubleshooting, check logs:"
    echo "  docker compose -f infrastructure/docker/docker-compose.yml logs -f"
}

# Handle errors
trap 'print_error "Installation failed! Check the error message above."; exit 1' ERR

# Run main function
main "$@"

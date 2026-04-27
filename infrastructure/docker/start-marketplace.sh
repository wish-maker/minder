#!/bin/bash
# Minder Marketplace Service Management Script
# Usage: ./start-marketplace.sh [command]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.marketplace.yml"
SERVICE_NAME="marketplace"
HEALTH_URL="http://localhost:8002/health"

# Functions
print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  Minder Plugin Marketplace${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
}

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi

    print_status "Docker is running"
}

check_services() {
    echo -e "\n${BLUE}Checking service status...${NC}"

    # Check if core services are running
    local services=("minder-postgres" "minder-redis" "minder-plugin-registry" "minder-marketplace")
    local all_running=true

    for service in "${services[@]}"; do
        if docker ps --filter "name=$service" --format "{{.Names}}" | grep -q "$service"; then
            local status=$(docker inspect "$service" --format='{{.State.Health.Status}}' 2>/dev/null || echo "running")
            if [ "$status" == "healthy" ] || [ "$status" == "running" ]; then
                print_status "$service is $status"
            else
                print_warning "$service is $status"
                all_running=false
            fi
        else
            print_error "$service is not running"
            all_running=false
        fi
    done

    if [ "$all_running" = false ]; then
        return 1
    fi

    return 0
}

start_services() {
    print_header
    echo "Starting Minder Marketplace services..."
    echo ""

    cd "$(dirname "$0")"

    # Start services
    docker compose $COMPOSE_FILES up -d $SERVICE_NAME

    echo ""
    echo -e "${BLUE}Waiting for services to be healthy...${NC}"

    # Wait for marketplace to be healthy (max 30 seconds)
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            echo ""
            print_status "All services are healthy!"
            break
        fi

        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done

    if [ $attempt -eq $max_attempts ]; then
        echo ""
        print_error "Services failed to become healthy"
        return 1
    fi

    echo ""
    show_info
}

stop_services() {
    print_header
    echo "Stopping Minder Marketplace services..."
    echo ""

    cd "$(dirname "$0")"

    docker compose $COMPOSE_FILES down $SERVICE_NAME

    print_status "Services stopped"
}

restart_services() {
    stop_services
    sleep 2
    start_services
}

show_logs() {
    local service=${1:-"minder-marketplace"}
    echo -e "${BLUE}Showing logs for $service...${NC}"
    echo ""
    docker logs -f "$service" --tail 100
}

show_info() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  Service Information${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
    echo -e "📊 ${GREEN}Marketplace API:${NC}     http://localhost:8002"
    echo -e "📚 ${GREEN}API Documentation:${NC}  http://localhost:8002/docs"
    echo -e "🏥 ${GREEN}Health Check:${NC}       http://localhost:8002/health"
    echo ""
    echo -e "🔌 ${GREEN}API Gateway:${NC}        http://localhost:8000"
    echo -e "📦 ${GREEN}Plugin Registry:${NC}    http://localhost:8001"
    echo ""
    echo -e "🗄️  ${GREEN}Database:${NC}           postgres://localhost:5432/minder_marketplace"
    echo -e "📋 ${GREEN}Redis:${NC}               redis://localhost:6379"
    echo ""
    echo -e "${BLUE}================================${NC}"
    echo ""
}

test_api() {
    print_header
    echo "Testing Marketplace API..."
    echo ""

    # Test health endpoint
    echo "1. Testing health endpoint..."
    if curl -sf "$HEALTH_URL" | python3 -m json.tool > /dev/null 2>&1; then
        print_status "Health check passed"
    else
        print_error "Health check failed"
        return 1
    fi

    # Test plugins endpoint
    echo "2. Testing plugins endpoint..."
    if curl -sf "http://localhost:8002/v1/marketplace/plugins" | python3 -m json.tool > /dev/null 2>&1; then
        print_status "Plugins endpoint works"
    else
        print_error "Plugins endpoint failed"
        return 1
    fi

    # Test license activation
    echo "3. Testing license activation..."
    local response=$(curl -s -X POST "http://localhost:8002/v1/marketplace/licenses/activate" \
        -H "Content-Type: application/json" \
        -d '{
            "user_id": "00000000-0000-0000-0000-000000000001",
            "plugin_id": "550e8400-e29b-41d4-a716-446655440002",
            "tier": "community"
        }')

    if echo "$response" | python3 -m json.tool > /dev/null 2>&1; then
        print_status "License activation works"
    else
        print_error "License activation failed"
        return 1
    fi

    echo ""
    print_status "All API tests passed!"
    return 0
}

show_help() {
    print_header
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start     Start marketplace services"
    echo "  stop      Stop marketplace services"
    echo "  restart   Restart marketplace services"
    echo "  status    Show service status"
    echo "  logs      Show service logs (default: minder-marketplace)"
    echo "  test      Test API endpoints"
    echo "  info      Show service information"
    echo "  help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start              # Start services"
    echo "  $0 logs               # Show marketplace logs"
    echo "  $0 logs plugin-registry  # Show plugin registry logs"
    echo "  $0 test              # Run API tests"
    echo ""
}

# Main script logic
main() {
    local command=${1:-"help"}

    case "$command" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            check_services
            ;;
        logs)
            show_logs "${2:-minder-marketplace}"
            ;;
        test)
            test_api
            ;;
        info)
            show_info
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"

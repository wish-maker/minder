#!/bin/bash
###############################################################################
# Minder Platform - Comprehensive Health Check System
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
DOCKER_DIR="../infrastructure/docker"
TIMEOUT=5

# Utility functions
print_header() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}${BLUE}  $1${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
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

# Check service health
check_service() {
    local name=$1
    local host=$2
    local port=$3
    local path=${4:-/}

    if curl -sf --max-time $TIMEOUT "http://${host}:${port}${path}" > /dev/null 2>&1; then
        print_success "${name}"
        return 0
    elif curl -sf --max-time $TIMEOUT "http://${host}:${port}/health" > /dev/null 2>&1; then
        print_success "${name}"
        return 0
    elif timeout $TIMEOUT bash -c "</dev/tcp/${host}/${port}" 2>/dev/null; then
        print_success "${name}"
        return 0
    else
        print_error "${name} - Connection failed"
        return 1
    fi
}

# Check Docker container health
check_container_health() {
    local container=$1
    local health=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null)

    if [ "$health" = "healthy" ]; then
        print_success "${container}"
        return 0
    elif [ "$health" = "starting" ]; then
        print_warning "${container} - Starting"
        return 1
    else
        print_error "${container} - Unhealthy or not running"
        return 1
    fi
}

# Main health check
main() {
    clear
    print_header "MINDER PLATFORM - COMPREHENSIVE HEALTH CHECK"

    cd "$DOCKER_DIR"

    local total=0
    local passed=0
    local failed=0

    # Infrastructure Services
    print_header "INFRASTRUCTURE SERVICES"

    check_container_health "minder-postgres" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-redis" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-qdrant" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-influxdb" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-neo4j" && ((passed++)) or ((failed++))
    ((total++))

    # AI Services
    print_header "AI SERVICES"

    check_container_health "minder-ollama" && ((passed++)) || ((failed++))
    ((total++))

    check_service "Ollama API" "localhost" "11434" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-rag-pipeline" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-model-management" && ((passed++)) || ((failed++))
    ((total++))

    # Core Services
    print_header "CORE SERVICES"

    check_container_health "minder-api-gateway" && ((passed++)) || ((failed++))
    ((total++))

    check_service "API Gateway" "localhost" "8000" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-plugin-registry" && ((passed++)) || ((failed++))
    ((total++))

    check_service "Plugin Registry" "localhost" "8001" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-plugin-state-manager" && ((passed++)) || ((failed++))
    ((total++))

    # Web Interfaces
    print_header "WEB INTERFACES"

    check_container_health "minder-openwebui" && ((passed++)) || ((failed++))
    ((total++))

    check_service "OpenWebUI" "localhost" "8080" && ((passed++)) || ((failed++))
    ((total++))

    check_container_health "minder-grafana" && ((passed++)) || ((failed++))
    ((total++))

    check_service "Grafana" "localhost" "3000" && ((passed++)) || ((failed++))
    ((total++))

    # Summary
    print_header "HEALTH CHECK SUMMARY"

    echo -e "Total Checks:  ${BOLD}${total}${NC}"
    echo -e "Passed:        ${GREEN}${passed}${NC}"
    echo -e "Failed:        ${RED}${failed}${NC}"

    local percentage=$((passed * 100 / total))
    echo ""
    echo -e "Health Score:  ${BOLD}${percentage}%${NC}"

    if [ $percentage -ge 80 ]; then
        print_success "System is healthy!"
        return 0
    elif [ $percentage -ge 50 ]; then
        print_warning "System has issues but is operational"
        return 1
    else
        print_error "System has critical failures!"
        return 2
    fi
}

main "$@"

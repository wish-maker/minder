#!/bin/bash

################################################################################
# Minder Platform - Automated Health Check Script
################################################################################
# Description: Comprehensive health monitoring for all Minder services
# Usage: ./scripts/health-check.sh [options]
# Options:
#   --fix     Automatically restart unhealthy services
#   --report  Generate detailed health report
#   --watch   Continuously monitor services (update every 30s)
################################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="/root/minder/docker/compose/docker-compose.yml"
REPORT_DIR="/root/minder/health-reports"
LOG_FILE="/root/minder/logs/health-check.log"

# Ensure directories exist
mkdir -p "$REPORT_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

# Timestamp function
timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Log function
log() {
    echo "[$(timestamp)] $1" | tee -a "$LOG_FILE"
}

# Count services by status
count_services() {
    local status=$1
    docker ps -a --filter "status=$status" --format "{{.Names}}" | wc -l
}

# Get service health status
get_service_status() {
    local service_name=$1
    docker ps -a --filter "name=$service_name" --format "{{.Status}}"
}

# Check if service is healthy
is_healthy() {
    local service_name=$1
    local status=$(get_service_status "$service_name")
    [[ "$status" =~ "healthy" ]] && return 0 || return 1
}

# Get unhealthy services
get_unhealthy_services() {
    docker ps -a --filter "health=unhealthy" --format "{{.Names}}"
}

# Get stopped services
get_stopped_services() {
    docker ps -a --filter "status=exited" --format "{{.Names}}"
}

# Restart service
restart_service() {
    local service_name=$1
    log "Restarting service: $service_name"
    cd /root/minder/docker/compose
    docker compose restart "$service_name" 2>&1 | tee -a "$LOG_FILE"

    # Wait for service to restart
    sleep 10

    # Check if service is now healthy
    if is_healthy "$service_name"; then
        log "${GREEN}✓ Service $service_name restarted successfully${NC}"
        return 0
    else
        log "${RED}✗ Service $service_name failed to restart${NC}"
        return 1
    fi
}

# Generate health report
generate_report() {
    local report_file="$REPORT_DIR/health-report-$(date +%Y%m%d-%H%M%S).txt"

    log "Generating health report: $report_file"

    {
        echo "=========================================="
        echo "  MINDER PLATFORM HEALTH REPORT"
        echo "=========================================="
        echo "Generated: $(timestamp)"
        echo ""

        # System overview
        echo "=== SYSTEM OVERVIEW ==="
        local total=$(docker ps -a --format "{{.Names}}" | wc -l)
        local running=$(count_services "running")
        local healthy=$(docker ps -a --filter "health=healthy" --format "{{.Names}}" | wc -l)
        local unhealthy=$(docker ps -a --filter "health=unhealthy" --format "{{.Names}}" | wc -l)
        local stopped=$(count_services "exited")

        echo "Total Services: $total"
        echo "Running: $running"
        echo "Healthy: $healthy"
        echo "Unhealthy: $unhealthy"
        echo "Stopped: $stopped"
        echo ""

        # Calculate health percentage
        local health_percentage=$((healthy * 100 / total))
        echo "Overall Health: ${health_percentage}%"
        echo ""

        # Service status by category
        echo "=== SERVICE STATUS BY CATEGORY ==="
        echo ""

        echo "--- Core Infrastructure ---"
        for service in postgres redis rabbitmq traefik authelia; do
            local status=$(get_service_status "minder-$service")
            local indicator="✓"
            [[ ! "$status" =~ "healthy" ]] && indicator="✗"
            echo "$indicator $service: $status"
        done
        echo ""

        echo "--- Core API Services ---"
        for service in api-gateway plugin-registry marketplace plugin-state-manager model-management; do
            local status=$(get_service_status "minder-$service")
            local indicator="✓"
            [[ ! "$status" =~ "healthy" ]] && indicator="✗"
            echo "$indicator $service: $status"
        done
        echo ""

        echo "--- Data & AI Services ---"
        for service in neo4j qdrant ollama openwebui rag-pipeline; do
            local status=$(get_service_status "minder-$service")
            local indicator="✓"
            [[ ! "$status" =~ "healthy" ]] && indicator="✗"
            echo "$indicator $service: $status"
        done
        echo ""

        echo "--- Monitoring Stack ---"
        for service in prometheus grafana jaeger alertmanager telegraf influxdb otel-collector; do
            local status=$(get_service_status "minder-$service")
            local indicator="✓"
            [[ ! "$status" =~ "healthy" ]] && indicator="✗"
            echo "$indicator $service: $status"
        done
        echo ""

        # Unhealthy services details
        if [ $unhealthy -gt 0 ]; then
            echo "=== UNHEALTHY SERVICES DETAILS ==="
            echo ""
            get_unhealthy_services | while read service; do
                echo "Service: $service"
                echo "Status: $(get_service_status "$service")"
                echo "Recent Logs:"
                docker logs --tail 10 "$service" 2>&1 | grep -i "error\|fail\|critical" || echo "No critical errors found"
                echo ""
            done
        fi

        # Resource usage
        echo "=== RESOURCE USAGE ==="
        echo ""
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
        echo ""

        # System resources
        echo "=== SYSTEM RESOURCES ==="
        echo ""
        echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)%"
        echo "Memory Usage: $(free -h | awk '/Mem:/ {print $3 "/" $2}')"
        echo "Disk Usage: $(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 ")"}')"
        echo ""

        # Network connectivity
        echo "=== NETWORK CONNECTIVITY ==="
        echo ""
        echo "Docker Networks:"
        docker network ls | grep -E "minder|docker"
        echo ""

    } | tee "$report_file"

    log "${GREEN}✓ Health report generated: $report_file${NC}"
}

# Continuous monitoring
watch_mode() {
    log "${BLUE}Starting continuous monitoring mode (Ctrl+C to stop)${NC}"

    while true; do
        clear
        echo "=========================================="
        echo "  MINDER PLATFORM - LIVE MONITORING"
        echo "=========================================="
        echo "Last Update: $(timestamp)"
        echo ""

        # Quick status overview
        local total=$(docker ps -a --format "{{.Names}}" | wc -l)
        local healthy=$(docker ps -a --filter "health=healthy" --format "{{.Names}}" | wc -l)
        local unhealthy=$(docker ps -a --filter "health=unhealthy" --format "{{.Names}}" | wc -l)
        local stopped=$(count_services "exited")
        local health_percentage=$((healthy * 100 / total))

        echo "Overall Health: ${health_percentage}% ($healthy/$total healthy)"
        echo "Unhealthy: $unhealthy | Stopped: $stopped"
        echo ""

        # Service status table
        echo "=== SERVICE STATUS ==="
        printf "%-30s %-20s %-10s\n" "Service" "Status" "Health"
        printf "%-30s %-20s %-10s\n" "-------" "------" "------"

        docker ps -a --format "{{.Names}}" | sort | while read service; do
            local status=$(docker ps -a --filter "name=$service" --format "{{.Status}}")
            local health="N/A"
            [[ "$status" =~ "healthy" ]] && health="✓ Healthy"
            [[ "$status" =~ "unhealthy" ]] && health="✗ Unhealthy"
            [[ "$status" =~ "exited" ]] && health="✗ Stopped"

            # Color coding
            local color="$NC"
            [[ "$health" =~ "✓" ]] && color="$GREEN"
            [[ "$health" =~ "✗" ]] && color="$RED"

            printf "%-30s %-20s ${color}%-10s${NC}\n" "$service" "$(echo $status | cut -d' ' -f1-2)" "$health"
        done

        echo ""
        echo "Press Ctrl+C to stop monitoring..."

        sleep 30
    done
}

# Main health check function
main_check() {
    log "${BLUE}=========================================="
    log "  MINDER PLATFORM HEALTH CHECK"
    log "==========================================${NC}"

    local total=$(docker ps -a --format "{{.Names}}" | wc -l)
    local healthy=$(docker ps -a --filter "health=healthy" --format "{{.Names}}" | wc -l)
    local unhealthy=$(docker ps -a --filter "health=unhealthy" --format "{{.Names}}" | wc -l)
    local stopped=$(count_services "exited")
    local health_percentage=$((healthy * 100 / total))

    log "Total Services: $total"
    log "Healthy: $healthy (${GREEN}✓${NC})"
    log "Unhealthy: $unhealthy ${YELLOW}⚠${NC}"
    log "Stopped: $stopped ${RED}✗${NC}"
    log "Overall Health: ${health_percentage}%"
    log ""

    # Check for unhealthy services
    if [ $unhealthy -gt 0 ]; then
        log "${YELLOW}⚠ Found $unhealthy unhealthy services${NC}"
        get_unhealthy_services | while read service; do
            log "${YELLOW}⚠ Unhealthy: $service${NC}"
        done
    fi

    # Check for stopped services
    if [ $stopped -gt 0 ]; then
        log "${RED}✗ Found $stopped stopped services${NC}"
        get_stopped_services | while read service; do
            log "${RED}✗ Stopped: $service${NC}"
        done
    fi

    # Overall status
    if [ $health_percentage -ge 90 ]; then
        log "${GREEN}✓ System is HEALTHY (${health_percentage}%)${NC}"
        return 0
    elif [ $health_percentage -ge 70 ]; then
        log "${YELLOW}⚠ System needs attention (${health_percentage}%)${NC}"
        return 1
    else
        log "${RED}✗ System is CRITICAL (${health_percentage}%)${NC}"
        return 2
    fi
}

# Parse command line arguments
case "${1:-}" in
    --fix)
        log "${BLUE}Running health check with auto-fix${NC}"
        main_check

        # Fix unhealthy services
        get_unhealthy_services | while read service; do
            log "Attempting to fix: $service"
            restart_service "$service"
        done

        # Fix stopped services
        get_stopped_services | while read service; do
            log "Attempting to start: $service"
            cd /root/minder/docker/compose
            docker compose up -d "$service" 2>&1 | tee -a "$LOG_FILE"
        done

        log "${GREEN}Auto-fix complete${NC}"
        ;;

    --report)
        generate_report
        ;;

    --watch)
        watch_mode
        ;;

    *)
        main_check
        ;;
esac

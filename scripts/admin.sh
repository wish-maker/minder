#!/bin/bash
###############################################################################
# Minder Platform - Interactive Administration Panel
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
DOCKER_DIR="../infrastructure/docker"
PROJECT_ROOT=".."

# Utility functions
print_header() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${BOLD}$1${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_menu() {
    echo -e "${BOLD}${BLUE}Select an option:${NC}"
    echo ""
}

print_option() {
    local num=$1
    local desc=$2
    echo -e "  ${GREEN}$num)${NC} $desc"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Menu functions
show_main_menu() {
    print_header "🧠 MINDER PLATFORM - ADMINISTRATION PANEL"

    echo -e "${BOLD}${CYAN}System Status${NC}"
    echo "  ┌─────────────────────────────────────────────┐"
    echo "  │  Services: $(docker ps -q | wc -l) running                      │"
    echo "  │  CPU Load: $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}')                            │"
    echo "  │  Memory: $(free -h | awk '/Mem:/{printf "%.1fG/%.1fG", $3, $2}')                         │"
    echo "  └─────────────────────────────────────────────┘"
    echo ""

    print_menu

    echo -e "${BOLD}${MAGENTA}📊 Monitoring${NC}"
    print_option "1" "Show Service Status"
    print_option "2" "Show Resource Usage"
    print_option "3" "Show Health Check Report"
    print_option "4" "View Logs"
    echo ""

    echo -e "${BOLD}${MAGENTA}🔧 Management${NC}"
    print_option "5" "Start All Services"
    print_option "6" "Stop All Services"
    print_option "7" "Restart Services"
    print_option "8" "Update & Rebuild"
    echo ""

    echo -e "${BOLD}${MAGENTA}🔒 Security${NC}"
    print_option "9" "Show Credentials"
    print_option "10" "Change Passwords"
    print_option "11" "Security Audit"
    echo ""

    echo -e "${BOLD}${MAGENTA}🗑️ Cleanup${NC}"
    print_option "12" "Clean Logs"
    print_option "13" "Clean Cache"
    print_option "14" "Full Reset"
    echo ""

    echo -e "${BOLD}${MAGENTA}❓ Help & Info${NC}"
    print_option "15" "Show Access URLs"
    print_option "16" "System Information"
    print_option "17" "Troubleshooting Guide"
    echo ""

    print_option "0" "Exit"
    echo ""
}

# Action functions
show_service_status() {
    print_header "SERVICE STATUS"

    cd "${DOCKER_DIR}"
    docker compose ps
    cd "${PROJECT_ROOT}"

    echo ""
    read -p "Press Enter to continue..."
}

show_resource_usage() {
    print_header "RESOURCE USAGE"

    echo -e "${BOLD}Container Stats:${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

    echo ""
    echo -e "${BOLD}System Resources:${NC}"
    echo "CPU: $(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1"%"}')"
    echo "Memory: $(free -h | awk '/Mem:/{printf "%.1fG/%.1fG (%.1f%%)", $3, $2, $3/$2*100}')"
    echo "Disk: $(df -h / | awk 'NR==2{printf "%s/%s (%s)", $3, $2, $5}')"

    echo ""
    read -p "Press Enter to continue..."
}

show_health_check() {
    print_header "HEALTH CHECK REPORT"

    ../scripts/health-check.sh

    echo ""
    read -p "Press Enter to continue..."
}

view_logs() {
    print_header "VIEW LOGS"

    echo "Select service:"
    echo "  1) API Gateway"
    echo "  2) Plugin Registry"
    echo "  3) RAG Pipeline"
    echo "  4) Ollama"
    echo "  5) All Services"
    echo ""
    read -p "Choice: " choice

    case $choice in
        1) docker logs -f --tail=100 minder-api-gateway ;;
        2) docker logs -f --tail=100 minder-plugin-registry ;;
        3) docker logs -f --tail=100 minder-rag-pipeline ;;
        4) docker logs -f --tail=100 minder-ollama ;;
        5) cd "${DOCKER_DIR}" && docker compose logs -f --tail=100 ;;
    esac
}

start_services() {
    print_header "STARTING SERVICES"

    cd "${DOCKER_DIR}"
    docker compose up -d
    cd "${PROJECT_ROOT}"

    print_success "Services started"
    sleep 2
}

stop_services() {
    print_header "STOPPING SERVICES"

    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        cd "${DOCKER_DIR}"
        docker compose down
        cd "${PROJECT_ROOT}"
        print_success "Services stopped"
    fi
    sleep 2
}

restart_services() {
    print_header "RESTARTING SERVICES"

    cd "${DOCKER_DIR}"
    docker compose restart
    cd "${PROJECT_ROOT}"

    print_success "Services restarted"
    sleep 2
}

update_rebuild() {
    print_header "UPDATE & REBUILD"

    read -p "Pull latest code first? (yes/no): " pull

    if [ "$pull" = "yes" ]; then
        git pull origin main
    fi

    print_info "Rebuilding services..."
    cd "${DOCKER_DIR}"
    docker compose up -d --build
    cd "${PROJECT_ROOT}"

    print_success "Rebuild complete"
    sleep 2
}

show_credentials() {
    print_header "SECURITY CREDENTIALS"

    print_warning "Keep these credentials secure!"
    echo ""

    if [ -f "${DOCKER_DIR}/.env" ]; then
        echo -e "${BOLD}Database Credentials:${NC}"
        grep "POSTGRES_PASSWORD" "${DOCKER_DIR}/.env" | head -1
        grep "REDIS_PASSWORD" "${DOCKER_DIR}/.env" | head -1
        echo ""

        echo -e "${BOLD}Application Credentials:${NC}"
        grep "JWT_SECRET" "${DOCKER_DIR}/.env" | head -1
        grep "WEBUI_SECRET_KEY" "${DOCKER_DIR}/.env" | head -1
        echo ""

        echo -e "${BOLD}Monitoring:${NC}"
        grep "GRAFANA_ADMIN_PASSWORD" "${DOCKER_DIR}/.env" | head -1
        grep "NEO4J_AUTH" "${DOCKER_DIR}/.env" | head -1
    else
        print_error "Configuration file not found"
    fi

    echo ""
    read -p "Press Enter to continue..."
}

change_passwords() {
    print_header "CHANGE PASSWORDS"

    echo "Select password to change:"
    echo "  1) Grafana Admin"
    echo "  2) PostgreSQL"
    echo "  3) Redis"
    echo "  4) JWT Secret"
    echo ""
    read -p "Choice: " choice

    case $choice in
        1)
            read -sp "New password: " pass
            docker exec -it minder-grafana grafana-cli admin reset-admin-password "$pass"
            ;;
        2)
            print_warning "PostgreSQL password change requires manual update"
            print_info "Edit infrastructure/docker/.env and restart services"
            ;;
        3)
            print_warning "Redis password change requires manual update"
            print_info "Edit infrastructure/docker/.env and restart services"
            ;;
        4)
            print_warning "JWT secret change requires manual update"
            print_info "Edit infrastructure/docker/.env and restart services"
            ;;
    esac

    print_success "Password change initiated"
    sleep 2
}

security_audit() {
    print_header "SECURITY AUDIT"

    echo -e "${BOLD}1. Container Security:${NC}"
    docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"

    echo ""
    echo -e "${BOLD}2. Open Ports:${NC}"
    docker ps --format "{{.Ports}}" | grep -o '0.0.0.0:[0-9]*' | sort -u

    echo ""
    echo -e "${BOLD}3. Volume Permissions:${NC}"
    docker volume ls | grep minder

    echo ""
    echo -e "${BOLD}4. Network Configuration:${NC}"
    docker network ls | grep minder

    echo ""
    echo -e "${BOLD}5. Security Recommendations:${NC}"
    echo "  ✓ Use strong passwords"
    echo "  ✓ Enable TLS/SSL for production"
    echo "  ✓ Restrict port exposure"
    echo "  ✓ Regular security updates"
    echo "  ✓ Monitor logs for suspicious activity"

    echo ""
    read -p "Press Enter to continue..."
}

clean_logs() {
    print_header "CLEAN LOGS"

    read -p "Clean all container logs? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        docker ps -q | xargs -I {} sh -c 'truncate -s 0 /var/lib/docker/containers/$(docker inspect {} | grep LogPath | cut -d'"' -f4) 2>/dev/null || true'
        print_success "Logs cleaned"
    fi
    sleep 2
}

clean_cache() {
    print_header "CLEAN CACHE"

    print_info "Cleaning Docker build cache..."
    docker builder prune -f

    print_info "Cleaning dangling images..."
    docker image prune -f

    print_info "Cleaning unused volumes..."
    docker volume prune -f

    print_success "Cache cleaned"
    sleep 2
}

full_reset() {
    print_header "⚠️  FULL RESET"

    print_warning "This will remove ALL data, containers, and images!"
    echo ""
    read -p "Type 'RESET' to confirm: " confirm

    if [ "$confirm" = "RESET" ]; then
        cd "${DOCKER_DIR}"
        docker compose down -v
        docker system prune -a --volumes -f
        cd "${PROJECT_ROOT}"
        print_success "Full reset complete"
        print_info "Run ./deploy.sh deploy to start fresh"
    else
        print_info "Reset cancelled"
    fi
    sleep 2
}

show_access_urls() {
    print_header "ACCESS URLs"

    echo -e "${BOLD}Web Interfaces:${NC}"
    echo "  🌐 API Gateway:        http://localhost:8000"
    echo "  📚 API Documentation:  http://localhost:8000/docs"
    echo "  🔌 Plugin Registry:    http://localhost:8001"
    echo "  🤖 OpenWebUI:          http://localhost:8080"
    echo "  📊 Grafana:            http://localhost:3000"
    echo "  📈 Prometheus:         http://localhost:9090"
    echo ""

    echo -e "${BOLD}Default Credentials:${NC}"
    echo "  Grafana: admin / (check .env)"
    echo "  Neo4j: neo4j / (check .env)"
    echo ""

    read -p "Press Enter to continue..."
}

show_system_info() {
    print_header "SYSTEM INFORMATION"

    echo -e "${BOLD}Docker:${NC}"
    docker --version
    docker compose version
    echo ""

    echo -e "${BOLD}System:${NC}"
    uname -a
    echo ""

    echo -e "${BOLD}Resources:${NC}"
    echo "CPU: $(nproc) cores"
    echo "Memory: $(free -h | awk '/Mem:/{printf "%.1fG total", $2}')"
    echo "Disk: $(df -h / | awk 'NR==2{printf "%s total, %s used", $2, $3}')"
    echo ""

    echo -e "${BOLD}Minder Platform:${NC}"
    echo "Version: 2.0.0"
    echo "Services: $(docker ps -q | wc -l) running"
    echo "Containers: $(docker ps -a | wc -l) total"
    echo "Volumes: $(docker volume ls | wc -l) total"
    echo ""

    read -p "Press Enter to continue..."
}

show_troubleshooting() {
    print_header "TROUBLESHOOTING GUIDE"

    echo -e "${BOLD}Common Issues:${NC}"
    echo ""
    echo "1. Service won't start:"
    echo "   ./deploy.sh logs <service-name>"
    echo "   docker restart minder-<service>"
    echo ""
    echo "2. Out of memory:"
    echo "   docker stats"
    echo "   docker stop minder-ollama  # If not using AI"
    echo ""
    echo "3. Port conflicts:"
    echo "   sudo lsof -i :8000"
    echo "   # Change port in infrastructure/docker/.env"
    echo ""
    echo "4. Database connection issues:"
    echo "   docker exec -it minder-postgres psql -U minder -d minder"
    echo "   docker restart minder-postgres"
    echo ""
    echo "5. AI models not loading:"
    echo "   docker exec -it minder-ollama ollama list"
    echo "   docker exec -it minder-ollama ollama pull llama3.2"
    echo ""

    echo -e "${BOLD}Get More Help:${NC}"
    echo "  📚 Documentation: docs/"
    echo "  🐛 Report Issues: https://github.com/your-org/minder/issues"
    echo "  💬 Discussions: https://github.com/your-org/minder/discussions"
    echo ""

    read -p "Press Enter to continue..."
}

# Main loop
main() {
    while true; do
        show_main_menu
        read -p "Enter choice: " choice

        case $choice in
            1) show_service_status ;;
            2) show_resource_usage ;;
            3) show_health_check ;;
            4) view_logs ;;
            5) start_services ;;
            6) stop_services ;;
            7) restart_services ;;
            8) update_rebuild ;;
            9) show_credentials ;;
            10) change_passwords ;;
            11) security_audit ;;
            12) clean_logs ;;
            13) clean_cache ;;
            14) full_reset ;;
            15) show_access_urls ;;
            16) show_system_info ;;
            17) show_troubleshooting ;;
            0)
                print_success "Goodbye!"
                exit 0
                ;;
            *)
                print_error "Invalid choice"
                sleep 1
                ;;
        esac
    done
}

main

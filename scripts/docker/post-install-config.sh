#!/usr/bin/env bash
# ============================================================================
# Minder Platform Post-Install Configuration
# ============================================================================
# This script runs after setup.sh to ensure proper system configuration
# for zero-install deployment readiness.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================================
# CRITICAL FIXES FOR ZERO-INSTALL DEPLOYMENT
# ============================================================================

fix_ufw_forward_policy() {
    log_info "Checking UFW FORWARD policy..."

    # Check if UFW is active
    if ! command -v ufw &>/dev/null; then
        log_warn "UFW not installed, skipping..."
        return 0
    fi

    if ! ufw status | grep -q "Status: active"; then
        log_warn "UFW not active, skipping..."
        return 0
    fi

    # Check current forward policy
    current_policy=$(grep "DEFAULT_FORWARD_POLICY" /etc/default/ufw 2>/dev/null | cut -d= -f2)

    if [[ "$current_policy" == "DROP" ]]; then
        log_warn "UFW FORWARD policy is DROP - changing to ACCEPT for Docker..."
        sed -i 's/DEFAULT_FORWARD_POLICY="DROP"/DEFAULT_FORWARD_POLICY="ACCEPT"/' /etc/default/ufw
        ufw reload &>/dev/null
        log_success "UFW FORWARD policy changed to ACCEPT"
    else
        log_success "UFW FORWARD policy is ACCEPT (already correct)"
    fi
}

update_telegraf_config() {
    log_info "Checking Telegraf InfluxDB configuration..."

    local telegraf_conf="/root/minder/infrastructure/docker/telegraf/telegraf.conf"

    if [[ ! -f "$telegraf_conf" ]]; then
        log_warn "Telegraf config not found, skipping..."
        return 0
    fi

    # Check if using wrong InfluxDB version
    if grep -q "\[\[outputs.influxdb_v3\]\]" "$telegraf_conf"; then
        log_warn "Telegraf using InfluxDB v3 config - updating to v2..."

        # Backup original
        cp "$telegraf_conf" "${telegraf_conf}.backup"

        # Update to InfluxDB v2 format
        sed -i 's/\[\[outputs.influxdb_v3\]\]/[[outputs.influxdb_v2]]/' "$telegraf_conf"
        sed -i 's/^  database = "minder_metrics"/  organization = "${INFLUXDB_ORG:-minder}"/' "$telegraf_conf"
        sed -i '/^  database = "minder_metrics"/d' "$telegraf_conf"
        sed -i '/^  organization/a\  bucket = "${INFLUXDB_BUCKET:-telegraf}"' "$telegraf_conf"

        log_success "Telegraf config updated to InfluxDB v2"
        echo "Run: docker restart minder-telegraf"
    else
        log_success "Telegraf config already correct"
    fi
}

fix_redis_exporter_config() {
    log_info "Checking Redis Exporter configuration..."

    local compose_file="/root/minder/infrastructure/docker/docker-compose.yml"

    if [[ ! -f "$compose_file" ]]; then
        log_warn "docker-compose.yml not found, skipping..."
        return 0
    fi

    # Check Redis exporter config
    if grep -q "REDIS_ADDR=redis://:\${REDIS_PASSWORD}@redis:6379" "$compose_file"; then
        log_warn "Redis Exporter using wrong auth format - updating..."

        # Backup original
        cp "$compose_file" "${compose_file}.backup"

        # Fix to correct format
        sed -i 's/REDIS_ADDR=redis://:\${REDIS_PASSWORD}@redis:6379/REDIS_ADDR=redis:\/\/redis:6379/' "$compose_file"
        sed -i '/REDIS_ADDR=redis:\/\/redis:6379/a\    - REDIS_PASSWORD=${REDIS_PASSWORD}' "$compose_file"

        log_success "Redis Exporter config updated"
        echo "Run: docker compose restart redis-exporter"
    else
        log_success "Redis Exporter config already correct"
    fi
}

# ============================================================================
# EXTERNAL IP DISCOVERY
# ============================================================================

get_external_ip() {
    # Try to get the primary external IP
    local primary_ip

    # Method 1: Get first non-docker/non-loopback IP
    primary_ip=$(hostname -I | awk '{print $1}')

    # Method 2: Fallback to eth0 if primary is localhost
    if [[ -z "$primary_ip" ]] || [[ "$primary_ip" == "127.0.0.1" ]]; then
        if command -v ip &>/dev/null; then
            primary_ip=$(ip addr show eth0 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
        fi
    fi

    echo "$primary_ip"
}

display_access_info() {
    local external_ip
    external_ip=$(get_external_ip)

    if [[ -n "$external_ip" ]]; then
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo -e "${GREEN}MINDER PLATFORM ACCESS URLs${NC}"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo -e "${BLUE}API Gateway:${NC}      http://${external_ip}:8000/health"
        echo -e "${BLUE}Plugin Registry:${NC}  http://${external_ip}:8001/health"
        echo -e "${BLUE}RAG Pipeline:${NC}     http://${external_ip}:8004/health"
        echo -e "${BLUE}Grafana:${NC}          http://${external_ip}:3000"
        echo -e "${BLUE}Prometheus:${NC}       http://${external_ip}:9090"
        echo ""
        echo -e "${YELLOW}NOTE:${NC} If localhost (127.0.0.1) doesn't work, use the external IP above."
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
    fi
}

# ============================================================================
# MAIN EXECUTION
# ============================================================================

main() {
    echo "═══════════════════════════════════════════════════════════════"
    echo "Minder Platform Post-Install Configuration"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    # Run all fixes
    fix_ufw_forward_policy
    update_telegraf_config
    fix_redis_exporter_config

    # Display access information
    display_access_info

    log_success "Post-install configuration complete!"
    echo ""
    echo "Next steps:"
    echo "1. Restart any modified services if needed"
    echo "2. Test external access: curl http://$(get_external_ip):8000/health"
    echo "3. Run health checks: docker ps -a --filter health=unhealthy"
    echo ""
}

# Run main function
main "$@"

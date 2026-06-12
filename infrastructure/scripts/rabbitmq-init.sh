#!/bin/bash
# ============================================================================
# Minder Platform - RabbitMQ Multi-Tenant Resource Initialization
# ============================================================================
# Creates vhosts, users, permissions, queues, exchanges, and bindings
# Usage: ./rabbitmq-init.sh [create|delete|status]
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# RabbitMQ connection settings
RABBITMQ_HOST="localhost"
RABBITMQ_PORT="15672"
RABBITMQ_USER="minder"
RABBITMQ_PASSWORD="${RABBITMQ_PASSWORD:-minder}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[RabbitMQ]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[RabbitMQ]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[RabbitMQ]${NC} $1"
}

log_error() {
    echo -e "${RED}[RabbitMQ]${NC} $1"
}

# ============================================================================
# RabbitMQ Management API Functions
# ============================================================================

rabbitmq_api() {
    local endpoint=$1
    local method=${2:-GET}
    local data=${3:-}

    local url="http://${RABBITMQ_HOST}:${RABBITMQ_PORT}/api/${endpoint}"

    if [ -n "$data" ]; then
        curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASSWORD}" \
             -X "${method}" \
             -H "content-type:application/json" \
             -d "${data}" \
             "${url}"
    else
        curl -s -u "${RABBITMQ_USER}:${RABBITMQ_PASSWORD}" \
             -X "${method}" \
             "${url}"
    fi
}

# ============================================================================
# Vhost Management
# ============================================================================

create_vhost() {
    local vhost_name=$1

    log_info "Creating vhost: ${vhost_name}"

    local response
    response=$(rabbitmq_api "vhosts/${vhost_name}" PUT '{"tracing":false}' 2>&1)

    if echo "$response" | grep -q "error\|404"; then
        log_error "Failed to create vhost: ${vhost_name}"
        return 1
    else
        log_success "Vhost created: ${vhost_name}"
    fi
}

delete_vhost() {
    local vhost_name=$1

    log_info "Deleting vhost: ${vhost_name}"
    rabbitmq_api "vhosts/${vhost_name}" DELETE
    log_success "Vhost deleted: ${vhost_name}"
}

list_vhosts() {
    log_info "Listing all vhosts..."
    rabbitmq_api "vhosts" | jq -r '.[] | select(.name | startswith("minder")) | .name'
}

# ============================================================================
# User Management
# ============================================================================

create_user() {
    local username=$1
    local password=$2
    local vhost=$3

    log_info "Creating user: ${username} for vhost: ${vhost}"

    # Create user
    rabbitmq_api "users/${username}" PUT "{\"password\":\"${password}\",\"tags\":\"\"}" > /dev/null 2>&1

    # Grant permissions
    rabbitmq_api "permissions/${vhost}/${username}" PUT "{\"configure\":\".*\",\"write\":\".*\",\"read\":\".*\"}" > /dev/null 2>&1

    log_success "User created: ${username}"
}

# ============================================================================
# Queue Management
# ============================================================================

declare -A QUEUE_DEFINITIONS=(
    ["minder"]="[
        {\"name\":\"tasks.incoming\",\"durable\":true,\"auto_delete\":false,\"arguments\":{\"x-max-length\":10000}},
        {\"name\":\"tasks.processing\",\"durable\":true,\"auto_delete\":false,\"arguments\":{\"x-max-length\":5000}},
        {\"name\":\"events.incoming\",\"durable\":true,\"auto_delete\":false,\"arguments\":{\"x-max-length\":50000}},
        {\"name\":\"notifications\",\"durable\":true,\"auto_delete\":false}
    ]"
    ["monitoring"]="[
        {\"name\":\"metrics.incoming\",\"durable\":true,\"auto_delete\":false,\"arguments\":{\"x-max-length\":100000}},
        {\"name\":\"alerts\",\"durable\":true,\"auto_delete\":false},
        {\"name\":\"logs\",\"durable\":false,\"auto_delete\":true,\"arguments\":{\"x-message-ttl\":86400000}}
    ]"
    ["analytics"]="[
        {\"name\":\"events.raw\",\"durable\":true,\"auto_delete\":false,\"arguments\":{\"x-max-length\":1000000}},
        {\"name\":\"events.processed\",\"durable\":true,\"auto_delete\":false},
        {\"name\":\"aggregation\",\"durable\":true,\"auto_delete\":false}
    ]"
)

create_queues() {
    local vhost=$1
    local queue_json=${QUEUE_DEFINITIONS[$vhost]}

    log_info "Creating queues for vhost: ${vhost}"

    echo "$queue_json" | jq -c '.[]' | while read -r queue; do
        local queue_name
        queue_name=$(echo "$queue" | jq -r '.name')

        log_info "Creating queue: ${queue_name}"

        rabbitmq_api "queues/${vhost}/${queue_name}" PUT "$queue" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            log_success "Queue created: ${queue_name}"
        else
            log_warn "Queue may already exist: ${queue_name}"
        fi
    done
}

# ============================================================================
# Exchange Management
# ============================================================================

declare -A EXCHANGE_DEFINITIONS=(
    ["minder"]="[
        {\"name\":\"tasks.direct\",\"type\":\"direct\",\"durable\":true},
        {\"name\":\"tasks.fanout\",\"type\":\"fanout\",\"durable\":true},
        {\"name\":\"events.topic\",\"type\":\"topic\",\"durable\":true}
    ]"
    ["monitoring"]="[
        {\"name\":\"metrics.direct\",\"type\":\"direct\",\"durable\":true},
        {\"name\":\"alerts.topic\",\"type\":\"topic\",\"durable\":true}
    ]"
    ["analytics"]="[
        {\"name\":\"events.direct\",\"type\":\"direct\",\"durable\":true},
        {\"name\":\"analytics.fanout\",\"type\":\"fanout\",\"durable\":true}
    ]"
)

create_exchanges() {
    local vhost=$1
    local exchange_json=${EXCHANGE_DEFINITIONS[$vhost]}

    log_info "Creating exchanges for vhost: ${vhost}"

    echo "$exchange_json" | jq -c '.[]' | while read -r exchange; do
        local exchange_name
        exchange_name=$(echo "$exchange" | jq -r '.name')

        log_info "Creating exchange: ${exchange_name}"

        rabbitmq_api "exchanges/${vhost}/${exchange_name}" PUT "$exchange" > /dev/null 2>&1

        if [ $? -eq 0 ]; then
            log_success "Exchange created: ${exchange_name}"
        else
            log_warn "Exchange may already exist: ${exchange_name}"
        fi
    done
}

# ============================================================================
# Binding Management
# ============================================================================

create_bindings() {
    local vhost=$1

    log_info "Creating bindings for vhost: ${vhost}"

    # Task queues to direct exchange
    rabbitmq_api "bindings/${vhost}/e/tasks.direct/q/tasks.incoming" POST \
        '{"source":"tasks.direct","vhost":"'${vhost}'","destination":"tasks.incoming","destination_type":"queue","routing_key":"incoming"}' > /dev/null 2>&1

    rabbitmq_api "bindings/${vhost}/e/tasks.direct/q/tasks.processing" POST \
        '{"source":"tasks.direct","vhost":"'${vhost}'","destination":"tasks.processing","destination_type":"queue","routing_key":"processing"}' > /dev/null 2>&1

    # Events queue to topic exchange
    rabbitmq_api "bindings/${vhost}/e/events.topic/q/events.incoming" POST \
        '{"source":"events.topic","vhost":"'${vhost}'","destination":"events.incoming","destination_type":"queue","routing_key":"events.#"}' > /dev/null 2>&1

    log_success "Bindings created for vhost: ${vhost}"
}

# ============================================================================
# Main Functions
# ============================================================================

create_all_resources() {
    log_info "Creating RabbitMQ multi-tenant resources..."

    # Create vhosts
    for vhost in "minder" "monitoring" "analytics"; do
        create_vhost "$vhost"

        # Create queues
        create_queues "$vhost"

        # Create exchanges
        create_exchanges "$vhost"

        # Create bindings
        create_bindings "$vhost"

        # Create dedicated users for each vhost
        create_user "${vhost}_user" "${RABBITMQ_PASSWORD}_${vhost}" "$vhost"
    done

    log_success "RabbitMQ multi-tenant resources created successfully!"
}

delete_all_resources() {
    log_warn "Deleting all RabbitMQ multi-tenant resources..."

    for vhost in "analytics" "monitoring" "minder"; do
        delete_vhost "$vhost"
        rabbitmq_api "users/${vhost}_user" DELETE > /dev/null 2>&1 || true
    done

    log_success "All RabbitMQ resources deleted"
}

show_status() {
    log_info "RabbitMQ multi-tenant status:"

    echo ""
    echo "Vhosts:"
    list_vhosts

    echo ""
    echo "Queues per vhost:"
    for vhost in "minder" "monitoring" "analytics"; do
        echo "  ${vhost}:"
        rabbitmq_api "queues/${vhost}" | jq -r '.[].name' | sed 's/^/    - /' || echo "    No queues found"
    done

    echo ""
    echo "Exchanges per vhost:"
    for vhost in "minder" "monitoring" "analytics"; do
        echo "  ${vhost}:"
        rabbitmq_api "exchanges/${vhost}" | jq -r '.[].name' | sed 's/^/    - /' || echo "    No exchanges found"
    done
}

# ============================================================================
# Main Command Handler
# ============================================================================

case "${1:-}" in
    create)
        create_all_resources
        ;;
    delete)
        delete_all_resources
        ;;
    status)
        show_status
        ;;
    *)
        echo "Minder Platform - RabbitMQ Multi-Tenant Resource Management"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  create    Create all vhosts, queues, exchanges, and bindings"
        echo "  delete    Delete all RabbitMQ resources"
        echo "  status    Show current RabbitMQ resource status"
        echo ""
        echo "Examples:"
        echo "  $0 create"
        echo "  $0 status"
        exit 1
        ;;
esac

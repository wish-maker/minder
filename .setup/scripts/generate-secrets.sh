#!/bin/bash
# ============================================================================
# Minder Platform - Docker Secrets Generator
# ============================================================================
# Generates secure Docker secrets for all sensitive environment variables
# Usage: ./generate-secrets.sh [generate|rotate|list]
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SECRETS_DIR="$PROJECT_ROOT/.secrets"
ENV_FILE="$PROJECT_ROOT/infrastructure/docker/.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# Secret Management Functions
# ============================================================================

generate_random_string() {
    local length=$1
    openssl rand -base64 "$length" | tr -d '=+/' | cut -c1-"$length"
}

generate_password() {
    local length=${1:-32}
    # Generate strong password with mixed case, numbers, and special chars
    openssl rand -base64 48 | tr -d '=+/' | cut -c1-"$length"
}

generate_jwt_secret() {
    # JWT secrets should be longer (64 bytes)
    generate_random_string 64
}

generate_session_secret() {
    # Session secrets for Authelia (32 bytes)
    generate_random_string 32
}

generate_influxdb_token() {
    # InfluxDB tokens have specific format requirements
    echo "my-super-secret-auth-token-$(generate_random_string 24)"
}

# ============================================================================
# Secret Definitions
# ============================================================================

declare -A SECRET_DESCRIPTIONS=(
    ["postgres_password"]="PostgreSQL database password"
    ["redis_password"]="Redis cache password"
    ["rabbitmq_password"]="RabbitMQ message broker password"
    ["minio_root_password"]="MinIO object storage admin password"
    ["influxdb_token"]="InfluxDB time-series database authentication token"
    ["influxdb_admin_password"]="InfluxDB admin user password"
    ["grafana_password"]="Grafana monitoring dashboard admin password"
    ["jwt_secret"]="JWT token signing secret for API authentication"
    ["authelia_jwt_secret"]="Authelia 2FA authentication JWT secret"
    ["authelia_session_secret"]="Authelia session encryption secret"
    ["authelia_storage_encryption_key"]="Authelia database encryption key"
    ["webui_secret_key"]="OpenWebUI session encryption key"
)

declare -A SECRET_GENERATORS=(
    ["postgres_password"]="generate_password"
    ["redis_password"]="generate_password"
    ["rabbitmq_password"]="generate_password"
    ["minio_root_password"]="generate_password"
    ["influxdb_token"]="generate_influxdb_token"
    ["influxdb_admin_password"]="generate_password"
    ["grafana_password"]="generate_password"
    ["jwt_secret"]="generate_jwt_secret"
    ["authelia_jwt_secret"]="generate_session_secret"
    ["authelia_session_secret"]="generate_session_secret"
    ["authelia_storage_encryption_key"]="generate_password"
    ["webui_secret_key"]="generate_password"
)

# ============================================================================
# Secret File Operations
# ============================================================================

ensure_secrets_dir() {
    if [ ! -d "$SECRETS_DIR" ]; then
        log_info "Creating secrets directory: $SECRETS_DIR"
        mkdir -p "$SECRETS_DIR"
        chmod 700 "$SECRETS_DIR"
    fi
}

save_secret() {
    local secret_name=$1
    local secret_value=$2
    local secret_file="$SECRETS_DIR/${secret_name}.secret"

    echo -n "$secret_value" > "$secret_file"
    chmod 600 "$secret_file"
    log_info "Saved secret: $secret_name"
}

read_secret() {
    local secret_name=$1
    local secret_file="$SECRETS_DIR/${secret_name}.secret"

    if [ -f "$secret_file" ]; then
        cat "$secret_file"
    else
        log_error "Secret not found: $secret_name"
        return 1
    fi
}

generate_all_secrets() {
    log_info "Generating all secrets..."

    ensure_secrets_dir

    for secret_name in "${!SECRET_GENERATORS[@]}"; do
        local generator_func="${SECRET_GENERATORS[$secret_name]}"
        local secret_value=$($generator_func)
        save_secret "$secret_name" "$secret_value"
    done

    log_info "All secrets generated successfully!"
    log_warn "Please backup the secrets directory: $SECRETS_DIR"
}

rotate_secret() {
    local secret_name=$1

    if [ -z "$secret_name" ]; then
        log_error "Secret name required for rotation"
        echo "Usage: $0 rotate <secret_name>"
        exit 1
    fi

    if [ -z "${SECRET_GENERATORS[$secret_name]}" ]; then
        log_error "Unknown secret: $secret_name"
        echo "Available secrets:"
        for s in "${!SECRET_GENERATORS[@]}"; do
            echo "  - $s: ${SECRET_DESCRIPTIONS[$s]}"
        done
        exit 1
    fi

    log_info "Rotating secret: $secret_name"

    # Backup old secret
    local secret_file="$SECRETS_DIR/${secret_name}.secret"
    if [ -f "$secret_file" ]; then
        local backup_file="${secret_file}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$secret_file" "$backup_file"
        log_info "Backed up old secret to: $backup_file"
    fi

    # Generate new secret
    local generator_func="${SECRET_GENERATORS[$secret_name]}"
    local new_secret_value=$($generator_func)
    save_secret "$secret_name" "$new_secret_value"

    log_info "Secret rotated successfully!"
    log_warn "Remember to restart services that use this secret"
}

list_secrets() {
    log_info "Listing all secrets..."

    ensure_secrets_dir

    echo ""
    echo "Secret Name                      | Description                              | Status"
    echo "---------------------------------|------------------------------------------|--------"
    for secret_name in "${!SECRET_DESCRIPTIONS[@]}"; do
        local secret_file="$SECRETS_DIR/${secret_name}.secret"
        local status="❌ Missing"
        if [ -f "$secret_file" ]; then
            status="✓ Present"
        fi
        printf "%-32s | %-40s | %s\n" "$secret_name" "${SECRET_DESCRIPTIONS[$secret_name]}" "$status"
    done
    echo ""
}

export_secrets_to_env() {
    log_info "Exporting secrets to environment for docker-compose..."

    ensure_secrets_dir

    local env_export_file="$SECRETS_DIR/secrets.env"
    echo "# Auto-generated from Docker secrets - DO NOT COMMIT" > "$env_export_file"
    echo "# Generated: $(date)" >> "$env_export_file"

    for secret_name in "${!SECRET_GENERATORS[@]}"; do
        local secret_file="$SECRETS_DIR/${secret_name}.secret"
        if [ -f "$secret_file" ]; then
            local env_var_name=$(echo "$secret_name" | tr '[:lower:]' '[:upper:]')
            local secret_value=$(cat "$secret_file")
            echo "${env_var_name}=${secret_value}" >> "$env_export_file"
        fi
    done

    log_info "Exported to: $env_export_file"
}

# ============================================================================
# Main Command Handler
# ============================================================================

case "${1:-}" in
    generate)
        generate_all_secrets
        ;;
    rotate)
        rotate_secret "$2"
        ;;
    list)
        list_secrets
        ;;
    export)
        export_secrets_to_env
        ;;
    *)
        echo "Minder Platform - Docker Secrets Generator"
        echo ""
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  generate    Generate all secrets (overwrites existing)"
        echo "  rotate      Rotate a specific secret (backs up old value)"
        echo "  list        List all secrets and their status"
        echo "  export      Export secrets to .env file for docker-compose"
        echo ""
        echo "Examples:"
        echo "  $0 generate"
        echo "  $0 rotate jwt_secret"
        echo "  $0 list"
        echo "  $0 export"
        exit 1
        ;;
esac

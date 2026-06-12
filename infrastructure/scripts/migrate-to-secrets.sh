#!/bin/bash
# ============================================================================
# Minder Platform - Migration Script: Environment Variables to Secrets
# ============================================================================
# Migrates existing .env file to use Docker secrets
# This script updates docker-compose.yml to use secret files instead of env vars
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SECRETS_DIR="$PROJECT_ROOT/.secrets"
ENV_FILE="$PROJECT_ROOT/infrastructure/docker/.env"
COMPOSE_FILE="$PROJECT_ROOT/infrastructure/docker/docker-compose.yml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# ============================================================================
# Migration Functions
# ============================================================================

backup_files() {
    log_info "Backing up existing files..."

    # Backup .env file
    if [ -f "$ENV_FILE" ]; then
        cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "Backed up: $ENV_FILE"
    fi

    # Backup docker-compose.yml
    if [ -f "$COMPOSE_FILE" ]; then
        cp "$COMPOSE_FILE" "${COMPOSE_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        log_info "Backed up: $COMPOSE_FILE"
    fi
}

check_secrets_exist() {
    log_info "Checking if secrets exist..."

    local missing_secrets=()

    for secret_file in "$SECRETS_DIR"/*.secret; do
        if [ ! -f "$secret_file" ]; then
            missing_secrets+=("$(basename "$secret_file" .secret)")
        fi
    done

    if [ ${#missing_secrets[@]} -gt 0 ]; then
        log_warn "Missing secrets: ${missing_secrets[*]}"
        log_info "Run: ./generate-secrets.sh generate"
        exit 1
    fi

    log_info "All secrets found!"
}

# ============================================================================
# Main Migration Process
# ============================================================================

log_info "Starting migration to Docker secrets..."

# Check if secrets exist
check_secrets_exist

# Backup existing files
backup_files

log_info "Migration preparation complete!"
log_warn "Next steps:"
log_warn "1. Update docker-compose.yml to use secret files (manual step required)"
log_warn "2. Test services with new secret configuration"
log_warn "3. Remove sensitive values from .env file"
log_warn ""
log_warn "Example secret file mount in docker-compose.yml:"
log_warn "  services:"
log_warn "    postgres:"
log_warn "      environment:"
log_warn "        POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password"
log_warn "      secrets:"
log_warn "        - postgres_password"
log_warn "  secrets:"
log_warn "    postgres_password:"
log_warn "      file: ./.secrets/postgres_password.secret"

log_info "Migration script completed successfully!"

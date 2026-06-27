# ─────────────────────────────────────────────────────────────
# SECRET GENERATION
# ─────────────────────────────────────────────────────────────

gen_secret() {
    local bytes="${1:-32}"
    if command -v openssl &>/dev/null; then
        openssl rand -hex "$bytes"
    else
        LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c $(( bytes * 2 ))
    fi
}

generate_secrets() {
    local secrets_dir="${SCRIPT_DIR}/.secrets"

    log_step "Generating Docker secrets"

    # Create secrets directory
    mkdir -p "$secrets_dir"

    # Check if secrets already exist
    if [[ -f "$secrets_dir/postgres_password.secret" ]]; then
        log_info "Secrets already exist in $secrets_dir"
        log_detail "Remove directory to regenerate: rm -rf $secrets_dir"
        return 0
    fi

    log_detail "Generating 12 secrets in $secrets_dir"

    # Generate 12 secrets
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/postgres_password.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/redis_password.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/rabbitmq_password.secret"
    openssl rand -base64 85 | tr -d '=+/' | head -c 85 > "$secrets_dir/jwt_secret.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/webui_secret_key.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/grafana_password.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/influxdb_admin_password.secret"
    openssl rand -base64 64 | tr -d '=+/' | head -c 64 > "$secrets_dir/influxdb_token.secret"
    # authelia disabled pending proper configuration
    # openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/authelia_jwt_secret.secret"
    # openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/authelia_session_secret.secret"
    # openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/authelia_storage_encryption_key.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/minio_root_password.secret"

    # Set permissions
    chmod 600 "$secrets_dir"/*.secret

    # Grafana için 644 (non-root container user)
    chmod 644 "$secrets_dir/grafana_password.secret"
    chmod 644 "$secrets_dir/influxdb_admin_password.secret"
    chmod 644 "$secrets_dir/influxdb_token.secret"

    log_success "Secrets generated in $secrets_dir"
    log_detail "Permissions: 600 (grafana/influxdb: 644)"
}

sync_postgres_password() {
    local password_file="${SCRIPT_DIR}/.secrets/postgres_password.secret"

    if [[ ! -f "$password_file" ]]; then
        log_error "Password file not found: $password_file"
        return 1
    fi

    local new_password
    new_password=$(cat "$password_file")

    log_step "Syncing PostgreSQL password"

    # Check if PostgreSQL container is running
    if ! container_running postgres; then
        log_warn "PostgreSQL container not running"
        log_detail "Start services first: ./setup.sh start"
        return 1
    fi

    # Update password in database
    log_detail "Updating password in database..."
    if docker exec "$(container_name postgres)" psql -U minder -d minder -c \
        "ALTER USER minder PASSWORD '$new_password';" &>/dev/null; then
        log_success "PostgreSQL password synced"
    else
        log_warn "Password sync failed (may already be set)"
    fi
}


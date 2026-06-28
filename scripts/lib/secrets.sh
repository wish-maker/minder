# ─────────────────────────────────────────────────────────────
# POSTGRES PASSWORD ROTATION
#
# Stateful-credential caveat: editing POSTGRES_PASSWORD in .env does NOT
# rotate the live credential — Postgres bakes the password into its data
# volume at first init, after which it lives in the volume, not the env.
# This helper applies the current .env value to the running container via
# ALTER USER. Run it after changing POSTGRES_PASSWORD in .env.
#
# (gen_secret lives in env.sh, co-located with the .env secret fill.)
# ─────────────────────────────────────────────────────────────

sync_postgres_password() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error "Env file not found: $ENV_FILE"
        log_detail "Run install first: ./setup.sh"
        return 1
    fi

    local new_password
    new_password="$(_env_get POSTGRES_PASSWORD)"

    if [[ -z "$new_password" ]]; then
        log_error "POSTGRES_PASSWORD not set in $ENV_FILE"
        return 1
    fi

    log_step "Syncing PostgreSQL password from .env"

    # Check if PostgreSQL container is running
    if ! container_running postgres; then
        log_warn "PostgreSQL container not running"
        log_detail "Start services first: ./setup.sh start"
        return 1
    fi

    # Apply the .env password to the running database
    log_detail "Applying password from .env to running container…"
    if docker exec "$(container_name postgres)" psql -U minder -d minder -c \
        "ALTER USER minder PASSWORD '$new_password';" &>/dev/null; then
        log_success "PostgreSQL password synced"
    else
        log_warn "Password sync failed (may already be set)"
    fi
}

# ─────────────────────────────────────────────────────────────
# DRY RUN WRAPPER
# ─────────────────────────────────────────────────────────────

run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${DIM}[dry-run] $*${NC}"
        return 0
    fi
    "$@"
}

# ─────────────────────────────────────────────────────────────
# DOCKER HELPERS
# ─────────────────────────────────────────────────────────────

compose() {
    if [[ "${MINDER_USE_SECRETS:-false}" == "true" ]] && [[ -f "$SECRETS_FILE" ]]; then
        run docker compose -f "$COMPOSE_FILE" -f "$SECRETS_FILE" "$@"
    else
        run docker compose -f "$COMPOSE_FILE" "$@"
    fi
}

compose_monitoring() {
    if [[ "${MINDER_USE_SECRETS:-false}" == "true" ]] && [[ -f "$SECRETS_FILE" ]]; then
        run docker compose -f "$COMPOSE_FILE" -f "$SECRETS_FILE" --profile monitoring "$@"
    else
        run docker compose -f "$COMPOSE_FILE" --profile monitoring "$@"
    fi
}

container_name() { echo "${CONTAINER_PREFIX}-${1}"; }

container_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^$(container_name "$1")$"
}

container_health() {
    docker inspect --format='{{.State.Health.Status}}' "$(container_name "$1")" 2>/dev/null || echo "n/a"
}

container_exists() {
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^$(container_name "$1")$"
}

# ─────────────────────────────────────────────────────────────
# WAIT / POLL HELPERS
# ─────────────────────────────────────────────────────────────

wait_healthy() {
    local svc="$1" timeout="${2:-$TIMEOUT_SERVICES}"
    local elapsed=0

    spinner_start "Waiting for ${svc}…"
    while (( elapsed < timeout )); do
        local s; s="$(container_health "$svc")"
        if [[ "$s" == "healthy" ]]; then
            spinner_stop
            log_success "${svc} is healthy"
            return 0
        fi
        sleep 3; elapsed=$(( elapsed + 3 ))
    done
    spinner_stop
    log_warn "${svc} not healthy after ${timeout}s  (status: $(container_health "$svc"))"
    return 1
}

wait_port() {
    local host="$1" port="$2" timeout="${3:-$TIMEOUT_PORT}"
    local elapsed=0
    while (( elapsed < timeout )); do
        if 2>/dev/null >/dev/tcp/"$host"/"$port"; then return 0; fi
        sleep 2; elapsed=$(( elapsed + 2 ))
    done
    return 1
}

wait_postgres_ready() {
    local timeout="${1:-$TIMEOUT_DB}"
    local elapsed=0
    spinner_start "Waiting for PostgreSQL…"
    while (( elapsed < timeout )); do
        if docker exec "$(container_name postgres)" pg_isready -U minder &>/dev/null 2>&1; then
            spinner_stop
            log_success "PostgreSQL is ready"
            return 0
        fi
        sleep 2; elapsed=$(( elapsed + 2 ))
    done
    spinner_stop
    log_error "PostgreSQL did not become ready within ${timeout}s"
    return 1
}


# ─────────────────────────────────────────────────────────────
# SERVICE STARTUP
# ─────────────────────────────────────────────────────────────

start_services() {
    log_step "Starting all services"

    # Detect Ollama mode. The platform-managed ollama container is gated by the compose
    # 'internal-ollama' profile (see docker-compose.yml + config.sh). We activate it via
    # COMPOSE_PROFILES ONLY in internal mode. In external mode the profile stays inactive,
    # so ollama is not part of the project — no `compose up` here or added later can start
    # it (this replaces the old --scale ollama=0 flag, which had to be repeated on every
    # up and silently regressed when one was missed: finding #4).
    #
    # Source of the knob: an exported OLLAMA_BASE_URL wins (CLI override); otherwise read
    # it from .env (the single source of truth) so `ollama-mode` + a plain restart switch
    # modes without needing to export anything.
    local ollama_url="${OLLAMA_BASE_URL:-$(_env_get OLLAMA_BASE_URL)}"
    if [[ -n "$ollama_url" ]]; then
        log_info "🌐 External Ollama mode (OLLAMA_BASE_URL set)"
        log_info "   OLLAMA_BASE_URL: $ollama_url"
        log_info "   Platform-managed ollama container will NOT start (compose 'internal-ollama' profile inactive)"
        unset COMPOSE_PROFILES
    else
        log_info "🏠 Internal Ollama mode (platform-managed container, default zero-config)"
        log_info "   OLLAMA_BASE_URL: (empty, using internal minder-ollama container)"
        export COMPOSE_PROFILES="internal-ollama"
    fi

    log_info "① Security layer…"
    compose up -d "${SECURITY_SERVICES[@]}"
    sleep 5

    log_info "② Infrastructure (DB, cache, vector store, AI runtime)…"
    compose up -d "${CORE_SERVICES[@]}"
    sleep 8

    log_info "③ Message broker (RabbitMQ)…"
    # RabbitMQ is already started in CORE_SERVICES, just wait for it to be healthy
    wait_healthy "rabbitmq" "$TIMEOUT_SERVICES" || true

    log_info "④ Core microservices…"
    compose up -d "${API_SERVICES[@]}"
    sleep 5

    log_info "⑤ Monitoring stack…"
    compose up -d influxdb telegraf
    compose_monitoring up -d prometheus grafana alertmanager
    compose up -d "${MONITORING_SERVICES[@]}"
    sleep 5

    log_info "⑥ AI enhancement services…"
    compose up -d "${AI_SERVICES[@]}"
    sleep 5

    log_info "⑦ Metrics exporters…"
    compose_monitoring up -d "${EXPORTER_SERVICES[@]}"

    log_success "All service groups dispatched"
}

# ─────────────────────────────────────────────────────────────
# HEALTH CHECKS
# ─────────────────────────────────────────────────────────────

wait_for_services() {
    section "⏳  Waiting for Services"

    for svc in "${CORE_SERVICES[@]}";       do wait_healthy "$svc" "$TIMEOUT_SERVICES"   || true; done
    for svc in "${API_SERVICES[@]}";        do wait_healthy "$svc" "$TIMEOUT_SERVICES"   || true; done
    for svc in "${MONITORING_SERVICES[@]}"; do wait_healthy "$svc" "$TIMEOUT_MONITORING" || true; done
    for svc in "${AI_SERVICES[@]}";         do wait_healthy "$svc" "$TIMEOUT_AI"         || true; done
}


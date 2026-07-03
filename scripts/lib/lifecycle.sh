# ─────────────────────────────────────────────────────────────
# SERVICE STARTUP
# ─────────────────────────────────────────────────────────────

start_services() {
    log_step "Starting all services"

    # Detect Ollama mode. The local ollama container is gated by the compose
    # 'local-ollama' profile (see docker-compose.yml + config.sh). We activate it via
    # COMPOSE_PROFILES ONLY in local mode. In remote/native mode the profile stays
    # inactive, so ollama is not part of the project — no `compose up` here or added
    # later can start it (this replaces the old --scale ollama=0 flag, which had to be
    # repeated on every up and silently regressed when one was missed: finding #4).
    if [[ -n "${OLLAMA_BASE_URL:-}" ]]; then
        log_info "🌐 Remote Ollama mode DETECTED"
        log_info "   OLLAMA_BASE_URL: $OLLAMA_BASE_URL"
        log_info "   Local ollama container will NOT start (compose 'local-ollama' profile inactive)"
        unset COMPOSE_PROFILES
    else
        log_info "🏠 Local Ollama mode (default, zero-config)"
        log_info "   OLLAMA_BASE_URL: (empty, using local minder-ollama container)"
        export COMPOSE_PROFILES="local-ollama"
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


# ─────────────────────────────────────────────────────────────
# SERVICE STARTUP
# ─────────────────────────────────────────────────────────────

# Resolve a third-party image ref from THIRD_PARTY_IMAGE_SPECS by its repo base
# (everything before the :tag). Single source of truth for the manual-docker
# path, so its image versions can't drift from the compose path. Arg is the
# bare repo, e.g. "postgres" or "grafana/grafana".
manual_image() {
    local base="$1" spec ref
    for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do
        ref="${spec%%|*}"          # strip the |stable_tag|constraint suffix
        if [[ "${ref%:*}" == "$base" ]]; then
            echo "$ref"
            return 0
        fi
    done
    log_error "manual_image: no THIRD_PARTY_IMAGE_SPECS entry for image base '${base}'"
    return 1
}

start_services() {
    # Check if manual docker mode is enabled
    if [[ "${MINDER_USE_MANUAL_DOCKER:-false}" == "true" ]]; then
        start_services_manually
        return $?
    fi

    log_step "Starting all services"

    # Detect Ollama mode
    if [[ -n "${OLLAMA_BASE_URL:-}" ]]; then
        log_info "🌐 Remote Ollama mode DETECTED"
        log_info "   OLLAMA_BASE_URL: $OLLAMA_BASE_URL"
        log_info "   Local ollama container will NOT start (--scale ollama=0)"
        log_info "   ⚠️  If you bypass setup.sh, you MUST manually use: docker compose up --scale ollama=0"
        COMPOSE_OLLAMA_SCALE=("--scale" "ollama=0")
    else
        log_info "🏠 Local Ollama mode (default, zero-config)"
        log_info "   OLLAMA_BASE_URL: (empty, using local minder-ollama container)"
        COMPOSE_OLLAMA_SCALE=()
    fi

    log_info "① Security layer…"
    compose up -d "${SECURITY_SERVICES[@]}"
    sleep 5

    log_info "② Infrastructure (DB, cache, vector store, AI runtime)…"
    compose up -d "${CORE_SERVICES[@]}" "${COMPOSE_OLLAMA_SCALE[@]}"
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
# MANUAL DOCKER RUN MODE (for YAML validation error workaround)
# ─────────────────────────────────────────────────────────────

start_services_manually() {
    log_step "Starting services manually (docker run)"

    # Check if secrets exist
    if [[ ! -d "${SCRIPT_DIR}/.secrets" ]]; then
        log_error "Secrets not found. Run: ./setup.sh generate-secrets"
        exit 1
    fi

    # Create network if not exists
    if ! docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        log_detail "Creating network: ${NETWORK_NAME}"
        run docker network create "$NETWORK_NAME"
    fi

    # Load secrets
    local postgres_pass redis_pass rabbitmq_pass jwt_secret webui_key grafana_pass
    local influxdb_pass influxdb_token authelia_jwt authelia_enc

    postgres_pass=$(cat "${SCRIPT_DIR}/.secrets/postgres_password.secret")
    redis_pass=$(cat "${SCRIPT_DIR}/.secrets/redis_password.secret")
    rabbitmq_pass=$(cat "${SCRIPT_DIR}/.secrets/rabbitmq_password.secret")
    jwt_secret=$(cat "${SCRIPT_DIR}/.secrets/jwt_secret.secret")
    webui_key=$(cat "${SCRIPT_DIR}/.secrets/webui_secret_key.secret")
    grafana_pass=$(cat "${SCRIPT_DIR}/.secrets/grafana_password.secret")
    influxdb_pass=$(cat "${SCRIPT_DIR}/.secrets/influxdb_admin_password.secret")
    influxdb_token=$(cat "${SCRIPT_DIR}/.secrets/influxdb_token.secret")
    # authelia_jwt=$(cat "${SCRIPT_DIR}/.secrets/authelia_jwt_secret.secret")
    # authelia_enc=$(cat "${SCRIPT_DIR}/.secrets/authelia_storage_encryption_key.secret")

    # Core services
    log_info "① Starting core services (PostgreSQL, Redis, RabbitMQ)..."

    # PostgreSQL
    if ! container_running postgres; then
        if container_exists postgres; then
            log_detail "Removing existing PostgreSQL container..."
            run docker rm "$(container_name postgres)" 2>/dev/null || true
        fi
        log_detail "Starting PostgreSQL..."
        run docker run -d \
          --name "$(container_name postgres)" \
          --network "$NETWORK_NAME" \
          -v docker_postgres_data:/var/lib/postgresql \
          -v "${SCRIPT_DIR}/docker/services/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
          -v "${SCRIPT_DIR}/.secrets/postgres_password.secret:/run/secrets/postgres_password:ro" \
          -e POSTGRES_USER=minder \
          -e POSTGRES_MULTIPLE_DATABASES=tefas_db,weather_db,news_db,crypto_db \
          -e POSTGRES_DB=minder \
          -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
          --health-cmd="pg_isready -U minder -d minder" \
          --health-interval=10s \
          --health-timeout=5s \
          --health-retries=5 \
          "$(manual_image postgres)"
    fi

    # Wait for PostgreSQL
    wait_postgres_ready || true

    # Redis
    if ! container_running redis; then
        log_detail "Starting Redis..."
        run docker run -d \
          --name "$(container_name redis)" \
          --network "$NETWORK_NAME" \
          -v docker_redis_data:/data \
          -v "${SCRIPT_DIR}/.secrets/redis_password.secret:/run/secrets/redis_password:ro" \
          "$(manual_image redis)" \
          sh -c 'redis-server --appendonly yes --requirepass "$(cat /run/secrets/redis_password)" --masterauth "$(cat /run/secrets/redis_password)"'
    fi

    # RabbitMQ
    if ! container_running rabbitmq; then
        log_detail "Starting RabbitMQ..."
        run docker run -d \
          --name "$(container_name rabbitmq)" \
          --network "$NETWORK_NAME" \
          -v docker_rabbitmq_data:/var/lib/rabbitmq \
          -v "${SCRIPT_DIR}/.secrets/rabbitmq_password.secret:/run/secrets/rabbitmq_password:ro" \
          -v "${SCRIPT_DIR}/docker/services/rabbitmq/entrypoint.sh:/entrypoint.sh:ro" \
          -e RABBITMQ_CONFIG_FILE=/etc/rabbitmq/rabbitmq.conf \
          -e RABBITMQ_LOGS=- \
          -e RABBITMQ_LOG_LEVEL=info \
          -e RABBITMQ_DEFAULT_USER=minder \
          --entrypoint=/entrypoint.sh \
          --health-cmd="rabbitmq-diagnostics -q ping" \
          --health-interval=30s \
          --health-timeout=30s \
          --health-retries=3 \
          "$(manual_image rabbitmq)"
    fi

    sleep 5

    # Monitoring services
    log_info "② Starting monitoring services..."

    # Grafana
    if ! container_running grafana; then
        log_detail "Starting Grafana..."
        run docker run -d \
          --name "$(container_name grafana)" \
          --network "$NETWORK_NAME" \
          -v docker_grafana_data:/var/lib/grafana \
          -v "${SCRIPT_DIR}/docker/services/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro" \
          -v "${SCRIPT_DIR}/docker/services/grafana/datasources:/etc/grafana/provisioning/datasources:ro" \
          -v "${SCRIPT_DIR}/.secrets/grafana_password.secret:/run/secrets/grafana_password:ro" \
          -e GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_password \
          -e GF_SERVER_ROOT_URL=https://grafana.minder.local \
          -e GF_INSTALL_PLUGINS= \
          --health-cmd="wget --no-verbose --tries=1 --spider http://localhost:3000/api/health" \
          --health-interval=10s \
          --health-timeout=5s \
          --health-retries=5 \
          "$(manual_image grafana/grafana)"
    fi

    # InfluxDB
    if ! container_running influxdb; then
        log_detail "Starting InfluxDB..."
        run docker run -d \
          --name "$(container_name influxdb)" \
          --network "$NETWORK_NAME" \
          -v docker_influxdb_data:/var/lib/influxdb2 \
          -v "${SCRIPT_DIR}/.secrets/influxdb_admin_password.secret:/run/secrets/influxdb_admin_password:ro" \
          -v "${SCRIPT_DIR}/.secrets/influxdb_token.secret:/run/secrets/influxdb_token:ro" \
          -e DOCKER_INFLUXDB_INIT_MODE=setup \
          -e DOCKER_INFLUXDB_INIT_USERNAME=admin \
          -e DOCKER_INFLUXDB_INIT_ORG=minder \
          -e DOCKER_INFLUXDB_INIT_BUCKET=minder-metrics \
          -e DOCKER_INFLUXDB_INIT_RETENTION=30d \
          -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN_FILE=/run/secrets/influxdb_token \
          -e DOCKER_INFLUXDB_INIT_PASSWORD_FILE=/run/secrets/influxdb_admin_password \
          -e INFLUXDB_LOG_LEVEL=info \
          --health-cmd="influx ping" \
          --health-interval=10s \
          --health-timeout=5s \
          --health-retries=5 \
          "$(manual_image influxdb)"
    fi

    sleep 5

    # Application services
    log_info "③ Starting application services..."

    # API-Gateway
    if ! container_running api-gateway; then
        log_detail "Starting API-Gateway..."
        run docker run -d \
          --name "$(container_name api-gateway)" \
          --network "$NETWORK_NAME" \
          -p 8000:8000 \
          -e REDIS_HOST="$(container_name redis)" \
          -e REDIS_PORT=6379 \
          -e REDIS_PASSWORD="$redis_pass" \
          -e POSTGRES_HOST="$(container_name postgres)" \
          -e POSTGRES_PORT=5432 \
          -e POSTGRES_USER=minder \
          -e POSTGRES_PASSWORD="$postgres_pass" \
          -e POSTGRES_DB=minder \
          -e JWT_SECRET="$jwt_secret" \
          -e PLUGIN_REGISTRY_URL=http://$(container_name plugin-registry):8001 \
          -e RAG_PIPELINE_URL=http://$(container_name rag-pipeline):8004 \
          -e MODEL_MANAGEMENT_URL=http://$(container_name model-management):8005 \
          -e RATE_LIMIT_ENABLED=true \
          -e LOG_LEVEL=INFO \
          -e ENVIRONMENT=development \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:8000/health || exit 1" \
          --health-interval=30s \
          --health-timeout=10s \
          --health-retries=3 \
          minder/api-gateway:1.0.0
    fi

    # OpenWebUI
    if ! container_running openwebui; then
        log_detail "Starting OpenWebUI..."
        run docker run -d \
          --name "$(container_name openwebui)" \
          --network "$NETWORK_NAME" \
          -p 3000:8080 \
          -e WEBUI_SECRET_KEY="$webui_key" \
          -e JWT_SECRET="$jwt_secret" \
          -e GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D \
          -e OPENAI_API_KEY=${OPENAI_API_KEY:-} \
          -e TIKTOKEN_ENCODING_NAME=cl100k_base \
          -v docker_openwebui_data:/app/backend/data \
          -v "${SCRIPT_DIR}/docker/services/openwebui/functions.json:/app/config/functions.json:ro" \
          --restart unless-stopped \
          "$(manual_image ghcr.io/open-webui/open-webui)"
    fi

    # Schema Registry
    if ! container_running schema-registry; then
        log_detail "Starting Schema Registry..."
        run docker run -d \
          --name "$(container_name schema-registry)" \
          --network "$NETWORK_NAME" \
          -e QUARKUS_DATASOURCE_JDBC_URL=jdbc:postgresql://$(container_name postgres):5432/minder_schemaregistry \
          -e QUARKUS_DATASOURCE_USERNAME=minder \
          -e QUARKUS_DATASOURCE_PASSWORD="$postgres_pass" \
          -e REGISTRY_DATASOURCE_URL=jdbc:postgresql://$(container_name postgres):5432/minder_schemaregistry \
          -e REGISTRY_DATASOURCE_USERNAME=minder \
          -e REGISTRY_DATASOURCE_PASSWORD="$postgres_pass" \
          -e QUARKUS_DATASOURCE_DRIVER=org.postgresql.Driver \
          -e REGISTRY_DATASOURCE_DRIVER=org.postgresql.Driver \
          "$(manual_image apicurio/apicurio-registry-sql)"
    fi

    # RabbitMQ-Exporter
    if ! container_running rabbitmq-exporter; then
        log_detail "Starting RabbitMQ Exporter..."
        run docker run -d \
          --name "$(container_name rabbitmq-exporter)" \
          --network "$NETWORK_NAME" \
          -e RABBIT_USER=minder \
          -e RABBIT_PASSWORD="$rabbitmq_pass" \
          -e RABBIT_URL=http://minder:$rabbitmq_pass@$(container_name rabbitmq):15672 \
          -e PUBLISH_PORT=9419 \
          -e RABBIT_CAPABILITIES=sort,bert \
          --restart unless-stopped \
          "$(manual_image kbudde/rabbitmq-exporter)"
    fi

    sleep 5

    # Security & Proxy services
    log_info "④ Starting security and proxy services..."

    # Traefik
    if ! container_running traefik; then
        log_detail "Starting Traefik..."
        run docker run -d \
          --name "$(container_name traefik)" \
          --network "$NETWORK_NAME" \
          -p 8080:8080 \
          -p 8443:8443 \
          -p 80:80 \
          -p 443:443 \
          -v /var/run/docker.sock:/var/run/docker.sock:ro \
          -v "${SCRIPT_DIR}/docker/services/traefik/traefik.yml:/etc/traefik/traefik.yml:ro" \
          -v "${SCRIPT_DIR}/docker/services/traefik/dynamic:/etc/traefik/dynamic:ro" \
          --restart unless-stopped \
          "$(manual_image traefik)"
    fi

    # Authelia - DISABLED due to configuration issue
    # if ! container_running authelia; then
    #     log_detail "Starting Authelia..."
    #     run docker run -d \
    #       --name "$(container_name authelia)" \
    #       --network "$NETWORK_NAME" \
    #       -p 9091:9091 \
    #       -v "${SCRIPT_DIR}/.secrets:/secrets:ro" \
    #       -v "${SCRIPT_DIR}/docker/services/authelia/configuration.yml:/config/configuration.yml:ro" \
    #       -v "${SCRIPT_DIR}/docker/services/authelia/users_database.yml:/config/users_database.yml:ro" \
    #       -v docker_authelia_data:/config \
    #       -e AUTHELIA_STORAGE_POSTGRES_PASSWORD="$postgres_pass" \
    #       -e AUTHELIA_STORAGE_ENCRYPTION_KEY="$authelia_enc" \
    #       -e AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET="$authelia_jwt" \
    #       --health-cmd="curl -f http://localhost:9091 | grep 'OK' || exit 1" \
    #       --health-interval=10s \
    #       --health-timeout=5s \
    #       --health-retries=5 \
    #       authelia/authelia:4.38.7
    # fi
    #
    # sleep 5

    # Core databases & AI runtime
    log_info "⑤ Starting core databases and AI runtime..."

    # Neo4j
    if ! container_running neo4j; then
        log_detail "Starting Neo4j..."
        run docker run -d \
          --name "$(container_name neo4j)" \
          --network "$NETWORK_NAME" \
          -p 7474:7474 \
          -p 7687:7687 \
          -v docker_neo4j_data:/data \
          -e NEO4J_AUTH=neo4j/$(openssl rand -base64 16 | tr -d '=+/') \
          --health-cmd="curl -f http://localhost:7474 || exit 1" \
          --health-interval=10s \
          --health-timeout=5s \
          --health-retries=5 \
          "$(manual_image neo4j)"
    fi

    # Qdrant
    if ! container_running qdrant; then
        log_detail "Starting Qdrant..."
        run docker run -d \
          --name "$(container_name qdrant)" \
          --network "$NETWORK_NAME" \
          -p 6333:6333 \
          -v docker_qdrant_data:/qdrant/storage \
          "$(manual_image qdrant/qdrant)"
    fi

    # Ollama
    if ! container_running ollama; then
        log_detail "Starting Ollama..."
        run docker run -d \
          --name "$(container_name ollama)" \
          --network "$NETWORK_NAME" \
          -p 11434:11434 \
          -v docker_ollama_data:/root/.ollama \
          --restart unless-stopped \
          "$(manual_image ollama/ollama)"
    fi

    sleep 5

    # API Services
    log_info "⑥ Starting API microservices..."

    # Plugin Registry
    if ! container_running plugin-registry; then
        log_detail "Starting Plugin Registry..."
        run docker run -d \
          --name "$(container_name plugin-registry)" \
          --network "$NETWORK_NAME" \
          -p 8001:8001 \
          -e REDIS_HOST="$(container_name redis)" \
          -e REDIS_PORT=6379 \
          -e REDIS_PASSWORD="$redis_pass" \
          -e POSTGRES_HOST="$(container_name postgres)" \
          -e POSTGRES_PORT=5432 \
          -e POSTGRES_USER=minder \
          -e POSTGRES_PASSWORD="$postgres_pass" \
          -e POSTGRES_DB=minder \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:8001/health || exit 1" \
          --health-interval=30s \
          --health-timeout=10s \
          --health-retries=3 \
          minder/plugin-registry:1.0.0
    fi

    # Marketplace
    if ! container_running marketplace; then
        log_detail "Starting Marketplace..."
        run docker run -d \
          --name "$(container_name marketplace)" \
          --network "$NETWORK_NAME" \
          -p 8002:8002 \
          -e REDIS_HOST="$(container_name redis)" \
          -e REDIS_PORT=6379 \
          -e REDIS_PASSWORD="$redis_pass" \
          -e POSTGRES_HOST="$(container_name postgres)" \
          -e POSTGRES_PORT=5432 \
          -e POSTGRES_USER=minder \
          -e POSTGRES_PASSWORD="$postgres_pass" \
          -e POSTGRES_DB=minder \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:8002/health || exit 1" \
          --health-interval=30s \
          --health-timeout=10s \
          --health-retries=3 \
          minder/marketplace:1.0.0
    fi

    # Plugin State Manager
    if ! container_running plugin-state-manager; then
        log_detail "Starting Plugin State Manager..."
        run docker run -d \
          --name "$(container_name plugin-state-manager)" \
          --network "$NETWORK_NAME" \
          -p 8003:8003 \
          -e REDIS_HOST="$(container_name redis)" \
          -e REDIS_PORT=6379 \
          -e REDIS_PASSWORD="$redis_pass" \
          -e POSTGRES_HOST="$(container_name postgres)" \
          -e POSTGRES_PORT=5432 \
          -e POSTGRES_USER=minder \
          -e POSTGRES_PASSWORD="$postgres_pass" \
          -e POSTGRES_DB=minder \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:8003/health || exit 1" \
          --health-interval=30s \
          --health-timeout=10s \
          --health-retries=3 \
          minder/plugin-state-manager:1.0.0
    fi

    # RAG Pipeline
    if ! container_running rag-pipeline; then
        log_detail "Starting RAG Pipeline..."
        run docker run -d \
          --name "$(container_name rag-pipeline)" \
          --network "$NETWORK_NAME" \
          -p 8004:8004 \
          -e REDIS_HOST="$(container_name redis)" \
          -e REDIS_PORT=6379 \
          -e REDIS_PASSWORD="$redis_pass" \
          -e POSTGRES_HOST="$(container_name postgres)" \
          -e POSTGRES_PORT=5432 \
          -e POSTGRES_USER=minder \
          -e POSTGRES_PASSWORD="$postgres_pass" \
          -e POSTGRES_DB=minder \
          -e QDRANT_HOST="$(container_name qdrant)" \
          -e QDRANT_PORT=6333 \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:8004/health || exit 1" \
          --health-interval=30s \
          --health-timeout=10s \
          --health-retries=3 \
          minder/rag-pipeline:1.0.0
    fi

    # Model Management
    if ! container_running model-management; then
        log_detail "Starting Model Management..."
        run docker run -d \
          --name "$(container_name model-management)" \
          --network "$NETWORK_NAME" \
          -p 8005:8005 \
          -e REDIS_HOST="$(container_name redis)" \
          -e REDIS_PORT=6379 \
          -e REDIS_PASSWORD="$redis_pass" \
          -e POSTGRES_HOST="$(container_name postgres)" \
          -e POSTGRES_PORT=5432 \
          -e POSTGRES_USER=minder \
          -e POSTGRES_PASSWORD="$postgres_pass" \
          -e POSTGRES_DB=minder \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:8005/health || exit 1" \
          --health-interval=30s \
          --health-timeout=10s \
          --health-retries=3 \
          minder/model-management:1.0.0
    fi

    sleep 5

    # Monitoring stack
    log_info "⑦ Starting monitoring stack..."

    # Telegraf
    if ! container_running telegraf; then
        log_detail "Starting Telegraf..."
        run docker run -d \
          --name "$(container_name telegraf)" \
          --network "$NETWORK_NAME" \
          -v "${SCRIPT_DIR}/docker/services/telegraf/telegraf.conf:/etc/telegraf/telegraf.conf:ro" \
          -v /var/run/docker.sock:/var/run/docker.sock:ro \
          --restart unless-stopped \
          "$(manual_image telegraf)"
    fi

    # Prometheus
    if ! container_running prometheus; then
        log_detail "Starting Prometheus..."
        run docker run -d \
          --name "$(container_name prometheus)" \
          --network "$NETWORK_NAME" \
          -p 9090:9090 \
          -v "${SCRIPT_DIR}/docker/services/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
          -v docker_prometheus_data:/prometheus \
          --restart unless-stopped \
          --health-cmd="wget --no-verbose --tries=1 --spider http://localhost:9090/-/healthy" \
          --health-interval=10s \
          --health-timeout=5s \
          --health-retries=5 \
          "$(manual_image prom/prometheus)"
    fi

    # Alertmanager
    if ! container_running alertmanager; then
        log_detail "Starting Alertmanager..."
        run docker run -d \
          --name "$(container_name alertmanager)" \
          --network "$NETWORK_NAME" \
          -p 9093:9093 \
          -v "${SCRIPT_DIR}/docker/services/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" \
          -v docker_alertmanager_data:/alertmanager \
          --restart unless-stopped \
          "$(manual_image prom/alertmanager)"
    fi

    sleep 5

    # Exporters
    log_info "⑦ Starting metrics exporters..."

    # Blackbox Exporter
    if ! container_running blackbox-exporter; then
        log_detail "Starting Blackbox Exporter..."
        run docker run -d \
          --name "$(container_name blackbox-exporter)" \
          --network "$NETWORK_NAME" \
          -v "${SCRIPT_DIR}/docker/services/prometheus/blackbox.yml:/etc/blackbox/blackbox.yml:ro" \
          --restart unless-stopped \
          "$(manual_image prom/blackbox-exporter)"
    fi

    # Postgres Exporter
    if ! container_running postgres-exporter; then
        log_detail "Starting Postgres Exporter..."
        run docker run -d \
          --name "$(container_name postgres-exporter)" \
          --network "$NETWORK_NAME" \
          -e DATA_SOURCE_NAME="postgresql://minder:${postgres_pass}@$(container_name postgres):5432/minder?sslmode=disable" \
          --restart unless-stopped \
          "$(manual_image prometheuscommunity/postgres-exporter)"
    fi

    # Redis Exporter
    if ! container_running redis-exporter; then
        log_detail "Starting Redis Exporter..."
        run docker run -d \
          --name "$(container_name redis-exporter)" \
          --network "$NETWORK_NAME" \
          -e REDIS_ADDR="$(container_name redis):6379" \
          -e REDIS_PASSWORD="$redis_pass" \
          --restart unless-stopped \
          "$(manual_image oliver006/redis_exporter)"
    fi

    # cAdvisor
    if ! container_running cadvisor; then
        log_detail "Starting cAdvisor..."
        run docker run -d \
          --name "$(container_name cadvisor)" \
          --network "$NETWORK_NAME" \
          -v /:/rootfs:ro \
          -v /var/run:/var/run:ro \
          -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
          -v /var/lib/docker/:/var/lib/docker:ro \
          --restart unless-stopped \
          "$(manual_image gcr.io/cadvisor/cadvisor)"
    fi

    # Node Exporter
    if ! container_running node-exporter; then
        log_detail "Starting Node Exporter..."
        run docker run -d \
          --name "$(container_name node-exporter)" \
          --network "$NETWORK_NAME" \
          -v /proc:/host/proc:ro \
          -v /sys:/host/sys:ro \
          -v /:/rootfs:ro \
          --restart unless-stopped \
          "$(manual_image prom/node-exporter)"
    fi

    sleep 5

    # AI Services
    log_info "⑧ Starting AI enhancement services..."

    # TTS/STT Service
    if ! container_running tts-stt-service; then
        log_detail "Starting TTS/STT Service..."
        run docker run -d \
          --name "$(container_name tts-stt-service)" \
          --network "$NETWORK_NAME" \
          -p 8006:8006 \
          -e OLLAMA_URL=http://$(container_name ollama):11434 \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:8006/health || exit 1" \
          --health-interval=30s \
          --health-timeout=10s \
          --health-retries=3 \
          minder/tts-stt-service:1.0.0
    fi
    # Observability services
    log_info "⑧ Starting observability services..."

    # Jaeger
    if ! container_running jaeger; then
        log_detail "Starting Jaeger..."
        run docker run -d \
          --name "$(container_name jaeger)" \
          --network "$NETWORK_NAME" \
          -p 16686:16686 \
          -p 14268:14268 \
          -p 14250:14250 \
          -p 9411:9411 \
          -p 5778:5778 \
          --restart unless-stopped \
          "$(manual_image jaegertracing/all-in-one)"
    fi

    # OTEL Collector
    if ! container_running otel-collector; then
        log_detail "Starting OTEL Collector..."
        run docker run -d \
          --name "$(container_name otel-collector)" \
          --network "$NETWORK_NAME" \
          -p 18888:18888 \
          -p 4317:4317 \
          -p 4318:4318 \
          -v "${SCRIPT_DIR}/docker/services/otel-collector/otel-collector-config.yaml:/etc/otelcol/config.yaml:ro" \
          --restart unless-stopped \
          "$(manual_image otel/opentelemetry-collector)"
    fi

    # MinIO (Object Storage)
    if ! container_running minio; then
        log_detail "Starting MinIO..."
        run docker run -d \
          --name "$(container_name minio)" \
          --network "$NETWORK_NAME" \
          -p 9000:9000 \
          -p 9001:9001 \
          -v docker_minio_data:/data \
          -e MINIO_ROOT_USER=minioadmin \
          -e MINIO_ROOT_PASSWORD=$(cat "${SCRIPT_DIR}/.secrets/minio_root_password.secret") \
          --restart unless-stopped \
          --health-cmd="curl -f http://localhost:9000/minio/health/live" \
          --health-interval=10s \
          --health-timeout=5s \
          --health-retries=5 \
          "$(manual_image minio/minio)"
    fi

    log_success "All 31 services started manually"
    log_detail "Use MINDER_USE_MANUAL_DOCKER=true ./setup.sh stop to stop services"
}

stop_services_manually() {
    log_step "Stopping all manually started services"

    # Stop all minder containers
    local containers
    containers=$(docker ps -a --format '{{.Names}}' | grep "^${CONTAINER_PREFIX}-" || true)

    if [[ -z "$containers" ]]; then
        log_info "No containers found"
        return 0
    fi

    log_info "Stopping and removing containers..."
    for container in $containers; do
        log_detail "Stopping: $container"
        run docker stop "$container" 2>/dev/null || true
        log_detail "Removing: $container"
        run docker rm "$container" 2>/dev/null || true
    done

    # Remove networks if not in use
    if docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        run docker network rm "$NETWORK_NAME" 2>/dev/null \
            && log_success "Network '${NETWORK_NAME}' removed" \
            || log_detail "Network still in use"
    fi

    if docker network ls --format '{{.Name}}' | grep -q "^${MONITORING_NETWORK_NAME}$"; then
        run docker network rm "${MONITORING_NETWORK_NAME}" 2>/dev/null \
            && log_success "Network '${MONITORING_NETWORK_NAME}' removed" \
            || log_detail "Network still in use"
    fi

    if [[ "$CLEAN_DANGLING" == "true" ]]; then
        local reclaimed
        reclaimed="$(docker image prune -f | grep 'Total reclaimed' || echo 'unknown')"
        log_success "Dangling images pruned — ${reclaimed}"
    fi

    log_success "All services stopped and removed"
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


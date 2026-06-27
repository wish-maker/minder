# ─────────────────────────────────────────────────────────────
# NETWORK
# ─────────────────────────────────────────────────────────────

create_networks() {
    log_step "Setting up Docker networks"

    # Create main application network
    if docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        log_info "Network '${NETWORK_NAME}' already exists"
    else
        run docker network create "$NETWORK_NAME"
        log_success "Network '${NETWORK_NAME}' created"
    fi

    # Create monitoring network (for isolated monitoring zone)
    if docker network ls --format '{{.Name}}' | grep -q "^${MONITORING_NETWORK_NAME}$"; then
        log_info "Network '${MONITORING_NETWORK_NAME}' already exists"
    else
        run docker network create "${MONITORING_NETWORK_NAME}" --driver bridge --attachable
        log_success "Network '${MONITORING_NETWORK_NAME}' created"
    fi
}

# ─────────────────────────────────────────────────────────────
# DATABASE INITIALISATION
# ─────────────────────────────────────────────────────────────

readonly -a EXTRA_DATABASES=(minder_marketplace tefas_db weather_db news_db crypto_db)

initialize_database() {
    log_step "Initialising databases"

    compose up -d postgres
    wait_postgres_ready || exit 1

    log_info "Creating auxiliary databases…"
    for db in "${EXTRA_DATABASES[@]}"; do
        if docker exec "$(container_name postgres)" psql -U minder \
               -c "CREATE DATABASE ${db};" &>/dev/null 2>&1; then
            log_detail "Created: ${db}"
        else
            log_detail "Already exists: ${db}"
        fi
    done

    log_success "Database initialisation complete"
}

# ─────────────────────────────────────────────────────────────
# MINIO OBJECT STORAGE INITIALIZATION
# ─────────────────────────────────────────────────────────────

initialize_minio() {
    log_step "Initialising MinIO object storage"

    # Check if minio service exists in docker-compose.yml
    if ! grep -q "minio:" "$COMPOSE_FILE"; then
        log_info "MinIO service not defined in docker-compose.yml - skipping"
        return 0
    fi

    compose up -d minio
    wait_for_service "minio" "9000/minio/health/live" || exit 1

    log_info "Creating MinIO buckets…"

    # Define required buckets
    local buckets=(
        "rag-documents"
        "tts-artifacts"
        "fine-tuning-datasets"
        "model-checkpoints"
        "plugin-packages"
        "backup-archives"
    )

    # Wait for MinIO to be fully ready
    sleep 5

    # Install MinIO client if not available
    if ! docker exec minder-minio which mc &>/dev/null; then
        log_detail "Installing MinIO client..."
        docker exec minder-minio wget -q https://dl.min.io/client/mc/release/linux-amd64/mc -O /tmp/mc
        docker exec minder-minio chmod +x /tmp/mc
        docker exec minder-minio mv /tmp/mc /usr/local/bin/mc
    fi

    # Create buckets
    for bucket in "${buckets[@]}"; do
        if docker exec minder-minio mc ls mydata/"$bucket" &>/dev/null 2>&1; then
            log_detail "Already exists: $bucket"
        else
            if docker exec minder-minio mc mb mydata/"$bucket" &>/dev/null 2>&1; then
                log_detail "Created: $bucket"

                # Set public policy for buckets that need it
                case "$bucket" in
                    rag-documents|tts-artifacts|plugin-packages)
                        docker exec minder-minio mc anonymous set download mydata/"$bucket" &>/dev/null 2>&1
                        log_detail "Set public policy: $bucket"
                        ;;
                esac
            else
                log_warning "Failed to create bucket: $bucket"
            fi
        fi
    done

    log_success "MinIO initialisation complete"
}


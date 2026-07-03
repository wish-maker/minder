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
    wait_healthy "minio" "$TIMEOUT_SERVICES" || exit 1

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

    # mc already ships in the minio image (/usr/bin/mc) — no bootstrap needed.
    # The old block installed it via `wget` (absent from this image → 127 crash
    # under set -e) behind a `which mc` guard (`which` also absent → guard never
    # worked). Instead, configure the 'mydata' alias the bucket loop below relies
    # on: point it at the local server with the root creds from .env. (The default
    # 'local' alias is unauthenticated → Access Denied, so it can't be reused.)
    local minio_user minio_pass
    minio_user="$(_env_get MINIO_ROOT_USER)"
    minio_pass="$(_env_get MINIO_ROOT_PASSWORD)"
    if ! docker exec minder-minio mc alias set mydata \
            "http://localhost:9000" "$minio_user" "$minio_pass" &>/dev/null; then
        log_warn "Could not configure mc 'mydata' alias — skipping bucket creation"
        return 0
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
                log_warn "Failed to create bucket: $bucket"
            fi
        fi
    done

    log_success "MinIO initialisation complete"
}


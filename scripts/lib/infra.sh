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
}

# Counterpart to create_networks, for cmd_uninstall --purge. The network is
# declared `external: true` in docker-compose.yml, so `compose down -v` never
# removes it on its own — without this, it silently survives every purge.
remove_networks() {
    log_step "Removing Docker networks"

    if docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        run docker network rm "$NETWORK_NAME"
        log_success "Network '${NETWORK_NAME}' removed"
    else
        log_info "Network '${NETWORK_NAME}' already absent"
    fi
}

# One-time volume-name cleanup (#262): these 9 keys carried a redundant "docker_"
# prefix — Compose auto-prefixes every volume with the project name (CONTAINER_PREFIX)
# already, so the actual on-disk volumes were double-prefixed (e.g.
# "minder_docker_traefik_letsencrypt"). Old key:new key, matching the plain
# convention every other volume already uses. A plain indexed array (not an
# associative one) on purpose — associative-array key order isn't guaranteed in
# bash, and this order must match the Python port's dict order exactly for the
# behavior-parity gate (scripts/gate/infra_verify.sh).
readonly -a VOLUME_RENAMES=(
    "docker_traefik_letsencrypt:traefik_letsencrypt"
    "docker_traefik_logs:traefik_logs"
    "docker_otel-collector-data:otel_collector_data"
    "docker_plugins_data:plugins_data"
    "docker_models_data:models_data"
    "docker_models_cache:models_cache"
    "docker_prometheus_data:prometheus_data"
    "docker_grafana_data:grafana_data"
    "docker_alertmanager_data:alertmanager_data"
)

# Copies data from each old (project-prefixed) volume to its renamed counterpart
# before `compose up` ever gets a chance to create an empty volume under the new
# name — without this, a host that already has data under an old name (the Pi)
# would silently lose access to it the moment docker-compose.yml's volume keys
# changed. Idempotent (checks existence both sides) and safe to run on every
# start/restart. Never deletes the old volume — manual cleanup once confirmed good.
migrate_volume_names() {
    log_step "Checking for volume-name migrations"

    local migrated_any=false
    local pair old_key new_key old_name new_name
    for pair in "${VOLUME_RENAMES[@]}"; do
        old_key="${pair%%:*}"
        new_key="${pair##*:}"
        old_name="${CONTAINER_PREFIX}_${old_key}"
        new_name="${CONTAINER_PREFIX}_${new_key}"

        if ! docker volume ls --format '{{.Name}}' | grep -q "^${old_name}$"; then
            continue  # nothing to migrate
        fi
        if docker volume ls --format '{{.Name}}' | grep -q "^${new_name}$"; then
            continue  # already migrated
        fi

        log_info "Migrating volume '${old_name}' → '${new_name}'…"
        run docker volume create "$new_name"
        run docker run --rm -v "${old_name}:/from" -v "${new_name}:/to" \
            alpine sh -c "cp -a /from/. /to/"
        log_success "Migrated: ${old_key} → ${new_key}"
        migrated_any=true
    done

    if [[ "$migrated_any" == true ]]; then
        log_detail "Old volume(s) left in place — remove manually once the new ones look right."
    else
        log_info "No volume migrations needed"
    fi
}

# ─────────────────────────────────────────────────────────────
# DATABASE INITIALISATION
# ─────────────────────────────────────────────────────────────

# #294: minder_authelia/minder_schemaregistry were missing here — both are
# hardcoded, non-configurable database names (services/authelia/
# configuration.yml's `database: minder_authelia`; docker-compose.yml's
# schema-registry QUARKUS_DATASOURCE_JDBC_URL/REGISTRY_DATASOURCE_URL), so on
# a fresh install both containers fatally crashed on every single startup
# ("database ... does not exist") and were restarted by Docker's on-failure
# policy forever (confirmed live on the Pi: 835 and 363 restarts respectively).
readonly -a EXTRA_DATABASES=(minder_marketplace minder_authelia minder_schemaregistry tefas_db weather_db news_db crypto_db)

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

    # Cluster-wide default session timezone (#252): DEFAULT NOW() on a
    # TIMESTAMP (no tz) column casts the tz-aware "now" using the session's
    # `timezone` GUC — left at its OS default this stores local wall-clock
    # (e.g. TR time on the Pi), disagreeing with the naive-UTC values Python
    # writes (#239). ALTER SYSTEM + reload is idempotent and takes effect
    # immediately, so it's safe to run on every install/re-run, including
    # against clusters whose data directory predates this fix.
    # Two separate -c flags, NOT one semicolon-joined string: psql's simple
    # query protocol implicitly wraps a multi-statement -c string in one
    # transaction block, and ALTER SYSTEM cannot run inside a transaction
    # block (confirmed live — a single joined -c errors with exactly that).
    if docker exec "$(container_name postgres)" psql -U minder \
           -c "ALTER SYSTEM SET timezone TO 'UTC';" \
           -c "SELECT pg_reload_conf();" &>/dev/null 2>&1; then
        log_detail "Database timezone set to UTC"
    else
        log_detail "Could not set database timezone to UTC"
    fi

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
    # Match compose's `${MINIO_ROOT_USER:-minioadmin}`: empty/unset var → the
    # container runs as minioadmin, so mc must auth as that too, else `mc mb`
    # gets Access Denied and buckets silently fail (Pi clean-install, #8).
    minio_user="$(_env_get MINIO_ROOT_USER)"; minio_user="${minio_user:-minioadmin}"
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


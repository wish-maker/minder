# ─────────────────────────────────────────────────────────────
# SECRET GENERATION  (relocated from secrets.sh — sole consumer is the
# .env fill below; behavior unchanged)
# ─────────────────────────────────────────────────────────────

gen_secret() {
    local bytes="${1:-32}"
    if command -v openssl &>/dev/null; then
        openssl rand -hex "$bytes"
    else
        LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c $(( bytes * 2 ))
    fi
}

# ─────────────────────────────────────────────────────────────
# ENVIRONMENT SETUP
# ─────────────────────────────────────────────────────────────

# Authoritative secret-key set → "length[:format]". Smart-fill touches ONLY these
# keys; every other line (OLLAMA_BASE_URL, ACME_EMAIL, GPU vars, models, …) is left
# exactly as the user wrote it. Mirrors _validate_env's old required-keys list.
declare -A SECRET_SPEC=(
    [POSTGRES_PASSWORD]=32
    [REDIS_PASSWORD]=32
    [RABBITMQ_PASSWORD]=32
    [MINIO_ROOT_PASSWORD]=32
    [JWT_SECRET]=64
    [NEO4J_AUTH]="16:neo4j/"
    [INFLUXDB_TOKEN]=40
    [AUTHELIA_STORAGE_ENCRYPTION_KEY]=32
    [AUTHELIA_JWT_SECRET]=32
    [GRAFANA_PASSWORD]=32
    [WEBUI_SECRET_KEY]=32
)

# prepare_env — self-healing environment provisioning. Runs on install/start/restart.
#
#   root ./.env  = SINGLE SOURCE OF TRUTH (one per machine; gitignored; chmod 600).
#   docker/compose/.env (COMPOSE_ENV_FILE) = derived COPY that docker compose reads;
#                        regenerated from root .env every run, carries a DO-NOT-EDIT
#                        banner. COPY (not symlink) for Windows + Pi portability.
#
# Smart-fill is idempotent and SILENT when .env is already fully populated — this is
# what keeps the gate's start/stop/restart traces unchanged.
prepare_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        mkdir -p "$(dirname "$ENV_FILE")"
        if [[ -f "$ENV_EXAMPLE" ]]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            log_success "Created .env from .env.example"
        else
            log_info "No .env.example found — generating configuration"
            _write_default_env
        fi
    fi

    _fill_env_secrets               # heal MISSING/EMPTY/PLACEHOLDER secrets (backs up on change)
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    _sync_compose_env               # mirror root .env → docker/compose/.env (silent)
}

_write_default_env() {
    # Fallback: Only used when .env.example is missing
    # This should rarely happen as .env.example is in version control
    log_warn "No .env.example found — using legacy fallback (incomplete)"
    log_detail "Consider re-cloning repository or restoring .env.example"

    cat > "$ENV_FILE" << EOF
# Minder Platform — Environment Configuration (LEGACY FALLBACK)
# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# ⚠️  This is an INCOMPLETE fallback configuration!
#     Please restore .env.example from version control

# ── Core ────────────────────────────────────────────────────
ENVIRONMENT=development
LOG_LEVEL=INFO

# ── PostgreSQL ───────────────────────────────────────────────
POSTGRES_USER=minder
POSTGRES_PASSWORD=$(gen_secret 32)
POSTGRES_DB=minder

# ── Redis ────────────────────────────────────────────────────
REDIS_PASSWORD=$(gen_secret 32)

# ── RabbitMQ ─────────────────────────────────────────────────
RABBITMQ_PASSWORD=$(gen_secret 32)

# ── MinIO ─────────────────────────────────────────────────────
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=$(gen_secret 32)

# ── Auth & Security ──────────────────────────────────────────
JWT_SECRET=$(gen_secret 64)
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# ── Neo4j ────────────────────────────────────────────────────
NEO4J_AUTH=neo4j/$(gen_secret 16)

# ── InfluxDB ─────────────────────────────────────────────────
INFLUXDB_TOKEN=$(gen_secret 40)
INFLUXDB_ORG=minder
INFLUXDB_BUCKET=metrics

# ── Authelia ─────────────────────────────────────────────────
AUTHELIA_STORAGE_ENCRYPTION_KEY=$(gen_secret 32)
AUTHELIA_JWT_SECRET=$(gen_secret 32)

# ── Grafana ──────────────────────────────────────────────────
GRAFANA_ADMIN_USER=admin
GRAFANA_PASSWORD=$(gen_secret 32)

# ── OpenWebUI ────────────────────────────────────────────────
WEBUI_SECRET_KEY=$(gen_secret 32)
WEBUI_AUTH=true

# ── Traefik ───────────────────────────────────────────────────
ACME_EMAIL=admin@minder.local
TRAEFIK_TRUSTED_IPS=192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,127.0.0.1/32

# ── Ollama ───────────────────────────────────────────────────
OLLAMA_AUTOMATIC_PULL=true
OLLAMA_MODELS=llama3.2,nomic-embed-text
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# ── Models ─────────────────────────────────────────────────────
DEFAULT_BASE_MODEL=llama3.2

# ── TTS/STT ───────────────────────────────────────────────────
TTS_MODEL=tts_models/multilingual/multi-dataset/xtts_v2
STT_MODEL=base
TTS_DEVICE=cpu
TTS_COMPUTE_TYPE=int8
EOF
    log_success "Generated .env with secure random secrets (fallback mode)"
}

# Smart-fill: for each SECRET_SPEC key, generate a secret iff the value is MISSING,
# EMPTY, a CHANGEME-style placeholder, or (for prefixed formats) the bare prefix with
# no password. A REAL user-set value is left untouched — that is the "updatable"
# property. Backs up .env before any rewrite. SILENT no-op when nothing needs filling.
_fill_env_secrets() {
    local key spec format value
    local -a to_fill=()

    for key in "${!SECRET_SPEC[@]}"; do
        spec="${SECRET_SPEC[$key]}"
        format=""; [[ "$spec" == *:* ]] && format="${spec#*:}"

        if grep -qE "^${key}=" "$ENV_FILE"; then
            value="$(grep -E "^${key}=" "$ENV_FILE" | head -n1 | cut -d= -f2-)"
        else
            value="__MISSING__"
        fi

        if [[ "$value" == "__MISSING__" || -z "$value" ]] \
           || [[ "$value" =~ CHANGEME|REPLACE_ME|change-this-to|my-super-secret ]] \
           || { [[ -n "$format" ]] && [[ "$value" == "$format" ]]; }; then
            to_fill+=("$key")
        fi
    done

    (( ${#to_fill[@]} == 0 )) && return 0   # fully populated → silent no-op (gate-critical)

    # deterministic log/apply order (assoc-array iteration order is unspecified)
    mapfile -t to_fill < <(printf '%s\n' "${to_fill[@]}" | sort)

    # back up the source-of-truth BEFORE rewriting it
    local ts backup
    ts="$(date -u '+%Y%m%d-%H%M%S')"
    backup="$(dirname "$ENV_FILE")/.env.backup-${ts}"
    cp "$ENV_FILE" "$backup"
    log_detail "Backed up .env → $(basename "$backup")"

    local length new_secret
    for key in "${to_fill[@]}"; do
        spec="${SECRET_SPEC[$key]}"
        length="${spec%%:*}"
        format=""; [[ "$spec" == *:* ]] && format="${spec#*:}"
        new_secret="${format}$(gen_secret "$length")"

        if grep -qE "^${key}=" "$ENV_FILE"; then
            # '|' delimiter avoids clashing with the '/' in the neo4j/ prefix
            sed -i "s|^${key}=.*|${key}=${new_secret}|" "$ENV_FILE"
        else
            printf '%s=%s\n' "$key" "$new_secret" >> "$ENV_FILE"
        fi
        log_detail "✓ Generated secret for ${key}"
    done

    log_success "${#to_fill[@]} secret(s) generated/healed in .env"
}

# Mirror the source-of-truth root .env to the path docker compose reads
# (project-dir default = dirname COMPOSE_FILE). COPY (not symlink) for Windows + Pi
# portability; prepend a DO-NOT-EDIT banner. Silent — runs every prepare_env.
_sync_compose_env() {
    mkdir -p "$(dirname "$COMPOSE_ENV_FILE")"
    {
        printf '# ============================================================================\n'
        printf '# DO NOT EDIT — generated by setup.sh from the root .env (single source of truth).\n'
        printf '# Edit ./.env and re-run setup.sh (start/restart) to regenerate this file.\n'
        printf '# ============================================================================\n'
        cat "$ENV_FILE"
    } > "$COMPOSE_ENV_FILE"
    chmod 600 "$COMPOSE_ENV_FILE" 2>/dev/null || true
}

_env_get() {
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo ""
}


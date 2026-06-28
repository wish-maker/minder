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

setup_environment() {
    log_step "Setting up environment"

    if [[ -f "$ENV_FILE" ]]; then
        log_info ".env already exists — skipping generation"
        log_detail "Remove ${ENV_FILE} and re-run to regenerate secrets"
        _validate_env
        return 0
    fi

    mkdir -p "$(dirname "$ENV_FILE")"

    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        log_success "Copied .env from .env.example"
        _fill_env_secrets
    else
        log_info "No .env.example found — generating configuration"
        _write_default_env
    fi

    chmod 600 "$ENV_FILE"
    log_detail "Permissions set to 600 on .env"
    log_success "Environment ready"
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

_fill_env_secrets() {
    log_info "Replacing placeholder secrets with secure random values..."

    local changed=0
    local total=0

    while IFS= read -r line; do
        if [[ "$line" =~ ^([A-Z_]+)=(.+)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local value="${BASH_REMATCH[2]}"
            local needs_secret=false
            local secret_length=32
            local secret_format=""

            # Detect placeholder patterns (including embedded in description)
            if [[ "$value" =~ CHANGEME ]] || \
               [[ "$value" =~ REPLACE_ME ]] || \
               [[ "$value" =~ change-this-to ]] || \
               [[ "$value" =~ my-super-secret ]]; then
                needs_secret=true
            fi

            # Determine appropriate secret length based on key name
            case "$key" in
                JWT_SECRET)
                    secret_length=64
                    ;;
                INFLUXDB_TOKEN|INFLUXDB_ADMIN_TOKEN)
                    secret_length=40
                    ;;
                WEBUI_SECRET_KEY|AUTHELIA_*)
                    secret_length=32
                    ;;
                NEO4J_AUTH)
                    secret_format="neo4j/"
                    secret_length=16
                    ;;
            esac

            if $needs_secret; then
                total=$(( total + 1 ))
                local new_secret

                if [[ -n "$secret_format" ]]; then
                    new_secret="${secret_format}$(gen_secret "$secret_length")"
                else
                    new_secret="$(gen_secret "$secret_length")"
                fi

                # Use different delimiter for sed to avoid conflicts
                sed -i "s|^${key}=.*|${key}=${new_secret}|" "$ENV_FILE"
                log_detail "✓ Generated secret for ${key}"
                changed=$(( changed + 1 ))
            fi
        fi
    done < "$ENV_FILE"

    if (( changed > 0 )); then
        log_success "${changed} placeholder secret(s) replaced with secure random values"
    else
        log_detail "No placeholder secrets found (all secrets already set)"
    fi
}

_validate_env() {
    log_info "Validating environment configuration..."

    # Core required keys that MUST be set
    local required_keys=(
        POSTGRES_USER
        POSTGRES_PASSWORD
        REDIS_PASSWORD
        RABBITMQ_PASSWORD
        MINIO_ROOT_PASSWORD
        JWT_SECRET
        NEO4J_AUTH
        INFLUXDB_TOKEN
        AUTHELIA_STORAGE_ENCRYPTION_KEY
        AUTHELIA_JWT_SECRET
        GRAFANA_PASSWORD
        WEBUI_SECRET_KEY
    )

    local missing=()
    local insecure=()

    for key in "${required_keys[@]}"; do
        if ! grep -qE "^${key}=.+" "$ENV_FILE"; then
            missing+=("$key")
        else
            # Check for placeholder/insecure values
            local value
            value=$(grep -E "^${key}=" "$ENV_FILE" | cut -d= -f2-)
            if [[ "$value" =~ ^CHANGEME ]] || \
               [[ "$value" =~ ^REPLACE_ME ]] || \
               [[ "$value" =~ ^change-this ]] || \
               [[ "$value" =~ my-super-secret ]] || \
               [[ "$value" == "admin" ]] || \
               [[ "$value" =~ ^password$ ]]; then
                insecure+=("$key")
            fi
        fi
    done

    if (( ${#missing[@]} > 0 )); then
        log_warn "Missing required keys in .env: ${missing[*]}"
        log_detail "Run: sed -i 's/^CHANGEME.*/$(gen_secret 32)/' $ENV_FILE"
        return 1
    fi

    if (( ${#insecure[@]} > 0 )); then
        log_warn "Insecure placeholder values found: ${insecure[*]}"
        log_detail "Replace them with: ./setup.sh setup-env (re-runs secret generation)"
        log_detail "Or manually: openssl rand -hex 32"
    fi

    # Check file permissions
    local perm
    perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%A' "$ENV_FILE" 2>/dev/null || echo '???')"
    if [[ "$perm" != "600" ]] && [[ "$perm" != "0600" ]]; then
        log_warn ".env permissions are ${perm} — should be 600"
        log_detail "Run: chmod 600 $ENV_FILE"
    fi

    log_detail "Environment validation complete"
    return 0
}

_env_get() {
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo ""
}


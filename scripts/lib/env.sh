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
    [AUTHELIA_SESSION_SECRET]=32
    [AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET]=32
    [GRAFANA_PASSWORD]=32
    [WEBUI_SECRET_KEY]=32
    # registry→marketplace AI-tool sync auth (X-Service-Token); one value → both
    # containers. Was skipped → stayed empty → sync silently 401'd (#227).
    [SERVICE_SYNC_TOKEN]=32
    # Authelia OIDC provider (#<issue>): hmac_secret signs Authelia's own internal
    # OIDC session/consent tokens; MINDER_OIDC_CLIENT_SECRET is the plaintext
    # confidential-client secret shared between Authelia's configuration.yml
    # ($plaintext$ prefix) and api-gateway's token-exchange call.
    [AUTHELIA_IDENTITY_PROVIDERS_OIDC_HMAC_SECRET]=32
    [MINDER_OIDC_CLIENT_SECRET]=32
)

# prepare_env — self-healing environment provisioning. Runs on install/start/restart.
#
#   root ./.env  = SINGLE SOURCE OF TRUTH (one per machine; gitignored; chmod 600).
#   docker/.env (COMPOSE_ENV_FILE) = derived COPY that docker compose reads;
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
    _ensure_docker_gid              # record the docker group gid as DOCKER_GID (#11, silent)
    chmod 600 "$ENV_FILE" 2>/dev/null || true
    _sync_compose_env               # mirror root .env → docker/.env (silent)
    _ensure_oidc_issuer_key         # generate Authelia's OIDC signing key once (#<issue>, silent)
    _render_authelia_config         # substitute it into configuration.rendered.yml (#<issue>, silent)
}

_ensure_oidc_issuer_key() {
    # Generate Authelia's OIDC token-signing RSA key on first run (#<issue>).
    # Unlike the SECRET_SPEC values above, Authelia's jwks.key config wants
    # real PEM, not a bare token, so this gets its own file rather than an
    # .env entry — under docker/services/authelia/secrets/, matching the
    # repo's existing bare `secrets/` .gitignore rule, never committed, same
    # as .env itself. Left alone on every subsequent run: regenerating it
    # after Authelia has issued tokens against the old key silently
    # invalidates every active session with no user-facing recovery story.
    local key_path="${SCRIPT_DIR}/docker/services/authelia/secrets/oidc_issuer.pem"
    [[ -f "$key_path" ]] && return 0
    mkdir -p "$(dirname "$key_path")"
    if command -v openssl &>/dev/null; then
        if openssl genrsa -out "$key_path" 2048 &>/dev/null; then
            chmod 600 "$key_path" 2>/dev/null || true
            log_success "Generated Authelia OIDC issuer key"
        else
            log_warn "Could not generate OIDC issuer key"
        fi
    else
        # No host openssl (preflight only warns, doesn't hard-fail on this) —
        # fall back to a throwaway container the same way the Python setup
        # path always does, since docker itself is guaranteed present.
        local pem
        pem="$(docker run --rm alpine:3.20 sh -c \
            "apk add --no-cache openssl >/dev/null 2>&1 && openssl genrsa 2048" \
            2>/dev/null)"
        if [[ "$pem" == "-----BEGIN"* ]]; then
            printf '%s\n' "$pem" > "$key_path"
            chmod 600 "$key_path" 2>/dev/null || true
            log_success "Generated Authelia OIDC issuer key (via docker)"
        else
            log_warn "openssl not found and docker fallback failed — cannot generate OIDC issuer key"
        fi
    fi
}

_render_authelia_config() {
    # Substitute the real OIDC issuer key into Authelia's config (#<issue>).
    # configuration.yml (git-tracked) holds a stable placeholder instead of
    # key material; this writes configuration.rendered.yml (gitignored) with
    # the placeholder replaced by the actual PEM, reindented as a YAML
    # literal block scalar at the key's nesting depth (8 spaces + 2,
    # matching that line's own indentation in the source).
    #
    # Plain text substitution, deliberately NOT Authelia's own Go-template
    # config-file filter: that route was tried first and abandoned after
    # proving too fragile to debug reliably (raw double-curly-brace regions
    # get parsed everywhere in the file, including inside YAML comments, and
    # the engine's own error line numbers didn't correspond to anything
    # inspectable). Runs on every prepare_env() call, unlike key generation
    # above — cheap, and needs to stay in sync if the source template
    # changes, whereas the key itself must NOT be regenerated once issued.
    local src="${SCRIPT_DIR}/docker/services/authelia/configuration.yml"
    local dst="${SCRIPT_DIR}/docker/services/authelia/configuration.rendered.yml"
    local key_path="${SCRIPT_DIR}/docker/services/authelia/secrets/oidc_issuer.pem"
    [[ -f "$src" ]] || return 0
    [[ -f "$key_path" ]] || return 0
    local indented
    indented="$(sed 's/^/          /' "$key_path")"
    awk -v pem="$indented" '
        { gsub(/__MINDER_OIDC_ISSUER_KEY_PEM__/, "|\n" pem); print }
    ' "$src" > "$dst"
}

_ensure_docker_gid() {
    # Record the host 'docker' group gid in .env as DOCKER_GID (#11) so compose's
    # `group_add: ${DOCKER_GID:-0}` actually grants telegraf/plugin-registry read
    # access to a root:docker docker.sock when non-root. Silent; no-op when there's
    # no docker group (dev hosts — the :-0 fallback covers those) or already set.
    local gid; gid="$(getent group docker 2>/dev/null | cut -d: -f3)"
    [[ -z "$gid" ]] && return 0
    [[ "$(_env_get DOCKER_GID)" == "$gid" ]] && return 0
    if grep -qE "^DOCKER_GID=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s/^DOCKER_GID=.*/DOCKER_GID=${gid}/" "$ENV_FILE"
    else
        printf 'DOCKER_GID=%s\n' "$gid" >> "$ENV_FILE"
    fi
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
AUTHELIA_SESSION_SECRET=$(gen_secret 32)
AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET=$(gen_secret 32)
AUTHELIA_IDENTITY_PROVIDERS_OIDC_HMAC_SECRET=$(gen_secret 32)
MINDER_OIDC_CLIENT_SECRET=$(gen_secret 32)

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
# Set by 'ollama-mode failover <url>' (host:port of the external primary). Non-empty
# means failover mode: the ollama-router prefers this primary and falls back to the
# internal container. Empty means internal/external mode (see OLLAMA_BASE_URL).
OLLAMA_FAILOVER_PRIMARY=

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

    # #57: refuse to auto-(re)generate secrets while a provisioned stack is running —
    # doing so would mirror new secrets into docker/.env and let start_services
    # recreate the stateful cores, desyncing live services (redis/minio re-read their
    # password on recreate). Only reached when secrets ACTUALLY need filling; the
    # normal full-.env path returned above. Override: MINDER_ALLOW_SECRET_REGEN=1.
    local _live=""
    case "${MINDER_ALLOW_SECRET_REGEN,,}" in
        1|true|yes) : ;;
        *) local _svc
           for _svc in postgres redis neo4j rabbitmq minio; do
               container_running "$_svc" && { _live="$_svc"; break; }
           done ;;
    esac
    if [[ -n "$_live" ]]; then
        local _joined; _joined="$(printf '%s, ' "${to_fill[@]}")"; _joined="${_joined%, }"
        log_error "Refusing to regenerate .env secrets — a provisioned stack is already running (${_live})"
        log_detail "Missing/placeholder secrets: ${_joined}"
        log_detail "Regenerating would desync live services (redis/minio re-read their password on recreate)."
        log_detail "Fix: restore the real secrets into .env, or set MINDER_ALLOW_SECRET_REGEN=1 to rotate intentionally."
        exit 1
    fi

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


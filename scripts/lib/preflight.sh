# ─────────────────────────────────────────────────────────────
# PREREQUISITE CHECK
# ─────────────────────────────────────────────────────────────

check_prerequisites() {
    log_step "Checking prerequisites"
    local failed=0

    if ! command -v docker &>/dev/null; then
        log_error "Docker not installed → https://docs.docker.com/get-docker/"
        failed=1
    else
        log_detail "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
    fi

    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose v2 not available → https://docs.docker.com/compose/install/"
        failed=1
    else
        log_detail "Compose $(docker compose version --short 2>/dev/null || echo 'v2')"
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker daemon is not running — start Docker Desktop or dockerd"
        failed=1
    fi

    if ! command -v openssl &>/dev/null; then
        log_warn "openssl not found — falling back to /dev/urandom for secret generation"
    fi

    if ! command -v curl &>/dev/null; then
        log_warn "curl not found — smart version resolution will be skipped"
        SKIP_VERSION_CHECK=true
    fi

    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "Compose file not found: ${COMPOSE_FILE}"
        failed=1
    else
        log_detail "Compose file: ${COMPOSE_FILE}"
    fi

    local free_gb
    free_gb="$(df -BG "$SCRIPT_DIR" 2>/dev/null | awk 'NR==2{gsub("G",""); print $4}' || echo 999)"
    if (( free_gb < 10 )); then
        log_warn "Low disk space: ${free_gb}GB free (recommend ≥10GB)"
    else
        log_detail "Disk space: ${free_gb}GB free"
    fi

    local busy_ports=()
    for port in 5432 6379 8000 8001 8002 8003 8004 8005 8006 8007 8080 8081 8086 9090 9091 3000; do
        if 2>/dev/null >/dev/tcp/127.0.0.1/"$port"; then
            if ! docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                busy_ports+=("$port")
            fi
        fi
    done
    if (( ${#busy_ports[@]} > 0 )); then
        log_warn "Ports already in use (may conflict): ${busy_ports[*]}"
    fi

    if (( failed )); then
        log_error "Prerequisites failed — cannot continue"
        exit 1
    fi

    log_success "All prerequisites satisfied"
}

# ─────────────────────────────────────────────────────────────
# GPU VALIDATION (Phase 3)
# ─────────────────────────────────────────────────────────────

validate_gpu_environment() {
    log_info "Validating GPU environment for AI acceleration..."

    # Check if NVIDIA Container Toolkit is available
    if ! docker run --rm --gpus all nvidia/cuda:11.0-base-ubuntu20.04 nvidia-smi &>/dev/null; then
        log_warn "NVIDIA Container Toolkit not found"
        log_detail "GPU acceleration disabled - falling back to CPU mode"
        log_detail "Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide"
        export GPU_AVAILABLE=false
        return 0
    fi

    # Validate GPU availability
    local gpu_count
    gpu_count=$(nvidia-smi --query-gpu=count --format=csv,noheader 2>/dev/null || echo "0")

    if [[ "$gpu_count" -eq 0 ]]; then
        log_warn "No NVIDIA GPUs detected - falling back to CPU mode"
        export GPU_AVAILABLE=false
        return 0
    fi

    log_detail "GPUs detected: $gpu_count"

    # Get GPU model information
    local gpu_model
    gpu_model=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 2>/dev/null || echo "Unknown")
    log_detail "GPU Model: $gpu_model"

    # Get GPU memory information
    local gpu_memory
    gpu_memory=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1 2>/dev/null || echo "Unknown")
    log_detail "GPU Memory: $gpu_memory"

    export GPU_AVAILABLE=true
    log_success "GPU validation passed - hardware acceleration enabled"
    return 0
}

# ─────────────────────────────────────────────────────────────
# DYNAMIC CONFIGURATION VALIDATION (Phase 4)
# ─────────────────────────────────────────────────────────────

configure_traefik_access_mode() {
    local mode
    mode="$(_env_get "ACCESS_MODE")"
    mode="${mode:-local}"

    log_info "Configuring Traefik access mode: $mode"

    local traefik_dynamic_dir="${SCRIPT_DIR}/docker/services/traefik/dynamic"

    # Disable all access mode configs first
    local config_file
    for config_file in "${traefik_dynamic_dir}"/access-mode-*.yml; do
        if [[ -f "$config_file" ]]; then
            mv "$config_file" "${config_file}.disabled" 2>/dev/null || true
        fi
    done

    # Enable the selected access mode config
    local target_config="${traefik_dynamic_dir}/access-mode-${mode}.yml.disabled"
    if [[ -f "$target_config" ]]; then
        mv "$target_config" "${target_config%.disabled}"
        log_success "Enabled Traefik config: access-mode-${mode}.yml"
    else
        log_warn "Traefik config not found: access-mode-${mode}.yml"
        log_detail "Using default middleware configuration"
    fi

    return 0
}

validate_access_mode() {
    local mode
    mode="$(_env_get "ACCESS_MODE")"
    mode="${mode:-local}"  # Default to local if not set

    log_info "Validating Access Mode configuration..."

    case "$mode" in
        local)
            log_detail "Access Mode: LOCAL (localhost only)"
            log_detail "Services accessible only on 127.0.0.1"
            export TRAEFIK_ACCESS_MODE="local"
            ;;
        vpn)
            log_detail "Access Mode: VPN (LAN/VPN subnets)"
            log_detail "Services accessible via VPN with enhanced security"
            log_detail "Allowed CIDRs: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16"
            export TRAEFIK_ACCESS_MODE="vpn"
            ;;
        public)
            log_detail "Access Mode: PUBLIC (internet-facing)"
            log_detail "Services accessible via internet with DDoS protection"
            log_detail "WARNING: Ensure SSL certificates and firewall rules are configured"
            export TRAEFIK_ACCESS_MODE="public"
            ;;
        *)
            log_error "Invalid ACCESS_MODE: $mode"
            log_detail "Valid options: local, vpn, public"
            log_detail "Fix: Set ACCESS_MODE in $ENV_FILE"
            return 1
            ;;
    esac

    # Configure Traefik dynamic files based on access mode
    configure_traefik_access_mode

    log_success "Access Mode validation passed: $mode"
    return 0
}

validate_ai_compute_mode() {
    local mode
    mode="$(_env_get "AI_COMPUTE_MODE")"
    mode="${mode:-internal}"  # Default to internal if not set

    log_info "Validating AI Compute Mode configuration..."

    case "$mode" in
        internal)
            log_detail "AI Compute Mode: INTERNAL (local Ollama)"
            log_detail "Using local Docker Ollama service: minder-ollama:11434"
            export AI_ENDPOINT_STRATEGY="local"
            export AI_LOCAL_OLLAMA_URL="http://minder-ollama:11434"
            export AI_ENABLE_FALLBACK="false"
            ;;
        external)
            local external_url
            external_url="$(_env_get "EXTERNAL_GPU_NODE_URL")"
            if [[ -z "$external_url" ]]; then
                log_error "AI_COMPUTE_MODE=external requires EXTERNAL_GPU_NODE_URL"
                log_detail "Fix: Set EXTERNAL_GPU_NODE_URL in $ENV_FILE"
                log_detail "Example: http://gpu-node.example.com:11434"
                return 1
            fi
            log_detail "AI Compute Mode: EXTERNAL (remote GPU node)"
            log_detail "Routing AI requests to: $external_url"
            export AI_ENDPOINT_STRATEGY="external"
            export AI_LAN_OLLAMA_URL="$external_url"
            export AI_ENABLE_FALLBACK="false"
            ;;
        hybrid)
            local external_url
            external_url="$(_env_get "EXTERNAL_GPU_NODE_URL")"
            if [[ -z "$external_url" ]]; then
                log_warn "AI_COMPUTE_MODE=hybrid recommended EXTERNAL_GPU_NODE_URL"
                log_detail "Proceeding with local-only mode (no external fallback)"
                external_url="http://minder-ollama:11434"
            fi
            log_detail "AI Compute Mode: HYBRID (local + external fallback)"
            log_detail "Primary: local Ollama (minder-ollama:11434)"
            log_detail "Fallback: $external_url"
            export AI_ENDPOINT_STRATEGY="hybrid"
            export AI_LOCAL_OLLAMA_URL="http://minder-ollama:11434"
            export AI_LAN_OLLAMA_URL="$external_url"
            export AI_ENABLE_FALLBACK="true"
            export AI_FALLBACK_TIMEOUT_MS="5000"
            ;;
        *)
            log_error "Invalid AI_COMPUTE_MODE: $mode"
            log_detail "Valid options: internal, external, hybrid"
            log_detail "Fix: Set AI_COMPUTE_MODE in $ENV_FILE"
            return 1
            ;;
    esac

    log_success "AI Compute Mode validation passed: $mode"
    return 0
}

validate_compute_resource_profile() {
    local profile
    profile="$(_env_get "COMPUTE_RESOURCE_PROFILE")"
    profile="${profile:-medium}"  # Default to medium if not set

    log_info "Validating Compute Resource Profile..."

    case "$profile" in
        low)
            log_detail "Resource Profile: LOW (development)"
            log_detail "CPU limits: 1 core, Memory: 2GB per service"
            export COMPUTE_CPU_LIMIT="1.0"
            export COMPUTE_MEMORY_LIMIT="2g"
            ;;
        medium)
            log_detail "Resource Profile: MEDIUM (staging)"
            log_detail "CPU limits: 2 cores, Memory: 4GB per service"
            export COMPUTE_CPU_LIMIT="2.0"
            export COMPUTE_MEMORY_LIMIT="4g"
            ;;
        high)
            log_detail "Resource Profile: HIGH (production)"
            log_detail "CPU limits: 4 cores, Memory: 8GB per service"
            export COMPUTE_CPU_LIMIT="4.0"
            export COMPUTE_MEMORY_LIMIT="8g"
            ;;
        enterprise)
            log_detail "Resource Profile: ENTERPRISE (GPU-accelerated)"
            log_detail "CPU limits: 8 cores, Memory: 16GB per service + GPU passthrough"
            export COMPUTE_CPU_LIMIT="8.0"
            export COMPUTE_MEMORY_LIMIT="16g"
            if [[ "$GPU_AVAILABLE" == "true" ]]; then
                log_detail "GPU acceleration: ENABLED"
            else
                log_warn "GPU acceleration: DISABLED (no NVIDIA GPU detected)"
            fi
            ;;
        *)
            log_error "Invalid COMPUTE_RESOURCE_PROFILE: $profile"
            log_detail "Valid options: low, medium, high, enterprise"
            return 1
            ;;
    esac

    log_success "Resource Profile validation passed: $profile"
    return 0
}


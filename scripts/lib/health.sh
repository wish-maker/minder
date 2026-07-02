run_health_checks() {
    local json_mode=false
    [[ "${1:-}" == "--json" ]] && json_mode=true

    local results=()

    # Get the actual server IP for better reporting (cross-platform)
    local server_ip
    if command hostname &>/dev/null; then
        # Try hostname -I (Linux), fall back to hostname -i (macOS/BSD), then hostname (Windows)
        # || true to prevent exit on non-zero exit codes (set -e)
        server_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
        [[ -z "$server_ip" ]] && server_ip="$(hostname -i 2>/dev/null | awk '{print $1}' || true)"
        [[ -z "$server_ip" ]] && server_ip="$(hostname 2>/dev/null || true)"
    fi
    [[ -z "$server_ip" ]] && server_ip="localhost"  # Fallback to localhost

    _check_endpoint() {
        local name="$1" path="$2"
        local container_name="${CONTAINER_PREFIX}-${name}"
        local port="${path%%/*}"
        local health_path="${path#*/}"
        [[ "$health_path" == "$port" ]] && health_path="/health"

        # Check if container is running first
        if ! container_running "$name"; then
            results+=("${name}:error:container not running")
            [[ "$json_mode" == false ]] && echo -e "  ${RED}✗${NC} ${name}  (container not running)"
            return
        fi

        # Use docker exec for health checks (works with internal networks)
        local internal_url="http://localhost:${port}${health_path}"
        # Add slash between port and path if needed
        [[ "$health_path" != /* ]] && health_path="/${health_path}"
        local display_url="http://${server_ip}:${port}${health_path}"

        # Special case for InfluxDB v3 (requires auth for HTTP endpoints)
        if [[ "$name" == "influxdb" ]]; then
            if 2>/dev/null >/dev/tcp/127.0.0.1/"$port"; then
                results+=("${name}:ok:${display_url}")
                [[ "$json_mode" == false ]] && echo -e "  ${GREEN}✓${NC} ${name}  ${DIM}${display_url}${NC}  ${DIM}(TCP port check)${NC}"
            else
                results+=("${name}:warn:${display_url}")
                [[ "$json_mode" == false ]] && echo -e "  ${YELLOW}⚠${NC} ${name}  ${DIM}${display_url}  (not yet reachable)${NC}"
            fi
            return
        fi

        # Use direct HTTP request from host (more reliable than docker exec)
        if curl -sf --max-time 3 "$display_url" &>/dev/null; then
            results+=("${name}:ok:${display_url}")
            [[ "$json_mode" == false ]] && echo -e "  ${GREEN}✓${NC} ${name}  ${DIM}${display_url}${NC}"
        else
            results+=("${name}:warn:${display_url}")
            [[ "$json_mode" == false ]] && echo -e "  ${YELLOW}⚠${NC} ${name}  ${DIM}${display_url}  (not yet reachable)${NC}"
        fi
    }

    if [[ "$json_mode" == false ]]; then
        section "🔍  Health Check"
        echo -e "${BOLD}Core APIs${NC}"
    fi

    for svc in "${API_SERVICES[@]}"; do
        [[ -v "SERVICE_PORTS[$svc]" ]] && _check_endpoint "$svc" "${SERVICE_PORTS[$svc]}"
    done

    [[ "$json_mode" == false ]] && echo -e "\n${BOLD}Monitoring${NC}"
    for svc in prometheus grafana influxdb traefik rabbitmq; do
        [[ -v "SERVICE_PORTS[$svc]" ]] && _check_endpoint "$svc" "${SERVICE_PORTS[$svc]}"
    done

    [[ "$json_mode" == false ]] && echo -e "\n${BOLD}AI Services${NC}"
    for svc in openwebui tts-stt-service; do
        [[ -v "SERVICE_PORTS[$svc]" ]] && _check_endpoint "$svc" "${SERVICE_PORTS[$svc]}"
    done

    local ok_count=0 warn_count=0
    for r in "${results[@]}"; do
        [[ "$r" == *":ok:"*   ]] && ok_count=$(( ok_count + 1 ))
        [[ "$r" == *":warn:"* ]] && warn_count=$(( warn_count + 1 ))
    done

    if [[ "$json_mode" == true ]]; then
        echo "{"
        echo "  \"timestamp\": \"$(date -u +%FT%TZ)\","
        echo "  \"ok\": ${ok_count},"
        echo "  \"warn\": ${warn_count},"
        echo "  \"services\": ["
        local first=true
        for r in "${results[@]}"; do
            local name="${r%%:*}"; local rest="${r#*:}"; local status="${rest%%:*}"; local url="${rest#*:}"
            [[ "$first" == false ]] && echo ","
            printf '    {"name":"%s","status":"%s","url":"%s"}' "$name" "$status" "$url"
            first=false
        done
        echo ""
        echo "  ]"
        echo "}"
        return
    fi

    echo ""
    if (( warn_count == 0 )); then
        log_success "${ok_count}/${#results[@]} endpoints healthy 🎉"
    else
        log_warn "${ok_count}/${#results[@]} endpoints reachable — ${warn_count} still starting"
        log_detail "Re-check: ./${SCRIPT_NAME} status"
    fi
}

# ─────────────────────────────────────────────────────────────
# OLLAMA MODEL DOWNLOAD
# ─────────────────────────────────────────────────────────────

download_ollama_models() {
    section "🤖  AI Model Download"

    # Remote/native Ollama: the local container is scaled to 0 (see start_services),
    # so there's nothing to pull into and docker-exec would just burn TIMEOUT_OLLAMA.
    # Mirrors docker/compose/ollama/init-models.sh:12.
    if [[ -n "${OLLAMA_BASE_URL:-}" ]]; then
        log_info "🌐 Remote/native Ollama mode (OLLAMA_BASE_URL set) — skipping in-container model pull"
        log_detail "Pull models on the native host, e.g.:  ollama pull llama3.2 && ollama pull nomic-embed-text"
        return 0
    fi

    spinner_start "Waiting for Ollama daemon…"
    local elapsed=0
    while (( elapsed < TIMEOUT_OLLAMA )); do
        if docker exec "$(container_name ollama)" ollama list &>/dev/null 2>&1; then
            spinner_stop; log_success "Ollama is ready"; break
        fi
        sleep 3; elapsed=$(( elapsed + 3 ))
    done

    if (( elapsed >= TIMEOUT_OLLAMA )); then
        spinner_stop
        log_warn "Ollama did not start within ${TIMEOUT_OLLAMA}s — skipping model pull"
        log_detail "Pull later:  docker exec $(container_name ollama) ollama pull <model>"
        return 0
    fi

    local auto_pull; auto_pull="$(_env_get OLLAMA_AUTOMATIC_PULL)"
    if [[ "${auto_pull:-true}" != "true" ]]; then
        log_info "OLLAMA_AUTOMATIC_PULL=false — skipping"
        return 0
    fi

    local model_list; model_list="$(_env_get OLLAMA_MODELS)"
    model_list="${model_list:-llama3.2,nomic-embed-text}"

    IFS=',' read -ra models <<< "$model_list"
    log_info "Pulling ${#models[@]} model(s): ${models[*]}"

    local success=0
    for model in "${models[@]}"; do
        model="$(echo "$model" | xargs)"
        [[ -z "$model" ]] && continue

        spinner_start "Pulling ${model}…"
        if run timeout 300 docker exec "$(container_name ollama)" ollama pull "$model" &>/dev/null 2>&1; then
            spinner_stop; log_success "${model}"
            success=$(( success + 1 ))
        else
            spinner_stop; log_warn "${model} — failed or timed out"
        fi
    done

    local installed
    installed="$(docker exec "$(container_name ollama)" ollama list 2>/dev/null | tail -n +2 | wc -l | xargs || echo 0)"
    log_success "${installed} model(s) available"
    docker exec "$(container_name ollama)" ollama list 2>/dev/null | tail -n +2 \
        | while IFS= read -r line; do log_detail "$line"; done
}


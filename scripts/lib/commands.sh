# ─────────────────────────────────────────────────────────────
# MIGRATE
# ─────────────────────────────────────────────────────────────

cmd_migrate() {
    local target="${1:-head}"
    section "🗄  Database Migration  (target: ${target})"

    if ! container_running postgres; then
        log_error "PostgreSQL is not running. Start services first."
        exit 1
    fi

    local -a migration_services=(api-gateway marketplace plugin-registry rag-pipeline model-management)

    for svc in "${migration_services[@]}"; do
        if container_running "$svc"; then
            log_info "Running migrations in ${svc}…"
            if run docker exec "$(container_name "$svc")" \
                   alembic upgrade "$target" 2>&1 | tee -a "$LOG_FILE"; then
                log_success "${svc} — migrations applied"
            else
                log_warn "${svc} — migration failed (check logs)"
            fi
        else
            log_detail "${svc} — not running, skipping"
        fi
    done

    log_success "Migration run complete"
}

# ─────────────────────────────────────────────────────────────
# OLLAMA MODE SWITCH  (ergonomic .env flip — does NOT restart)
# ─────────────────────────────────────────────────────────────
# internal            → OLLAMA_BASE_URL= (empty): platform-managed ollama container.
# external [url]       → OLLAMA_BASE_URL=<url> (default host.docker.internal:11434):
#                        reach ollama at a URL (same-host daemon OR a remote host).
# Surgically rewrites ONLY the OLLAMA_BASE_URL line in root .env (the single source of
# truth; outside SECRET_SPEC so smart-fill never touches it). Prints a restart hint —
# does NOT restart. start_services/download_ollama_models read this back from .env.
cmd_ollama_mode() {
    local mode="${1:-}" url="${2:-}"
    local default_url="http://host.docker.internal:11434"
    local new_url

    case "$mode" in
        internal) new_url="" ;;
        external)
            new_url="${url:-$default_url}"
            if ! [[ "$new_url" =~ ^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/.*)?$ ]]; then
                log_error "Invalid Ollama URL: '${new_url}'"
                log_detail "Expected a full URL, e.g. ${default_url} or http://192.168.1.50:11434"
                log_detail ".env was NOT changed."
                exit 1
            fi
            ;;
        *)
            log_error "Usage: ./${SCRIPT_NAME} ollama-mode internal|external [url]"
            log_detail "  internal        platform-managed ollama container (OLLAMA_BASE_URL empty)"
            log_detail "  external [url]  reach ollama at a URL (default ${default_url})"
            exit 1
            ;;
    esac

    [[ -f "$ENV_FILE" ]] || { log_error "No .env at ${ENV_FILE} — run ./${SCRIPT_NAME} install first."; exit 1; }

    local before after repl
    before="$(_env_get OLLAMA_BASE_URL)"
    repl="${new_url//&/\\&}"                       # escape sed replacement metachar
    if grep -qE "^OLLAMA_BASE_URL=" "$ENV_FILE"; then
        sed -i "s|^OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=${repl}|" "$ENV_FILE"
    else
        printf 'OLLAMA_BASE_URL=%s\n' "$new_url" >> "$ENV_FILE"
    fi
    after="$(_env_get OLLAMA_BASE_URL)"

    local label
    [[ -z "$new_url" ]] && label="internal (platform-managed container)" || label="external (${new_url})"
    if [[ "$before" == "$after" ]]; then
        log_info "Ollama mode already ${label} — .env unchanged."
    else
        log_success "Ollama mode → ${label}"
        log_detail "OLLAMA_BASE_URL: '${before}' → '${after}'"
    fi
    log_warn "Run  ./${SCRIPT_NAME} restart  to apply (recreates services + re-mirrors .env)."
}

# ─────────────────────────────────────────────────────────────
# BACKUP
# ─────────────────────────────────────────────────────────────

cmd_backup() {
    local ts; ts="$(date +%Y%m%d-%H%M%S)"
    local dest="${BACKUP_DIR}/minder-${ts}"
    mkdir -p "$dest"

    section "💾  Platform Backup  →  ${dest}"

    if [[ -f "$ENV_FILE" ]]; then
        cp "$ENV_FILE" "${dest}/env.backup"
        chmod 600 "${dest}/env.backup"
        log_success ".env backed up"
    else
        log_warn ".env not found"
    fi

    if container_running postgres; then
        spinner_start "Dumping PostgreSQL…"
        if docker exec "$(container_name postgres)" \
               pg_dumpall -U minder 2>/dev/null > "${dest}/postgres.sql"; then
            spinner_stop
            log_success "PostgreSQL  ($(du -sh "${dest}/postgres.sql" | cut -f1))"
        else
            spinner_stop; log_warn "PostgreSQL dump failed"
        fi
    else
        log_warn "PostgreSQL not running — skipped"
    fi

    if container_running neo4j; then
        spinner_start "Dumping Neo4j…"
        local neo4j_dump="${dest}/neo4j.dump"
        if run docker exec "$(container_name neo4j)" \
               neo4j-admin database dump neo4j \
               --to-stdout 2>/dev/null > "$neo4j_dump"; then
            spinner_stop
            log_success "Neo4j  ($(du -sh "$neo4j_dump" | cut -f1))"
        else
            spinner_stop; log_warn "Neo4j dump failed"
        fi
    else
        log_warn "Neo4j not running — skipped"
    fi

    if container_running influxdb; then
        spinner_start "Backing up InfluxDB…"
        local influx_token; influx_token="$(_env_get INFLUXDB_ADMIN_TOKEN)"
        if [[ -n "$influx_token" ]]; then
            if run docker exec "$(container_name influxdb)" \
                   influx backup /tmp/influx-backup \
                   --token "$influx_token" &>/dev/null 2>&1; then
                run docker cp "$(container_name influxdb):/tmp/influx-backup" "${dest}/influxdb/"
                spinner_stop; log_success "InfluxDB backed up"
            else
                spinner_stop; log_warn "InfluxDB backup failed"
            fi
        else
            spinner_stop; log_warn "INFLUXDB_ADMIN_TOKEN not set — skipping InfluxDB backup"
        fi
    else
        log_warn "InfluxDB not running — skipped"
    fi

    if container_running qdrant; then
        spinner_start "Snapshotting Qdrant storage…"
        if run docker exec "$(container_name qdrant)" \
               tar czf /tmp/qdrant-backup.tar.gz /qdrant/storage 2>/dev/null && \
           run docker cp "$(container_name qdrant):/tmp/qdrant-backup.tar.gz" \
               "${dest}/qdrant.tar.gz"; then
            spinner_stop
            log_success "Qdrant  ($(du -sh "${dest}/qdrant.tar.gz" | cut -f1))"
        else
            spinner_stop; log_warn "Qdrant snapshot failed"
        fi
    else
        log_warn "Qdrant not running — skipped"
    fi

    if container_running rabbitmq; then
        spinner_start "Backing up RabbitMQ definitions…"
        if run docker exec "$(container_name rabbitmq)" \
               rabbitmqctl export_definitions /tmp/rabbitmq-defs.json 2>/dev/null && \
           run docker cp "$(container_name rabbitmq):/tmp/rabbitmq-defs.json" \
               "${dest}/rabbitmq-definitions.json"; then
            spinner_stop
            log_success "RabbitMQ definitions backed up"
        else
            spinner_stop; log_warn "RabbitMQ definitions export failed"
        fi
    else
        log_warn "RabbitMQ not running — skipped"
    fi

    spinner_start "Compressing backup archive…"
    local archive="${BACKUP_DIR}/minder-${ts}.tar.gz"
    if tar czf "$archive" -C "$BACKUP_DIR" "minder-${ts}" 2>/dev/null; then
        rm -rf "$dest"
        spinner_stop
        log_success "Archive: ${archive}  ($(du -sh "$archive" | cut -f1))"
    else
        spinner_stop
        log_warn "Compression failed — uncompressed backup kept at ${dest}"
    fi

    local count
    count="$(find "$BACKUP_DIR" -maxdepth 1 -name 'minder-*.tar.gz' | wc -l | xargs)"
    if (( count > 7 )); then
        find "$BACKUP_DIR" -maxdepth 1 -name 'minder-*.tar.gz' \
            | sort | head -n $(( count - 7 )) \
            | xargs rm -f
        log_detail "Pruned old backups (keeping last 7)"
    fi

    log_success "Backup complete"
}

# ─────────────────────────────────────────────────────────────
# RESTORE
# ─────────────────────────────────────────────────────────────

cmd_restore() {
    local archive="${1:-}"

    if [[ -z "$archive" ]]; then
        echo -e "\n${BOLD}Available backups:${NC}"
        local i=0
        local -a backup_files=()
        while IFS= read -r f; do
            i=$(( i + 1 ))
            backup_files+=("$f")
            local size; size="$(du -sh "$f" | cut -f1)"
            local ts; ts="$(basename "$f" .tar.gz | sed 's/minder-//')"
            printf "  ${CYAN}[%d]${NC}  %s  ${DIM}%s${NC}\n" "$i" "$ts" "$size"
        done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'minder-*.tar.gz' | sort -r)

        if (( i == 0 )); then
            log_error "No backups found in ${BACKUP_DIR}"
            exit 1
        fi

        if [[ "$INTERACTIVE" == "true" ]]; then
            printf "\nSelect backup [1-%d]: " "$i"
            read -r choice
            archive="${backup_files[$(( choice - 1 ))]}"
        else
            log_error "No backup archive specified. Usage: ./${SCRIPT_NAME} restore <archive.tar.gz>"
            exit 1
        fi
    fi

    [[ ! -f "$archive" ]] && { log_error "File not found: ${archive}"; exit 1; }

    section "♻️   Restore  ←  $(basename "$archive")"
    log_warn "This will OVERWRITE current data. Services must be stopped."

    if [[ "$INTERACTIVE" == "true" ]]; then
        printf "Continue? [y/N] "
        read -r confirm
        [[ "${confirm,,}" != "y" ]] && { log_info "Restore cancelled."; return 0; }
    fi

    local tmp_dir; tmp_dir="$(mktemp -d)"
    spinner_start "Extracting archive…"
    tar xzf "$archive" -C "$tmp_dir"
    spinner_stop
    local restore_dir; restore_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -1)"

    if [[ -f "${restore_dir}/env.backup" ]]; then
        cp "${restore_dir}/env.backup" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        log_success ".env restored"
    fi

    if ! container_running postgres; then
        compose up -d postgres
        wait_postgres_ready
    fi

    if [[ -f "${restore_dir}/postgres.sql" ]]; then
        spinner_start "Restoring PostgreSQL…"
        if docker exec -i "$(container_name postgres)" \
               psql -U minder -f - < "${restore_dir}/postgres.sql" &>/dev/null 2>&1; then
            spinner_stop; log_success "PostgreSQL restored"
        else
            spinner_stop; log_warn "PostgreSQL restore had errors (partial restore possible)"
        fi
    fi

    if [[ -f "${restore_dir}/qdrant.tar.gz" ]] && container_running qdrant; then
        spinner_start "Restoring Qdrant…"
        docker cp "${restore_dir}/qdrant.tar.gz" "$(container_name qdrant):/tmp/"
        docker exec "$(container_name qdrant)" \
            tar xzf /tmp/qdrant-backup.tar.gz -C / 2>/dev/null
        spinner_stop; log_success "Qdrant restored"
    fi

    if [[ -f "${restore_dir}/rabbitmq-definitions.json" ]] && container_running rabbitmq; then
        spinner_start "Restoring RabbitMQ definitions…"
        docker cp "${restore_dir}/rabbitmq-definitions.json" "$(container_name rabbitmq):/tmp/rabbitmq-defs.json"
        if docker exec "$(container_name rabbitmq)" \
               rabbitmqctl import_definitions /tmp/rabbitmq-defs.json 2>/dev/null; then
            spinner_stop; log_success "RabbitMQ definitions restored"
        else
            spinner_stop; log_warn "RabbitMQ definitions restore had errors"
        fi
    fi

    rm -rf "$tmp_dir"
    log_success "Restore complete — restart services: ./${SCRIPT_NAME} start"
}

# ─────────────────────────────────────────────────────────────
# DOCTOR  — deep diagnostics  (now includes version drift)
# ─────────────────────────────────────────────────────────────

cmd_doctor() {
    section "🩺  System Diagnostics"

    local issues=0

    echo -e "${BOLD}Docker${NC}"
    log_detail "Version: $(docker --version)"
    log_detail "Compose: $(docker compose version --short 2>/dev/null || echo 'n/a')"

    local docker_mem
    docker_mem="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
    local docker_mem_gb=$(( docker_mem / 1073741824 ))
    if (( docker_mem_gb < 4 )); then
        log_warn "Docker has only ${docker_mem_gb}GB RAM (recommend ≥4GB for Ollama)"
        issues=$(( issues + 1 ))
    else
        log_detail "Docker RAM: ${docker_mem_gb}GB ✓"
    fi

    echo -e "\n${BOLD}Disk${NC}"
    local free_gb
    free_gb="$(df -BG "$SCRIPT_DIR" 2>/dev/null | awk 'NR==2{gsub("G",""); print $4}' || echo 999)"
    if (( free_gb < 10 )); then
        log_warn "Low disk space: ${free_gb}GB free"
        issues=$(( issues + 1 ))
    else
        log_detail "Free space: ${free_gb}GB ✓"
    fi

    echo -e "\n${BOLD}Environment (.env)${NC}"
    if [[ ! -f "$ENV_FILE" ]]; then
        log_warn ".env not found — run install first"
        issues=$(( issues + 1 ))
    else
        local perm; perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%A' "$ENV_FILE" 2>/dev/null || echo '???')"
        if [[ "$perm" != "600" ]] && [[ "$perm" != "0600" ]]; then
            log_warn ".env permissions are ${perm} — should be 600"
            issues=$(( issues + 1 ))
        else
            log_detail "Permissions: ${perm} ✓"
        fi

        local weak=0
        while IFS='=' read -r key val; do
            [[ "$key" =~ ^#  ]] && continue
            [[ -z "$val"     ]] && continue
            if [[ "$val" =~ ^(admin|password|secret|changeme|replace_me|minder)$ ]]; then
                log_warn "Weak value detected for ${key}"
                weak=$(( weak + 1 ))
                issues=$(( issues + 1 ))
            fi
        done < "$ENV_FILE"
        (( weak == 0 )) && log_detail "No obvious weak secrets ✓"
    fi

    echo -e "\n${BOLD}Port Availability${NC}"
    local -a ports=(5432 6379 8000 8001 8002 8003 8004 8005 8006 8007 8080 8081 8086 9090 9091 3000)
    for port in "${ports[@]}"; do
        if 2>/dev/null >/dev/tcp/127.0.0.1/"$port"; then
            if docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                log_detail ":${port} — in use by Minder ✓"
            else
                log_warn ":${port} — in use by another process"
                issues=$(( issues + 1 ))
            fi
        else
            log_detail ":${port} — free ✓"
        fi
    done

    echo -e "\n${BOLD}Container Health${NC}"
    local unhealthy_containers
    unhealthy_containers="$(docker ps --filter 'health=unhealthy' \
        --format '{{.Names}}' 2>/dev/null | grep "^${CONTAINER_PREFIX}-" || true)"
    if [[ -n "$unhealthy_containers" ]]; then
        log_warn "Unhealthy containers:"
        echo "$unhealthy_containers" | while IFS= read -r c; do log_detail "  $c"; done
        issues=$(( issues + 1 ))
    else
        local running
        running="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
        log_detail "${running} containers running, none unhealthy ✓"
    fi

    echo -e "\n${BOLD}Docker Volumes${NC}"
    local dangling_volumes
    dangling_volumes="$(docker volume ls -q --filter dangling=true 2>/dev/null | wc -l | xargs)"
    if (( dangling_volumes > 5 )); then
        log_warn "${dangling_volumes} dangling volumes (run: docker volume prune)"
    else
        log_detail "Dangling volumes: ${dangling_volumes} ✓"
    fi

    # ── Version drift check ──────────────────────────────────
    echo -e "\n${BOLD}Image Version Drift${NC}"
    if [[ "$SKIP_VERSION_CHECK" == "true" ]]; then
        log_warn "Version check skipped (curl unavailable or SKIP_VERSION_CHECK=1)"
    else
        log_info "Querying registries for newer compatible versions…"
        version_drift_report false
        # Count drift as issues
        local drift_count
        drift_count="$(version_drift_report false 2>/dev/null | grep -c '→\|AVAILABLE' || echo 0)"
        (( drift_count > 0 )) && issues=$(( issues + 1 )) || true
    fi

    echo ""
    if (( issues == 0 )); then
        log_success "No issues found — system looks healthy 🎉"
    else
        log_warn "${issues} issue(s) found — review warnings above"
    fi
}

# ─────────────────────────────────────────────────────────────
# UPDATE  — pull latest compatible images, rebuild, rolling restart
# ─────────────────────────────────────────────────────────────

cmd_update() {
    local check_only=false
    [[ "${1:-}" == "--check" ]] && check_only=true

    if [[ "$check_only" == "true" ]]; then
        section "🔍  Update Check  (no changes will be made)"
        log_info "Querying registries…"
        version_drift_report false
        return 0
    fi

    section "🔄  Update Platform"

    # Pull with smart version resolution
    pull_all_images

    log_info "Rebuilding custom Minder images…"
    run compose build --pull --no-cache 2>&1 | tee -a "$LOG_FILE" | grep -E 'Step|Successfully|ERROR' || true

    log_info "Performing rolling restart…"
    for svc in "${SECURITY_SERVICES[@]}" "${CORE_SERVICES[@]}" "${API_SERVICES[@]}" \
               "${MONITORING_SERVICES[@]}" "${AI_SERVICES[@]}"; do
        if container_running "$svc"; then
            run compose up -d --no-deps "$svc"
            log_detail "${svc} restarted"
            sleep 2
        fi
    done

    log_success "Update complete — run './${SCRIPT_NAME} status' to verify"
}

# ─────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────

cmd_status() {
    local json_mode=false
    [[ "${1:-}" == "--json" ]] && json_mode=true

    if [[ "$json_mode" == true ]]; then
        run_health_checks --json
        return
    fi

    section "📊  Minder Platform Status"

    local total healthy unhealthy starting
    total="$(    docker ps --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
    healthy="$(  docker ps --filter 'health=healthy'   --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
    unhealthy="$(docker ps --filter 'health=unhealthy' --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
    starting="$( docker ps --filter 'health=starting'  --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"

    echo -e "${BOLD}Summary${NC}  total=${total}  ${GREEN}healthy=${healthy}${NC}  ${YELLOW}starting=${starting}${NC}  ${RED}unhealthy=${unhealthy}${NC}"
    echo ""

    echo -e "${BOLD}Containers${NC}"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null \
        | grep -E "NAMES|${CONTAINER_PREFIX}-" | head -30

    echo ""
    echo -e "${BOLD}Resource Usage${NC}"
    docker stats --no-stream \
        --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" 2>/dev/null \
        | grep -E "NAME|${CONTAINER_PREFIX}-" | head -20

    echo ""
    run_health_checks
}

# ─────────────────────────────────────────────────────────────
# STOP
# ─────────────────────────────────────────────────────────────

cmd_stop() {
    log_step "Stopping all services"

    compose_monitoring down

    if docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        run docker network rm "$NETWORK_NAME" 2>/dev/null \
            && log_success "Network '${NETWORK_NAME}' removed" \
            || log_warn "Network not removed (may still be in use)"
    fi

    if [[ "$CLEAN_DANGLING" == "true" ]]; then
        local reclaimed
        reclaimed="$(docker image prune -f | grep 'Total reclaimed' || echo 'unknown')"
        log_success "Dangling images pruned — ${reclaimed}"
    fi

    log_success "All services stopped"
}

# ─────────────────────────────────────────────────────────────
# START / RESTART
# ─────────────────────────────────────────────────────────────

cmd_start() {
    check_prerequisites

    # Self-heal env + mirror root .env → docker/compose/.env before anything reads it.
    # Silent no-op when .env is already fully populated (keeps behavior gate clean).
    prepare_env

    # Phase 3: Validate GPU environment for AI acceleration
    validate_gpu_environment

    # Phase 4: Validate dynamic configuration
    validate_access_mode
    validate_ai_compute_mode
    validate_compute_resource_profile

    # Auto-regenerate docker-compose.yml if needed
    if should_regenerate_compose; then
        log_info "Auto-regenerating docker-compose.yml from version specs..."
        cmd_regenerate_compose
    fi

    create_networks
    start_services
    wait_for_services
    run_health_checks
}

cmd_restart() {
    cmd_stop
    sleep 3
    cmd_start
}

# ─────────────────────────────────────────────────────────────
# UNINSTALL
# ─────────────────────────────────────────────────────────────

cmd_uninstall() {
    local purge=false
    [[ "${1:-}" == "--purge" ]] && purge=true

    if [[ "$purge" == true ]]; then
        echo -e "${RED}${BOLD}"
        echo "  ┌─────────────────────────────────────────────────────┐"
        echo "  │  ⚠  DESTRUCTIVE OPERATION — CANNOT BE UNDONE  ⚠    │"
        echo "  │  All services AND data volumes will be deleted.     │"
        echo "  └─────────────────────────────────────────────────────┘"
        echo -e "${NC}"

        if [[ "$INTERACTIVE" == "true" ]]; then
            printf "Type ${BOLD}DELETE${NC} to confirm: "
            read -r confirm
            [[ "$confirm" != "DELETE" ]] && { log_info "Uninstall cancelled."; return 0; }
        fi

        log_warn "Removing all services, networks, and volumes…"
        compose_monitoring down -v --remove-orphans
        log_success "Full uninstall complete"
    else
        log_info "Stopping services (data volumes are preserved)"
        compose_monitoring down
        log_success "Services stopped — data preserved"
        log_detail "To also delete data: ./${SCRIPT_NAME} uninstall --purge"
    fi
}

# ─────────────────────────────────────────────────────────────
# LOGS
# ─────────────────────────────────────────────────────────────

cmd_logs() {
    local service="${1:-}" lines="${2:-100}"

    if [[ -n "$service" ]]; then
        local cname; cname="$(container_name "$service")"
        if docker ps --format '{{.Names}}' | grep -q "^${cname}$"; then
            log_info "Streaming ${service} logs (Ctrl+C to exit)…"
            docker logs -f --tail "$lines" "$cname"
        else
            log_error "No running container: ${cname}"
            log_detail "Running containers:"
            docker ps --format '  {{.Names}}' | grep "^  ${CONTAINER_PREFIX}-" || echo "  (none)"
            return 1
        fi
    else
        log_info "Streaming all service logs (Ctrl+C to exit)…"
        compose logs -f --tail 50
    fi
}

# ─────────────────────────────────────────────────────────────
# SHELL
# ─────────────────────────────────────────────────────────────

cmd_shell() {
    local service="${1:-}"

    if [[ -z "$service" ]]; then
        echo -e "${BOLD}Running containers:${NC}"
        docker ps --format '  {{.Names}}' | grep "^  ${CONTAINER_PREFIX}-" \
            | sed "s/  ${CONTAINER_PREFIX}-/  /" || echo "  (none)"
        echo ""
        if [[ "$INTERACTIVE" == "true" ]]; then
            printf "Container name (without '${CONTAINER_PREFIX}-'): "
            read -r service
        else
            log_error "Specify a service: ./${SCRIPT_NAME} shell <service>"
            exit 1
        fi
    fi

    local cname; cname="$(container_name "$service")"
    if ! docker ps --format '{{.Names}}' | grep -q "^${cname}$"; then
        log_error "Container not running: ${cname}"
        exit 1
    fi

    local shell="bash"
    docker exec -it "$cname" bash --version &>/dev/null || shell="sh"

    log_info "Opening ${shell} in ${cname}  (exit to return)"
    docker exec -it "$cname" "$shell"
}

# ─────────────────────────────────────────────────────────────
# FULL INSTALL
# ─────────────────────────────────────────────────────────────

cmd_install() {
    clear
    echo -e "${BOLD}${CYAN}"
    echo "  ╔══════════════════════════════════════════════════════════╗"
    echo "  ║         Minder Platform — Automated Setup               ║"
    printf "  ║                   Version %-30s║\n" "${SCRIPT_VERSION}"
    echo "  ╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}  ⚠  DRY RUN MODE — no changes will be made${NC}\n"
    fi

    progress_init 10   # one extra step for image resolution

    progress_next "Checking prerequisites";    check_prerequisites
    progress_next "Setting up environment";    prepare_env
    progress_next "Creating Docker network";   create_networks
    progress_next "Resolving & pulling images";pull_all_images
    progress_next "Initialising databases";    initialize_database
    progress_next "Initialising object storage"; initialize_minio
    progress_next "Starting services";         start_services
    progress_next "Waiting for services";      wait_for_services
    progress_next "Downloading AI models";     download_ollama_models
    progress_next "Running migrations";        cmd_migrate "head"
    progress_next "Health checks";             run_health_checks

    print_success_banner
}


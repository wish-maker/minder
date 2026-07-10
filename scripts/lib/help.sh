# ─────────────────────────────────────────────────────────────
# SUCCESS BANNER
# ─────────────────────────────────────────────────────────────

print_success_banner() {
    echo ""
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║${NC}         ${BOLD}🎉  Minder Platform v${SCRIPT_VERSION} — Ready!  🎉${NC}          ${BOLD}${GREEN}║${NC}"
    echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    echo -e "${BOLD}${MAGENTA}🔐 Security${NC}"
    echo -e "   Traefik Dashboard  →  ${CYAN}http://localhost:8081${NC}"
    echo -e "   ${YELLOW}Auth: register via POST /v1/auth/register on the API Gateway (JWT).${NC}"
    echo -e "   ${YELLOW}Authelia SSO is currently disabled (see issue #15).${NC}"

    echo ""
    echo -e "${BOLD}${MAGENTA}📍 Core APIs${NC}"
    local api_names=("API Gateway" "Plugin Registry" "Marketplace" "State Manager" "RAG Pipeline" "Model Mgmt" "Graph-RAG")
    local api_ports=(8000       8001              8002          8003             8004           8005         8008)
    for i in "${!api_names[@]}"; do
        printf "   %-20s →  ${CYAN}http://localhost:%s${NC}\n" "${api_names[$i]}" "${api_ports[$i]}"
    done

    echo ""
    echo -e "${BOLD}${MAGENTA}🤖 AI Services${NC}"
    echo -e "   OpenWebUI           →  ${CYAN}via Traefik (chat.minder.local)${NC}"
    echo -e "   TTS / STT           →  ${CYAN}http://localhost:8006${NC}"

    echo ""
    echo -e "${BOLD}${MAGENTA}📊 Monitoring${NC}"
    echo -e "   Prometheus          →  ${CYAN}http://localhost:9090${NC}"
    echo -e "   Grafana             →  ${CYAN}http://localhost:3000${NC}"
    echo -e "   InfluxDB            →  ${CYAN}http://localhost:8086${NC}"

    echo ""
    echo -e "${BOLD}${MAGENTA}🔧 Commands${NC}"
    echo -e "   ${DIM}./${SCRIPT_NAME} status              ${NC}— health overview"
    echo -e "   ${DIM}./${SCRIPT_NAME} status --json       ${NC}— machine-readable health"
    echo -e "   ${DIM}./${SCRIPT_NAME} logs [service]      ${NC}— tail logs"
    echo -e "   ${DIM}./${SCRIPT_NAME} shell [service]     ${NC}— open container shell"
    echo -e "   ${DIM}./${SCRIPT_NAME} migrate             ${NC}— run DB migrations"
    echo -e "   ${DIM}./${SCRIPT_NAME} backup              ${NC}— full platform backup"
    echo -e "   ${DIM}./${SCRIPT_NAME} restore             ${NC}— restore from backup"
    echo -e "   ${DIM}./${SCRIPT_NAME} doctor              ${NC}— deep diagnostics + version drift"
    echo -e "   ${DIM}./${SCRIPT_NAME} update              ${NC}— smart pull + rolling restart"
    echo -e "   ${DIM}./${SCRIPT_NAME} update --check      ${NC}— check for updates (no changes)"
    echo -e "   ${DIM}./${SCRIPT_NAME} stop                ${NC}— stop all services"
    echo -e "   ${DIM}./${SCRIPT_NAME} uninstall --purge   ${NC}— remove everything"
    echo ""
    echo -e "${DIM}Log file: ${LOG_FILE}${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────
# HELP
# ─────────────────────────────────────────────────────────────

show_help() {
    cat << EOF

${BOLD}Minder Platform${NC}  v${SCRIPT_VERSION}  —  Setup & Lifecycle Management

${BOLD}USAGE${NC}
    ./${SCRIPT_NAME} [command] [options]

${BOLD}INSTALL & LIFECYCLE${NC}
    (none)                  Full install: prereqs → env → network → DB → services → health
    start                   Start all services
    stop [--clean]          Stop services; --clean prunes dangling images
    restart                 Stop then start
    update                  Smart pull (latest compatible) + rebuild + rolling restart
    update --check          Show available updates without applying anything

${BOLD}OPERATIONS${NC}
    status [--json]         Health overview; --json for machine-readable output
    logs [service] [lines]  Tail logs (all or specific service)
    shell [service]         Open an interactive shell in a container
    migrate [target]        Run Alembic migrations (default: head)
    doctor                  Deep diagnostics: disk, ports, secrets, images, version drift
    sync-postgres-password  Apply POSTGRES_PASSWORD from .env to the running DB
                            (editing a stateful secret in .env does NOT rotate the
                             live credential by itself — run this after changing it)

${BOLD}DATA MANAGEMENT${NC}
    backup                  Full backup: Postgres, Neo4j, InfluxDB, Qdrant, .env
    restore [archive]       Restore from a backup archive (interactive if no path given)
    uninstall               Stop services, preserve data volumes
    uninstall --purge       Stop and DELETE all data (irreversible)

${BOLD}VERSION RESOLUTION${NC}
    Images are pulled with "try latest compatible → fall back to pinned" logic.
    Constraints per image:
      major  — accept any newer patch/minor within same major  (e.g. postgres:16.x)
      minor  — accept newer patches only within same major.minor
      none   — accept any newer version (used for rolling-release images)
      patch  — always use exact pinned tag (no resolution attempted)

    SKIP_VERSION_CHECK=1   Bypass registry queries, use pins directly
    VERBOSE=1              Show per-image resolution details

${BOLD}CONFIGURATION MANAGEMENT${NC}
    (image versions)         Edit docker/compose/docker-compose.yml directly to change
                             image tags — it is the source of truth for what runs.
    ollama-mode internal|external [url]
                             Switch the Ollama backend in .env: internal = platform-managed
                             container; external [url] = reach a URL (same-host daemon or a
                             remote host; default http://host.docker.internal:11434). Flips
                             .env only and prints a "run restart to apply" hint — no restart.

${BOLD}FLAGS${NC}
    DRY_RUN=1               Preview commands without executing
    VERBOSE=1               Enable debug-level output
    NONINTERACTIVE=1        Disable interactive prompts (for CI)
    SKIP_VERSION_CHECK=1    Use exact pinned versions, skip registry queries

${BOLD}EXAMPLES${NC}
    ./${SCRIPT_NAME}                                # Fresh install
    ./${SCRIPT_NAME} update --check                 # What's outdated?
    ./${SCRIPT_NAME} update                         # Pull + restart (smart versioning)
    SKIP_VERSION_CHECK=1 ./${SCRIPT_NAME} update   # Force pinned versions
    ./${SCRIPT_NAME} doctor                         # Full diagnostics with drift report
    ./${SCRIPT_NAME} status --json                  # JSON health for monitoring
    DRY_RUN=1 ./${SCRIPT_NAME} update              # Preview update steps

EOF
}


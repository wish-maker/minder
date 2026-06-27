#!/usr/bin/env bash
###############################################################################
# Minder Platform — Setup & Lifecycle Management Script
# Version: 1.0.0
#
# FEATURES:
#   • Full install / start / stop / restart / status / logs
#   • Comprehensive backup  (Postgres, Neo4j, InfluxDB, Qdrant, RabbitMQ, .env)
#   • restore  — restore from a backup directory
#   • migrate  — run Alembic DB migrations inside running containers
#   • doctor   — deep diagnostic: disk, ports, secrets, images, version drift
#   • update   — pull latest images, rebuild customs, rolling restart
#   • update --check  — report available updates without applying
#   • shell    — drop into a container shell
#   • Smart version resolution: try latest → fall back to pinned on failure
#   • Structured JSON health report  (--json flag on status)
#   • Dry-run mode  (DRY_RUN=1 ./setup.sh start)
#   • CI/non-interactive mode detection
#   • Trap-based cleanup on unexpected exit
#   • Full audit log in logs/setup-<timestamp>.log
###############################################################################

set -euo pipefail
IFS=$'\n\t'

# ─────────────────────────────────────────────────────────────
# SCRIPT METADATA
# ─────────────────────────────────────────────────────────────

readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


# ─────────────────────────────────────────────────────────────
# MODULE SOURCING  (Stage 1 split — see scripts/lib/)
# set -euo pipefail / IFS above are intentionally set BEFORE sourcing,
# matching the monolith's source-time execution order.
# ─────────────────────────────────────────────────────────────

readonly LIB_DIR="${SCRIPT_DIR}/scripts/lib"
source "${LIB_DIR}/config.sh"      # paths, service arrays, image specs, flags, colors
source "${LIB_DIR}/log.sh"         # _cleanup + trap, mkdir logs, logging, spinner, progress
source "${LIB_DIR}/docker.sh"      # run() dry-run gate, compose helpers, container/wait helpers
source "${LIB_DIR}/secrets.sh"     # secret generation, postgres password sync
source "${LIB_DIR}/versions.sh"    # smart version resolution engine (calls cache.sh fns)
source "${LIB_DIR}/preflight.sh"   # prerequisites, GPU, access/compute validation
source "${LIB_DIR}/env.sh"         # .env generation / validation
source "${LIB_DIR}/infra.sh"       # networks, database init, minio init
source "${LIB_DIR}/lifecycle.sh"   # start/stop services (compose + manual docker), waits
source "${LIB_DIR}/health.sh"      # health checks, ollama model download
source "${LIB_DIR}/compose_gen.sh" # compose regeneration + version-spec hashing
source "${LIB_DIR}/commands.sh"    # cmd_* implementations
source "${LIB_DIR}/help.sh"        # success banner, help text
# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────

main() {
    local args=()
    for arg in "$@"; do
        case "$arg" in
            --dry-run)   DRY_RUN=true ;;
            --verbose)   VERBOSE=true ;;
            --json)      JSON_OUTPUT=true ;;
            --skip-version-check) SKIP_VERSION_CHECK=true ;;
            *)           args+=("$arg") ;;
        esac
    done

    local cmd="${args[0]:-install}"
    local arg1="${args[1]:-}"
    local arg2="${args[2]:-}"

    case "$cmd" in
        install)    cmd_install ;;
        start)      cmd_start ;;
        stop)
            [[ "$arg1" == "--clean" || "$arg1" == "--clean-dangling" ]] && CLEAN_DANGLING=true
            cmd_stop
            ;;
        restart)    cmd_restart ;;
        status)
            [[ "$arg1" == "--json" || "$JSON_OUTPUT" == true ]] \
                && cmd_status --json || cmd_status
            ;;
        logs)       cmd_logs "$arg1" "${arg2:-100}" ;;
        shell)      cmd_shell "$arg1" ;;
        migrate)    cmd_migrate "${arg1:-head}" ;;
        backup)     cmd_backup ;;
        restore)    cmd_restore "$arg1" ;;
        doctor)     cmd_doctor ;;
        update)     cmd_update "${arg1:-}" ;;
        regenerate-compose) cmd_regenerate_compose ;;
        generate-secrets) generate_secrets ;;
        sync-postgres-password) sync_postgres_password ;;
        uninstall)  cmd_uninstall "$arg1" ;;
        -h|--help|help) show_help ;;
        *)
            log_error "Unknown command: ${cmd}"
            show_help
            exit 1
            ;;
    esac
}

main "$@"

# ─────────────────────────────────────────────────────────────
# TAG CACHE FUNCTIONS — sourced AFTER main "$@" to PRESERVE the
# monolith's original ordering (defined after main ran → undefined
# during main → caching no-ops). Fixing this is a separate follow-up.
# ─────────────────────────────────────────────────────────────
source "${LIB_DIR}/cache.sh"

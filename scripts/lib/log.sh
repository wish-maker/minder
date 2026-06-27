# ─────────────────────────────────────────────────────────────
# TRAP — cleanup on unexpected exit
# ─────────────────────────────────────────────────────────────

_cleanup() {
    local exit_code=$?
    spinner_stop
    if (( exit_code != 0 )); then
        echo -e "\n${RED}✗ Script exited unexpectedly (code ${exit_code})${NC}"
        echo -e "${DIM}Full log: ${LOG_FILE}${NC}"
    fi
}
trap _cleanup EXIT

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

mkdir -p "$LOGS_DIR"

_log() {
    local level="$1" icon="$2" color="$3"
    shift 3
    local msg="$*"
    local ts; ts="$(date '+%H:%M:%S')"
    echo -e "${color}${icon}${NC} ${DIM}${ts}${NC}  ${msg}"
    local plain; plain="$(echo -e "$msg" | sed 's/\x1b\[[0-9;]*m//g')"
    echo "[${ts}] [${level}] ${plain}" >> "$LOG_FILE" 2>/dev/null || true
}

log_info()    { _log "INFO"  "ℹ"  "${BLUE}"    "$@"; }
log_success() { _log "OK"    "✓"  "${GREEN}"   "${GREEN}$*${NC}"; }
log_warn()    { _log "WARN"  "⚠"  "${YELLOW}"  "${YELLOW}$*${NC}"; }
log_error()   { _log "ERROR" "✗"  "${RED}"     "${RED}$*${NC}"; }
log_debug()   { [[ "$VERBOSE" == "true" ]] && _log "DEBUG" "·" "${DIM}" "$@" || true; }
log_step()    { echo -e "\n${BOLD}${CYAN}▸ $*${NC}"; echo "[STEP] $*" >> "$LOG_FILE" 2>/dev/null || true; }
log_detail()  { echo -e "  ${DIM}$*${NC}"; }

section() {
    local title="$1"
    echo ""
    echo -e "${BOLD}${MAGENTA}┌──────────────────────────────────────────────────┐${NC}"
    printf  "${BOLD}${MAGENTA}│${NC}  %-48s${BOLD}${MAGENTA}│${NC}\n" "$title"
    echo -e "${BOLD}${MAGENTA}└──────────────────────────────────────────────────┘${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────
# SPINNER
# ─────────────────────────────────────────────────────────────

spinner_start() {
    spinner_stop
    local msg="$1"
    (
        local i=0
        while true; do
            printf "\r${CYAN}${SPINNER_FRAMES[$((i % 10))]}${NC}  %-60s" "$msg"
            sleep 0.1
            i=$(( i + 1 ))
        done
    ) &
    SPINNER_PID=$!
    disown "$SPINNER_PID" 2>/dev/null || true
}

spinner_stop() {
    if [[ -n "${SPINNER_PID:-}" ]]; then
        kill "$SPINNER_PID" 2>/dev/null || true
        wait "$SPINNER_PID" 2>/dev/null || true
        SPINNER_PID=""
    fi
    printf "\r\033[K"
}

# ─────────────────────────────────────────────────────────────
# PROGRESS BAR
# ─────────────────────────────────────────────────────────────

PROGRESS_STEP=0
PROGRESS_TOTAL=9

progress_init() { PROGRESS_TOTAL="$1"; PROGRESS_STEP=0; }

progress_next() {
    local label="$1"
    PROGRESS_STEP=$(( PROGRESS_STEP + 1 ))
    local pct=$(( PROGRESS_STEP * 100 / PROGRESS_TOTAL ))
    local filled=$(( pct / 5 ))
    local empty=$(( 20 - filled ))
    local bar=""
    for (( i=0; i<filled; i++ )); do bar+="█"; done
    for (( i=0; i<empty;  i++ )); do bar+="░"; done
    echo ""
    echo -e "${BOLD}[${PROGRESS_STEP}/${PROGRESS_TOTAL}]${NC} ${label}"
    echo -e "${CYAN}${bar}${NC} ${DIM}${pct}%${NC}"
}


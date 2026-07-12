"""Help text for the Minder setup CLI — ported from scripts/lib/help.sh
show_help() (#7, Stage 2). Byte-faithful to the bash heredoc; verified against
`bash setup.sh --help` by the port.
"""

import sys

SCRIPT_VERSION = "1.0.0"
SCRIPT_NAME = "setup.sh"

_HELP_TEMPLATE = (
'\n{bold}Minder Platform{nc}  v{version}  —  Setup & Lifecycle Management\n\n{bold}USAGE{nc}\n    ./{script} [command] [options]\n\n{bold}INSTALL & LIFECYCLE{nc}\n    (none)                  Full install: prereqs → env → network → DB → services → health\n    start                   Start all services\n    stop [--clean]          Stop services; --clean prunes dangling images\n    restart                 Stop then start\n    update                  Smart pull (latest compatible) + rebuild + rolling restart\n    update --check          Show available updates without applying anything\n\n{bold}OPERATIONS{nc}\n    status [--json]         Health overview; --json for machine-readable output\n    logs [service] [lines]  Tail logs (all or specific service)\n    shell [service]         Open an interactive shell in a container\n    migrate [target]        Run Alembic migrations (default: head)\n    doctor                  Deep diagnostics: disk, ports, secrets, images, version drift\n    sync-postgres-password  Apply POSTGRES_PASSWORD from .env to the running DB\n                            (editing a stateful secret in .env does NOT rotate the\n                             live credential by itself — run this after changing it)\n\n{bold}DATA MANAGEMENT{nc}\n    backup                  Full backup: Postgres, Neo4j, InfluxDB, Qdrant, .env\n    restore [archive]       Restore from a backup archive (interactive if no path given)\n    uninstall               Stop services, preserve data volumes\n    uninstall --purge       Stop and DELETE all data (irreversible)\n\n{bold}VERSION RESOLUTION{nc}\n    Images are pulled with "try latest compatible → fall back to pinned" logic.\n    Constraints per image:\n      major  — accept any newer patch/minor within same major  (e.g. postgres:16.x)\n      minor  — accept newer patches only within same major.minor\n      none   — accept any newer version (used for rolling-release images)\n      patch  — always use exact pinned tag (no resolution attempted)\n\n    SKIP_VERSION_CHECK=1   Bypass registry queries, use pins directly\n    VERBOSE=1              Show per-image resolution details\n\n{bold}CONFIGURATION MANAGEMENT{nc}\n    (image versions)         Edit docker/compose/docker-compose.yml directly to change\n                             image tags — it is the source of truth for what runs.\n    ollama-mode internal|external [url]\n                             Switch the Ollama backend in .env: internal = platform-managed\n                             container; external [url] = reach a URL (same-host daemon or a\n                             remote host; default http://host.docker.internal:11434). Flips\n                             .env only and prints a "run restart to apply" hint — no restart.\n\n{bold}FLAGS{nc}\n    DRY_RUN=1               Preview commands without executing\n    VERBOSE=1               Enable debug-level output\n    NONINTERACTIVE=1        Disable interactive prompts (for CI)\n    SKIP_VERSION_CHECK=1    Use exact pinned versions, skip registry queries\n\n{bold}EXAMPLES{nc}\n    ./{script}                                # Fresh install\n    ./{script} update --check                 # What\'s outdated?\n    ./{script} update                         # Pull + restart (smart versioning)\n    SKIP_VERSION_CHECK=1 ./{script} update   # Force pinned versions\n    ./{script} doctor                         # Full diagnostics with drift report\n    ./{script} status --json                  # JSON health for monitoring\n    DRY_RUN=1 ./{script} update              # Preview update steps\n\n'
)


def render(*, color: bool) -> str:
    bold = "[1m" if color else ""
    nc = "[0m" if color else ""
    return _HELP_TEMPLATE.format(
        bold=bold, nc=nc, version=SCRIPT_VERSION, script=SCRIPT_NAME
    )


def print_help() -> None:
    # bash gates color on `[[ -t 1 ]]` + tput colors>=8; approximate with isatty.
    text = render(color=sys.stdout.isatty())
    # Force UTF-8: the help text contains → and — which crash on Windows consoles
    # whose default codec (e.g. cp1254) cannot encode them. The port targets
    # cross-OS, so never rely on the ambient locale encoding.
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8"))
        buf.flush()
    else:  # stream without a binary buffer (e.g. test capture) — best effort
        sys.stdout.write(text)

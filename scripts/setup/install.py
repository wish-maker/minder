"""`install` verb — ported from scripts/lib/commands.sh cmd_install (#7, Stage 2).

The full install orchestration: clear, banner, then 11 progress-tracked phases —
each a ported step — and the success banner. Pure sequencing over already-ported,
already-verified functions; verified by its own output (banner + phase labels +
success banner) and call order via scripts/gate/install_cmd_verify.sh.
"""

from . import bundles, config, env, health
from . import help as help_module
from . import infra, lifecycle, log, migrate, preflight, versions


def _clear() -> None:
    # bash `clear`; emit the ANSI clear+home (works on any ANSI terminal, cross-OS).
    log._write_raw("\033[H\033[2J")


def run(profile: str = "standard") -> int:
    _clear()

    color = log._colors_on()
    b = log._BOLD if color else ""
    c = log._CYAN if color else ""
    y = log._YELLOW if color else ""
    nc = log._NC if color else ""

    log._emit(f"{b}{c}")  # echo -e "${BOLD}${CYAN}"
    log._emit("  ╔" + "═" * 58 + "╗")
    log._emit("  ║         Minder Platform — Automated Setup               ║")
    log._emit(f"  ║                   Version {config.SCRIPT_VERSION:<30}║")
    log._emit("  ╚" + "═" * 58 + "╝")
    log._emit(nc)  # echo -e "${NC}"

    if config.DRY_RUN:
        log._emit(f"{y}  ⚠  DRY RUN MODE — no changes will be made{nc}\n")

    log.progress_init(11)  # 11 phases below → the bar ends at a clean [11/11] 100%

    log.progress_next("Checking prerequisites")
    preflight.check_prerequisites()
    log.progress_next("Setting up environment")
    env.prepare_env()
    # Seed the bundle enable-state for a fresh install (silent + skip-if-exists +
    # DRY_RUN no-op → keeps install_cmd_verify byte-identical). `bundle status`
    # shows the result; `bundle enable <name>` adds more later.
    bundles.seed_profile(profile)
    log.progress_next("Creating Docker network")
    infra.create_networks()
    log.progress_next("Resolving & pulling images")
    versions.pull_all_images()
    log.progress_next("Initialising databases")
    infra.initialize_database()
    log.progress_next("Initialising object storage")
    infra.initialize_minio()
    log.progress_next("Starting services")
    lifecycle.start_services()
    log.progress_next("Waiting for services")
    lifecycle.wait_for_services()
    log.progress_next("Downloading AI models")
    health.download_ollama_models()
    log.progress_next("Running migrations")
    migrate.run("head")
    log.progress_next("Health checks")
    warns = health.run_health_checks()

    # Don't let the celebratory banner imply "all good" when it isn't: if the final
    # health pass had unreachable endpoints, say so first (the banner's URLs are
    # still useful). Gate-safe: under the docker shim everything is healthy → warns=0.
    if warns:
        log.warn(
            f"Install finished, but {warns} endpoint(s) are not yet healthy — "
            "the platform may not be fully ready."
        )
        log.detail(f"Re-check with: ./{config.SCRIPT_NAME} status")

    help_module.print_success_banner()
    return 0

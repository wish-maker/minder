"""`uninstall` verb — ported from scripts/lib/commands.sh cmd_uninstall (#7, Stage 2).

`uninstall`            → compose down (data volumes PRESERVED).
`uninstall --purge`    → destructive: `compose down -v --remove-orphans` (deletes
                         volumes too), behind a DESTRUCTIVE banner + (interactive
                         only) a typed-DELETE confirmation.

The compose calls go through docker.compose_monitoring() → dry-run-gated, so both
branches are non-destructive under DRY_RUN — which is how they are verified
(scripts/gate/uninstall_verify.sh, incl. --purge under CI where the DELETE prompt
is skipped). The interactive DELETE prompt is exercised by hand.
"""

import sys

from . import config, docker, log

SCRIPT_NAME = config.SCRIPT_NAME

# Hardcoded banner literals — copied byte-for-byte from cmd_uninstall (they are
# plain `echo` strings, no printf padding, so no width computation is needed).
_BANNER = (
    "  ┌" + "─" * 53 + "┐",
    "  │  ⚠  DESTRUCTIVE OPERATION — CANNOT BE UNDONE  ⚠    │",
    "  │  All services AND data volumes will be deleted.     │",
    "  └" + "─" * 53 + "┘",
)


def run(purge_arg: str = "") -> int:
    if purge_arg == "--purge":
        # echo -e "${RED}${BOLD}" … box … echo -e "${NC}" — the color lines print
        # as blank lines when colors are off (captured/non-tty), like bash.
        log._emit(f"{log._RED}{log._BOLD}" if log._colors_on() else "")
        for line in _BANNER:
            log._emit(line)
        log._emit(log._NC if log._colors_on() else "")

        if config.INTERACTIVE:
            # printf "Type ${BOLD}DELETE${NC} to confirm: " ; read -r confirm
            prompt = (
                f"Type {log._BOLD}DELETE{log._NC} to confirm: "
                if log._colors_on()
                else "Type DELETE to confirm: "
            )
            sys.stdout.write(prompt)
            sys.stdout.flush()
            if sys.stdin.readline().rstrip("\n") != "DELETE":
                log.info("Uninstall cancelled.")
                return 0

        log.warn("Removing all services, networks, and volumes…")
        docker.compose_monitoring("down", "-v", "--remove-orphans")
        log.success("Full uninstall complete")
    else:
        log.info("Stopping services (data volumes are preserved)")
        docker.compose_monitoring("down")
        log.success("Services stopped — data preserved")
        log.detail(f"To also delete data: ./{SCRIPT_NAME} uninstall --purge")
    return 0

"""Entrypoint for the Minder setup CLI — native Python (Stage 2 #7 complete).

`python -m scripts.setup <verb> [flags]` is the implementation; `setup.sh` is a
thin shim that execs this. Every verb is handled natively here — there is no bash
delegate (the original bash lives on only as the behavior-gate reference,
setup.bash.sh). An unknown command errors + prints help, mirroring the bash
`main()` `*)` case.
"""

import sys

from . import backup as backup_module
from . import config
from . import doctor as doctor_module
from . import help as help_module
from . import install as install_module
from . import log
from . import logs as logs_module
from . import migrate as migrate_module
from . import ollama as ollama_module
from . import restart as restart_module
from . import restore as restore_module
from . import secrets as secrets_module
from . import shell as shell_module
from . import start as start_module
from . import status as status_module
from . import stop as stop_module
from . import uninstall as uninstall_module
from . import update as update_module

# Global flags setup.sh's main() strips before picking the command (keep in sync).
_GLOBAL_FLAGS = {"--dry-run", "--verbose", "--json", "--skip-version-check"}
_HELP_VERBS = {"-h", "--help", "help"}
_VERSION_VERBS = {"-V", "--version", "version"}


def _positional(argv: list[str]) -> list[str]:
    """Args left after stripping global flags — mirrors setup.sh main()'s `args`."""
    return [a for a in argv if a not in _GLOBAL_FLAGS]


def _command(argv: list[str]) -> str:
    """The first positional after global flags — mirrors setup.sh main() (default install)."""
    positional = _positional(argv)
    return positional[0] if positional else "install"


def main(argv: list[str]) -> int:
    # Mirror setup.sh main()'s flag loop: --dry-run/--verbose set the globals the
    # ported modules (docker.run) read. The env-var form is already applied in config.
    if "--dry-run" in argv:
        config.DRY_RUN = True
    if "--verbose" in argv:
        config.VERBOSE = True

    cmd = _command(argv)
    if cmd in _VERSION_VERBS or "--version" in argv or "-V" in argv:
        log._emit(f"{config.SCRIPT_NAME} {config.SCRIPT_VERSION}")
        return 0
    if cmd in _HELP_VERBS:
        help_module.print_help()
        return 0
    if cmd == "ollama-mode":
        # setup.sh: cmd_ollama_mode "$arg1" "$arg2" (args[1], args[2] after flags).
        pos = _positional(argv)
        mode = pos[1] if len(pos) > 1 else ""
        url = pos[2] if len(pos) > 2 else ""
        return ollama_module.run(mode, url)
    if cmd == "sync-postgres-password":
        # setup.sh: sync_postgres_password (no args). Reads/writes .env + docker exec.
        return secrets_module.sync_postgres_password()
    if cmd == "migrate":
        # setup.sh: cmd_migrate "${arg1:-head}" (target defaults to head).
        pos = _positional(argv)
        target = pos[1] if len(pos) > 1 else "head"
        return migrate_module.run(target)
    if cmd == "stop":
        # setup.sh: --clean/--clean-dangling -> CLEAN_DANGLING=true; then cmd_stop.
        pos = _positional(argv)
        arg1 = pos[1] if len(pos) > 1 else ""
        if arg1 in ("--clean", "--clean-dangling"):
            config.CLEAN_DANGLING = True
        return stop_module.run()
    if cmd == "logs":
        # setup.sh: cmd_logs "$arg1" "${arg2:-100}" (service, lines default 100).
        pos = _positional(argv)
        service = pos[1] if len(pos) > 1 else ""
        lines = pos[2] if len(pos) > 2 else "100"
        return logs_module.run(service, lines)
    if cmd == "shell":
        # setup.sh: cmd_shell "$arg1" (service).
        pos = _positional(argv)
        service = pos[1] if len(pos) > 1 else ""
        return shell_module.run(service)
    if cmd == "uninstall":
        # setup.sh: cmd_uninstall "$arg1" (--purge or empty).
        pos = _positional(argv)
        arg1 = pos[1] if len(pos) > 1 else ""
        return uninstall_module.run(arg1)
    if cmd == "start":
        # setup.sh: cmd_start (no args) — full orchestration.
        return start_module.run()
    if cmd == "restart":
        # setup.sh: cmd_restart — stop, sleep 3, start.
        return restart_module.run()
    if cmd == "status":
        # setup.sh: status --json (or global --json) → json; else human.
        return status_module.run(json_mode="--json" in argv)
    if cmd == "update":
        # setup.sh: cmd_update "${arg1:-}" (optional --check).
        pos = _positional(argv)
        arg1 = pos[1] if len(pos) > 1 else ""
        return update_module.run(arg1)
    if cmd == "backup":
        # setup.sh: cmd_backup (no args).
        return backup_module.run()
    if cmd == "restore":
        # setup.sh: cmd_restore "$arg1" (optional archive path).
        pos = _positional(argv)
        archive = pos[1] if len(pos) > 1 else ""
        return restore_module.run(archive)
    if cmd == "doctor":
        # setup.sh: cmd_doctor (no args).
        return doctor_module.run()
    if cmd == "install":
        # setup.sh: default command (no verb) → cmd_install.
        return install_module.run()

    # Unknown command — mirrors setup.sh main()'s `*)` case: error, help, exit 1.
    log.error(f"Unknown command: {cmd}")
    help_module.print_help()
    return 1


def _entry(argv: list[str]) -> int:
    """Run main() with the ported log.sh `trap _cleanup EXIT` epilogue: clear a live
    spinner and, on a non-zero exit, print the "unexpected exit" message + log
    pointer. bash installs `trap _cleanup EXIT`, which fires on EVERY termination —
    including the explicit `exit 1` paths (check_prerequisites, initialize_*, the
    #57 secret guard) — so an explicit SystemExit must get the epilogue too."""
    try:
        code = main(argv)
    except SystemExit as exc:
        rc = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        log.cleanup(rc)
        raise
    except BaseException:
        log.cleanup(1)
        raise
    log.cleanup(code)
    return code


if __name__ == "__main__":
    raise SystemExit(_entry(sys.argv[1:]))

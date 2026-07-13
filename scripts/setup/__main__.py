"""Entrypoint seam for the Stage 2 bash->Python port (#7).

`python -m scripts.setup <verb> [flags]` — today a thin strangler-fig seam that
delegates to the existing bash `setup.sh`, so behaviour is identical while
modules are ported behind it one at a time. As `scripts/lib/*.sh` modules move
to Python (verified against scripts/gate/), their logic will be handled here
directly instead of by the bash delegate.

Cross-platform note: this delegate still requires bash (the modules are still
bash today). The cross-OS payoff arrives as modules are ported and the delegate
shrinks; the seam exists now so that port can happen incrementally.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config
from . import doctor as doctor_module
from . import help as help_module
from . import logs as logs_module
from . import migrate as migrate_module
from . import ollama as ollama_module
from . import restart as restart_module
from . import secrets as secrets_module
from . import shell as shell_module
from . import start as start_module
from . import status as status_module
from . import stop as stop_module
from . import uninstall as uninstall_module
from . import update as update_module

REPO_ROOT = config.REPO_ROOT
SETUP_SH = REPO_ROOT / "setup.sh"

# Global flags setup.sh's main() strips before picking the command (keep in sync).
_GLOBAL_FLAGS = {"--dry-run", "--verbose", "--json", "--skip-version-check"}
_HELP_VERBS = {"-h", "--help", "help"}


def _positional(argv: list[str]) -> list[str]:
    """Args left after stripping global flags — mirrors setup.sh main()'s `args`."""
    return [a for a in argv if a not in _GLOBAL_FLAGS]


def _command(argv: list[str]) -> str:
    """The first positional after global flags — mirrors setup.sh main() (default install)."""
    positional = _positional(argv)
    return positional[0] if positional else "install"


def _find_bash() -> str | None:
    """Locate a bash interpreter (PATH, then common Windows Git-Bash locations)."""
    found = shutil.which("bash")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def main(argv: list[str]) -> int:
    # Mirror setup.sh main()'s flag loop: --dry-run/--verbose set the globals the
    # ported modules (docker.run) read. The env-var form is already applied in config.
    if "--dry-run" in argv:
        config.DRY_RUN = True
    if "--verbose" in argv:
        config.VERBOSE = True

    # Ported verbs run natively in Python (no bash needed) — the cross-platform
    # steps of the strangler-fig port (#7). Everything else still delegates.
    cmd = _command(argv)
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
    if cmd == "doctor":
        # setup.sh: cmd_doctor (no args).
        return doctor_module.run()

    if not SETUP_SH.exists():
        print(f"error: {SETUP_SH} not found", file=sys.stderr)
        return 1

    bash = _find_bash()
    if bash is None:
        print(
            "error: bash not found. The installer is still bash-backed during the "
            "Stage 2 port (#7); install Git Bash or run on Linux/macOS.",
            file=sys.stderr,
        )
        return 127

    # Delegate to bash setup.sh from the repo root, forwarding all args + env.
    proc = subprocess.run(
        [bash, str(SETUP_SH), *argv],
        cwd=str(REPO_ROOT),
        env=os.environ.copy(),
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

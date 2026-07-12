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

# repo root = two levels up from this file (scripts/setup/__main__.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = REPO_ROOT / "setup.sh"


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

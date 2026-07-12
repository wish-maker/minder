"""Configuration constants — ported from scripts/lib/config.sh (#7, Stage 2).

The Python side's single source of truth for paths, names, and flags. Grows
incrementally as verbs are ported (strangler-fig): only what a ported module
actually consumes lives here yet. The bash `config.sh` stays authoritative for
the still-bash modules; these values are kept identical to it.
"""

import os
from pathlib import Path

# bash SCRIPT_DIR = the setup.sh dir = repo root (this file is scripts/setup/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT

# Mirrors setup.sh:30-31.
SCRIPT_VERSION = "1.0.0"
SCRIPT_NAME = "setup.sh"

# Paths (config.sh PATHS block).
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE_FILE = REPO_ROOT / "docker" / "compose" / "docker-compose.yml"
COMPOSE_ENV_FILE = REPO_ROOT / "docker" / "compose" / ".env"

# Service naming (config.sh SERVICE DEFINITIONS block).
CONTAINER_PREFIX = "minder"
NETWORK_NAME = "docker_minder-network"
MONITORING_NETWORK_NAME = "minder-monitoring"


def _truthy(val: str) -> bool:
    # bash run() accepts DRY_RUN in {1,true,yes} (case-insensitive).
    return (val or "").strip().lower() in ("1", "true", "yes")


# Flags. The env-var form is read here; __main__ also flips these when the
# equivalent global flag (--dry-run / --verbose) is present, mirroring setup.sh
# main()'s flag loop (DRY_RUN=true / VERBOSE=true).
DRY_RUN = _truthy(os.environ.get("DRY_RUN", ""))
VERBOSE = _truthy(os.environ.get("VERBOSE", ""))

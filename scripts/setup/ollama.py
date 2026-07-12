"""`ollama-mode` verb — ported from scripts/lib/commands.sh cmd_ollama_mode
(#7, Stage 2).

Switches the Ollama backend recorded in `.env` (the single source of truth):
  internal        -> OLLAMA_BASE_URL=            (platform-managed container)
  external [url]  -> OLLAMA_BASE_URL=<url>       (default host.docker.internal)

Flips `.env` only; prints a "run restart to apply" hint. No docker, no restart —
which is why it is a clean self-contained increment: pure file edit + output,
fully verifiable by diffing the resulting .env + stdout against the bash verb.
"""

import re
from pathlib import Path

from . import log

# SCRIPT_DIR in bash = the setup.sh dir = repo root; ENV_FILE = <root>/.env.
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
SCRIPT_NAME = "setup.sh"

_DEFAULT_URL = "http://host.docker.internal:11434"
# Identical to the bash regex: ^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/.*)?$
_URL_RE = re.compile(r"^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/.*)?$")

_KEY = "OLLAMA_BASE_URL"


def _env_get(key: str) -> str:
    """Mirror: grep -E "^KEY=" .env | cut -d= -f2-  (value after first '=')."""
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    out = [line.split("=", 1)[1] for line in text.splitlines() if line.startswith(f"{key}=")]
    return "\n".join(out)


def run(mode: str = "", url: str = "") -> int:
    if mode == "internal":
        new_url = ""
    elif mode == "external":
        new_url = url or _DEFAULT_URL
        if not _URL_RE.match(new_url):
            log.error(f"Invalid Ollama URL: '{new_url}'")
            log.detail(f"Expected a full URL, e.g. {_DEFAULT_URL} or http://192.168.1.50:11434")
            log.detail(".env was NOT changed.")
            return 1
    else:
        log.error(f"Usage: ./{SCRIPT_NAME} ollama-mode internal|external [url]")
        log.detail("  internal        platform-managed ollama container (OLLAMA_BASE_URL empty)")
        log.detail(f"  external [url]  reach ollama at a URL (default {_DEFAULT_URL})")
        return 1

    if not ENV_FILE.is_file():
        log.error(f"No .env at {ENV_FILE} — run ./{SCRIPT_NAME} install first.")
        return 1

    before = _env_get(_KEY)

    # newline="" so we never translate \n<->\r\n and mangle the file (cross-OS).
    with ENV_FILE.open("r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    # sed -i "s|^OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=<new>|" replaces every matching
    # line; if none match, bash appends the line (printf ... >> .env).
    prefix = f"{_KEY}="
    lines = raw.split("\n")
    if any(line.startswith(prefix) for line in lines):
        new_raw = "\n".join(
            f"{prefix}{new_url}" if line.startswith(prefix) else line for line in lines
        )
    else:
        new_raw = raw + f"{prefix}{new_url}\n"
    with ENV_FILE.open("w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)

    after = _env_get(_KEY)

    label = "internal (platform-managed container)" if not new_url else f"external ({new_url})"
    if before == after:
        log.info(f"Ollama mode already {label} — .env unchanged.")
    else:
        log.success(f"Ollama mode → {label}")
        log.detail(f"OLLAMA_BASE_URL: '{before}' → '{after}'")
    log.warn(f"Run  ./{SCRIPT_NAME} restart  to apply (recreates services + re-mirrors .env).")
    return 0

"""`tts-stt-mode` verb — mirrors ollama.py (#65 item 4), the second real
external-binding case: tts-stt is GPU-oriented (Whisper/Coqui XTTS) and
resource-heavy, so a Pi-class host may want to point at an external, more
capable instance instead of running it locally, same reasoning as Ollama.

Switches the tts-stt backend recorded in `.env` (the single source of truth):
  internal          -> TTS_STT_BASE_URL=                          (platform container)
  external [url]     -> TTS_STT_BASE_URL=<url>                     (one external host)
  failover [url]     -> TTS_STT_BASE_URL=http://minder-tts-stt-router:8006
                        TTS_STT_FAILOVER_PRIMARY=<host:port>       (external primary +
                        internal backup via the tts-stt-router; auto-recovering)

Flips `.env` only; prints a "run restart to apply" hint. No docker, no restart.
"""

import re

from . import config, env, log

ENV_FILE = config.ENV_FILE
SCRIPT_NAME = config.SCRIPT_NAME

_DEFAULT_URL = "http://host.docker.internal:8006"
# Identical to ollama.py's regex: ^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/.*)?$
_URL_RE = re.compile(r"^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/.*)?$")

_BASE_KEY = "TTS_STT_BASE_URL"
_PRIMARY_KEY = "TTS_STT_FAILOVER_PRIMARY"
# In failover mode consumers point here; the router itself reaches the primary.
_ROUTER_URL = "http://minder-tts-stt-router:8006"


def _host_port(url: str) -> str:
    """Strip scheme/path from a full URL → host:port (for the nginx upstream)."""
    return re.sub(r"^https?://", "", url).split("/", 1)[0]


def _set_key(raw: str, key: str, value: str) -> str:
    """Replace the `key=` line (every match) or append it — mirrors the bash
    `sed -i "s|^KEY=.*|KEY=<new>|"` with an append fallback when absent."""
    prefix = f"{key}="
    lines = raw.split("\n")
    if any(line.startswith(prefix) for line in lines):
        return "\n".join(
            f"{prefix}{value}" if line.startswith(prefix) else line for line in lines
        )
    return raw + f"{prefix}{value}\n"


def run(mode: str = "", url: str = "") -> int:
    if mode == "internal":
        base_url, primary = "", ""
    elif mode in ("external", "failover"):
        target = url or _DEFAULT_URL
        if not _URL_RE.match(target):
            log.error(f"Invalid tts-stt URL: '{target}'")
            log.detail(
                f"Expected a full URL, e.g. {_DEFAULT_URL} or http://192.168.1.50:8006"
            )
            log.detail(".env was NOT changed.")
            return 1
        if mode == "external":
            base_url, primary = target, ""
        else:  # failover: consumers -> router; router -> primary (host:port) + backup
            base_url, primary = _ROUTER_URL, _host_port(target)
    else:
        log.error(
            f"Usage: ./{SCRIPT_NAME} tts-stt-mode internal|external|failover [url]"
        )
        log.detail(
            "  internal        platform-managed tts-stt container (TTS_STT_BASE_URL empty)"
        )
        log.detail(f"  external [url]  reach tts-stt at a URL (default {_DEFAULT_URL})")
        log.detail(
            "  failover [url]  external primary + internal fallback via tts-stt-router"
        )
        return 1

    if not ENV_FILE.is_file():
        log.error(f"No .env at {ENV_FILE} — run ./{SCRIPT_NAME} install first.")
        return 1

    before = env.get(_BASE_KEY)

    # newline="" so we never translate \n<->\r\n and mangle the file (cross-OS).
    with ENV_FILE.open("r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    raw = _set_key(raw, _BASE_KEY, base_url)
    raw = _set_key(raw, _PRIMARY_KEY, primary)
    with ENV_FILE.open("w", encoding="utf-8", newline="") as fh:
        fh.write(raw)

    after = env.get(_BASE_KEY)

    if mode == "internal":
        label = "internal (platform-managed container)"
    elif mode == "external":
        label = f"external ({base_url})"
    else:
        label = f"failover (primary {primary} → internal backup, via tts-stt-router)"

    if before == after and mode != "failover":
        log.info(f"tts-stt mode already {label} — .env unchanged.")
    else:
        log.success(f"tts-stt mode → {label}")
        log.detail(f"TTS_STT_BASE_URL: '{before}' → '{after}'")
        if primary:
            log.detail(f"TTS_STT_FAILOVER_PRIMARY: '{primary}'")
    log.warn(
        f"Run  ./{SCRIPT_NAME} restart  to apply (recreates services + re-mirrors .env)."
    )
    return 0

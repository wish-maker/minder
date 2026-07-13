""".env helpers — ported from scripts/lib/env.sh (#7, Stage 2).

Only `get()` (bash `_env_get`) is ported so far: it is the one piece of env.sh
with live Python consumers (ollama.py, secrets.py), so consolidating it here
removes the duplicate copies those modules carried. The rest of env.sh
(prepare_env / secret self-heal / compose-.env mirror / gen_secret) is consumed
only by the still-bash start/install verbs and is deferred until those are ported
— porting it now would be dead code.
"""

from . import config

ENV_FILE = config.ENV_FILE


def get(key: str) -> str:
    """Mirror env.sh _env_get: `grep -E "^KEY=" .env | cut -d= -f2-` — the value
    after the FIRST '='; "" when the key is absent or .env is unreadable. Multiple
    matching lines yield their values joined by newlines, exactly like the pipe.
    (Keys are fixed identifiers with no regex metachars, so a prefix match is
    equivalent to bash's `^KEY=` anchor.)
    """
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    out = [line.split("=", 1)[1] for line in text.splitlines() if line.startswith(f"{key}=")]
    return "\n".join(out)

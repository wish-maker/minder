"""Console logging — ported from scripts/lib/log.sh (#7, Stage 2).

Mirrors the stdout formatting of bash `log_info/success/warn/error/detail`
byte-for-byte (icon + dim timestamp + two spaces + message; colors gated on a
real terminal exactly like bash's `[[ -t 1 ]]`).

Two deliberate scope notes:
- bash `_log` also appends a plain line to `logs/setup-<ts>.log`. That file
  mirroring belongs to the full `log` module port (it needs LOG_FILE / LOGS_DIR
  from the `config` module); it is NOT reproduced here. The user-facing stdout —
  what the port is verified against — is identical.
- Output is written as UTF-8 unconditionally. The icons (ℹ ✓ ⚠ ✗) and message
  glyphs (→, —) crash on Windows consoles whose default codec (e.g. cp1254)
  cannot encode them — the exact cross-OS trap this port exists to remove.
"""

import datetime
import sys

# Colors — identical codes to scripts/lib/config.sh.
_RED = "\033[0;31m"
_GREEN = "\033[0;32m"
_YELLOW = "\033[1;33m"
_BLUE = "\033[0;34m"
_DIM = "\033[2m"
_NC = "\033[0m"


def _colors_on() -> bool:
    # bash gates on `[[ -t 1 ]]` + `tput colors >= 8`; approximate with isatty.
    return sys.stdout.isatty()


def _emit(text: str) -> None:
    """echo -e semantics: write the line + trailing newline, forced UTF-8."""
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write((text + "\n").encode("utf-8"))
        buf.flush()
    else:  # stream without a binary buffer (e.g. test capture) — best effort
        sys.stdout.write(text + "\n")


def _now() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _line(icon: str, head_color: str, msg_color: str, msg: str) -> str:
    # bash: echo -e "${color}${icon}${NC} ${DIM}${ts}${NC}  ${msg}"
    # where success/warn/error pre-wrap msg in the same color; info leaves it plain.
    if _colors_on():
        head, dim, nc = head_color, _DIM, _NC
        body = f"{msg_color}{msg}{_NC}" if msg_color else msg
    else:
        head = dim = nc = ""
        body = msg
    return f"{head}{icon}{nc} {dim}{_now()}{nc}  {body}"


def info(msg: str) -> None:
    _emit(_line("ℹ", _BLUE, "", msg))


def success(msg: str) -> None:
    _emit(_line("✓", _GREEN, _GREEN, msg))


def warn(msg: str) -> None:
    _emit(_line("⚠", _YELLOW, _YELLOW, msg))


def error(msg: str) -> None:
    _emit(_line("✗", _RED, _RED, msg))


def detail(msg: str) -> None:
    # bash: echo -e "  ${DIM}$*${NC}"
    _emit(f"  {_DIM}{msg}{_NC}" if _colors_on() else f"  {msg}")

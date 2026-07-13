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
import threading

# Colors — identical codes to scripts/lib/config.sh.
_RED = "\033[0;31m"
_GREEN = "\033[0;32m"
_YELLOW = "\033[1;33m"
_BLUE = "\033[0;34m"
_MAGENTA = "\033[0;35m"
_CYAN = "\033[0;36m"
_BOLD = "\033[1m"
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


def _write_raw(text: str) -> None:
    """Write without a trailing newline, forced UTF-8 — for the \\r spinner frames
    (the glyphs are non-ASCII and would crash a cp1254 console; same reason _emit
    forces UTF-8)."""
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(text.encode("utf-8"))
        buf.flush()
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


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


def step(msg: str) -> None:
    # bash: echo -e "\n${BOLD}${CYAN}▸ $*${NC}" (a blank line precedes the heading).
    # The "[STEP] …" LOG_FILE append is deferred to the full log-module port
    # (needs config's LOG_FILE), exactly like the other file-mirroring above.
    _emit(f"\n{_BOLD}{_CYAN}▸ {msg}{_NC}" if _colors_on() else f"\n▸ {msg}")


# ── Spinner (log.sh SPINNER) ──────────────────────────────────────────────
# bash animates a background subshell printing `\r<frame>  <msg padded to 60>`
# every 0.1s; spinner_stop kills it and clears the line with `\r\033[K`. Ported
# with a daemon thread. Spinner output is transient (CR-overwritten) and is
# normalized away by the gate (`s/.*\r//`), so its bytes are cosmetic — what
# matters is that it never crashes and leaves a clean line on stop.
_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_spinner_thread: "threading.Thread | None" = None
_spinner_stop: "threading.Event | None" = None


def spinner_start(msg: str) -> None:
    spinner_stop()
    global _spinner_thread, _spinner_stop
    stop = threading.Event()

    def _run() -> None:
        i = 0
        while not stop.is_set():
            frame = _SPINNER_FRAMES[i % 10]
            if _colors_on():
                _write_raw(f"\r{_CYAN}{frame}{_NC}  {msg:<60}")
            else:
                _write_raw(f"\r{frame}  {msg:<60}")
            stop.wait(0.1)
            i += 1

    _spinner_stop = stop
    _spinner_thread = threading.Thread(target=_run, daemon=True)
    _spinner_thread.start()


def spinner_stop() -> None:
    global _spinner_thread, _spinner_stop
    if _spinner_thread is not None:
        if _spinner_stop is not None:
            _spinner_stop.set()
        _spinner_thread.join(timeout=1)
        _spinner_thread = None
        _spinner_stop = None
    _write_raw("\r\033[K")


# ── Progress bar (log.sh PROGRESS BAR) ────────────────────────────────────
_progress_step = 0
_progress_total = 9


def progress_init(total: int) -> None:
    global _progress_step, _progress_total
    _progress_total = int(total)
    _progress_step = 0


def progress_next(label: str) -> None:
    """bash progress_next: blank line, "[step/total] label", then a 20-cell bar +
    percent. Percent = step*100/total (integer), filled = pct/5 (integer)."""
    global _progress_step
    _progress_step += 1
    pct = _progress_step * 100 // _progress_total
    filled = pct // 5
    bar = "█" * filled + "░" * (20 - filled)
    _emit("")
    if _colors_on():
        _emit(f"{_BOLD}[{_progress_step}/{_progress_total}]{_NC} {label}")
        _emit(f"{_CYAN}{bar}{_NC} {_DIM}{pct}%{_NC}")
    else:
        _emit(f"[{_progress_step}/{_progress_total}] {label}")
        _emit(f"{bar} {pct}%")


def section(title: str) -> None:
    # bash section(): blank line, MAGENTA box (top / title / bottom), blank line.
    #   echo ""
    #   echo -e "┌<50×─>┐"
    #   printf  "│  %-48s│\n" "$title"   (2 leading spaces + 48-wide left-justified)
    #   echo -e "└<50×─>┘"
    #   echo ""
    bar = "─" * 50
    if _colors_on():
        bm, nc = _BOLD + _MAGENTA, _NC
    else:
        bm = nc = ""
    # bash `printf %-48s` pads to a minimum of 48 *bytes* (POSIX byte semantics,
    # which is what bash uses here) — NOT 48 code points. Emoji/multibyte titles
    # therefore get fewer trailing spaces than Python's str-width padding would;
    # match the byte width so the closing │ lands where bash puts it.
    pad = max(0, 48 - len(title.encode("utf-8")))
    _emit("")
    _emit(f"{bm}┌{bar}┐{nc}")
    _emit(f"{bm}│{nc}  {title}{' ' * pad}{bm}│{nc}")
    _emit(f"{bm}└{bar}┘{nc}")
    _emit("")

"""Console logging — ported from scripts/lib/log.sh (#7, Stage 2).

Mirrors the stdout formatting of bash `log_info/success/warn/error/detail`
byte-for-byte (icon + dim timestamp + two spaces + message; colors gated on a
real terminal exactly like bash's `[[ -t 1 ]]`).

The `logs/setup-<ts>.log` file mirroring is now ported too: `_log` (and
`log_step`) append a plain `[ts] [LEVEL] message` line to `config.LOG_FILE`,
ANSI-stripped, exactly like bash; `LOGS_DIR` is created at import (bash `mkdir -p`
at source time). The append is best-effort (`>> … 2>/dev/null || true`). The
`_cleanup` EXIT-trap epilogue is ported as `cleanup(exit_code)` (wired in
`__main__`), not an implicit trap — Python has no source-time trap install.

One deliberate note:
- Output is written as UTF-8 unconditionally. The icons (ℹ ✓ ⚠ ✗) and message
  glyphs (→, —) crash on Windows consoles whose default codec (e.g. cp1254)
  cannot encode them — the exact cross-OS trap this port exists to remove.
"""

import datetime
import re
import sys
import threading

from . import config

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


# ── LOG_FILE mirroring (log.sh `mkdir -p "$LOGS_DIR"` + `_log` file append) ──
# bash sources log.sh which unconditionally `mkdir -p "$LOGS_DIR"`; do the same at
# import so the append below always has a destination. Best-effort — never raises.
try:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    # bash: plain="$(echo -e "$msg" | sed 's/\x1b\[[0-9;]*m//g')" — the file line is
    # color-free regardless of whether the caller wrapped the message in a color.
    return _ANSI_RE.sub("", text)


def _append_file(line: str) -> None:
    # bash: echo "..." >> "$LOG_FILE" 2>/dev/null || true — append + swallow errors.
    # newline="\n" forces LF (no Windows \n→\r\n translation) to stay byte-faithful.
    try:
        with open(config.LOG_FILE, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _line(icon: str, head_color: str, msg_color: str, msg: str, ts: str) -> str:
    # bash: echo -e "${color}${icon}${NC} ${DIM}${ts}${NC}  ${msg}"
    # where success/warn/error pre-wrap msg in the same color; info leaves it plain.
    if _colors_on():
        head, dim, nc = head_color, _DIM, _NC
        body = f"{msg_color}{msg}{_NC}" if msg_color else msg
    else:
        head = dim = nc = ""
        body = msg
    return f"{head}{icon}{nc} {dim}{ts}{nc}  {body}"


def _log(level: str, icon: str, head_color: str, msg_color: str, msg: str) -> None:
    # bash _log: one `ts` shared between the stdout line and the file line.
    ts = _now()
    _emit(_line(icon, head_color, msg_color, msg, ts))
    _append_file(f"[{ts}] [{level}] {_strip_ansi(msg)}")


def info(msg: str) -> None:
    _log("INFO", "ℹ", _BLUE, "", msg)


def success(msg: str) -> None:
    _log("OK", "✓", _GREEN, _GREEN, msg)


def warn(msg: str) -> None:
    _log("WARN", "⚠", _YELLOW, _YELLOW, msg)


def error(msg: str) -> None:
    _log("ERROR", "✗", _RED, _RED, msg)


def debug(msg: str) -> None:
    # bash: log_debug() { [[ "$VERBOSE" == "true" ]] && _log "DEBUG" "·" "${DIM}" "$@" || true; }
    # VERBOSE-gated; icon "·", DIM head, message unwrapped. No-op when VERBOSE is off.
    if config.VERBOSE:
        _log("DEBUG", "·", _DIM, "", msg)


def detail(msg: str) -> None:
    # bash: echo -e "  ${DIM}$*${NC}" — NO LOG_FILE append (matches log_detail).
    _emit(f"  {_DIM}{msg}{_NC}" if _colors_on() else f"  {msg}")


def bold(text: str) -> str:
    """A bold-wrapped string (tty-gated) — the shared form of the section sub-headers
    that doctor/health/status/shell/versions each open-coded."""
    return f"{_BOLD}{text}{_NC}" if _colors_on() else text


def step(msg: str) -> None:
    # bash: echo -e "\n${BOLD}${CYAN}▸ $*${NC}"; echo "[STEP] $*" >> "$LOG_FILE"
    # A blank line precedes the heading; the file line is the literal "[STEP] msg"
    # (no ts/level brackets — unlike _log).
    _emit(f"\n{_BOLD}{_CYAN}▸ {msg}{_NC}" if _colors_on() else f"\n▸ {msg}")
    _append_file(f"[STEP] {msg}")


def cleanup(exit_code: int) -> None:
    # bash `_cleanup` (trap on EXIT): stop any running spinner, then on a non-zero
    # exit print the "unexpected exit" epilogue + the log-file pointer. Ported as an
    # explicit call (wired in __main__) — Python installs no source-time EXIT trap.
    spinner_stop()
    if exit_code != 0:
        if _colors_on():
            _emit(f"\n{_RED}✗ Script exited unexpectedly (code {exit_code}){_NC}")
            _emit(f"{_DIM}Full log: {config.LOG_FILE}{_NC}")
        else:
            _emit(f"\n✗ Script exited unexpectedly (code {exit_code})")
            _emit(f"Full log: {config.LOG_FILE}")


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

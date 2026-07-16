#!/usr/bin/env bash
# Verify the ported log FILE-mirroring + cleanup epilogue (scripts/setup/log.py)
# behave identically to scripts/lib/log.sh. Two comparisons:
#
#  1. LOG_FILE contents — `_log` (info/success/warn/error/debug) appends
#     "[ts] [LEVEL] msg" (ANSI-stripped); `log_step` appends the literal "[STEP] msg";
#     `log_detail` appends NOTHING. Each side writes to its OWN timestamped
#     logs/setup-<ts>.log (stamped at config load); we suppress the console lines,
#     then dump the file and compare (the [HH:MM:SS] stamp masked).
#  2. cleanup epilogue — bash `_cleanup` on a non-zero exit vs `log.cleanup(3)`:
#     the "✗ Script exited unexpectedly (code N)" + "Full log: <path>" lines
#     (path masked; colors off since captured output is not a tty).
#
# Pure/file-based (no live stack). The spinner is stubbed on both sides so the
# cleanup comparison isn't polluted by spinner_stop's \r\033[K line-clear.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root (script lives in scripts/gate/)

FAIL=0
cmp() {  # $1=name $2=bash $3=python
  local n="$1" b p
  b="$(printf '%s' "$2")"; p="$(printf '%s' "$3")"
  if [ "$b" = "$p" ]; then
    echo "PASS  $n"
  else
    FAIL=1; echo "FAIL  $n"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'
  fi
}

# ── 1. LOG_FILE contents ───────────────────────────────────────────────────
fnorm() { sed -E -e 's/\r//g' -e 's/\[[0-9]{2}:[0-9]{2}:[0-9]{2}\]/[TS]/g'; }

bfile="$(SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  spinner_start(){ :;}; spinner_stop(){ :;}
  VERBOSE=true
  : > "$LOG_FILE"     # start clean: bash + python stamp the SAME setup-<ts>.log
  {                   # within one second, and _append is append-mode → collision.
    log_info    "alpha info"
    log_success "bravo ok"
    log_warn    "charlie warn"
    log_error   "delta error"
    log_step    "Echo Step"
    log_detail  "foxtrot detail (must NOT be mirrored)"
    log_debug   "golf debug"
  } >/dev/null 2>&1
  cat "$LOG_FILE"
' | fnorm)"

pfile="$("$PY" -c "
import os, sys
from scripts.setup import config, log
config.VERBOSE = True
log.spinner_start = lambda *a, **k: None
log.spinner_stop = lambda *a, **k: None
open(config.LOG_FILE, 'w', encoding='utf-8').close()   # start clean (see bash note)
sys.stdout = open(os.devnull, 'w')          # suppress console lines (no .buffer -> text path)
log.info('alpha info')
log.success('bravo ok')
log.warn('charlie warn')
log.error('delta error')
log.step('Echo Step')
log.detail('foxtrot detail (must NOT be mirrored)')
log.debug('golf debug')
sys.stdout = sys.__stdout__
sys.stdout.buffer.write(open(config.LOG_FILE, 'rb').read())
" | fnorm)"

cmp "LOG_FILE contents" "$bfile" "$pfile"

# ── 2. cleanup epilogue (non-zero exit) ────────────────────────────────────
cnorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's#Full log: .*#Full log: LOGFILE#' \
          | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

bclean="$(SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  spinner_start(){ :;}; spinner_stop(){ :;}
  trap - EXIT            # disable the auto EXIT trap so it does not double-fire
  ( exit 3 ); _cleanup   # sets $?=3, then _cleanup reads it and prints the epilogue
' 2>&1 | cnorm)"

pclean="$("$PY" -c "
from scripts.setup import log
log.spinner_stop = lambda *a, **k: None
log.cleanup(3)
" 2>&1 | cnorm)"

cmp "cleanup epilogue (code 3)" "$bclean" "$pclean"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

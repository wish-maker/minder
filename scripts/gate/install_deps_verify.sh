#!/usr/bin/env bash
# Verify the install-only foundation pieces vs bash: the log progress bar
# (progress_init/progress_next) and help's print_success_banner. Both are pure
# output. The banner's last line prints the timestamped LOG_FILE path (masked).
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2

bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'
  SCRIPT_VERSION="1.0.0"; SCRIPT_NAME="setup.sh"   # set by setup.sh, not config.sh
  source scripts/lib/config.sh >/dev/null 2>&1
  source scripts/lib/log.sh    >/dev/null 2>&1
  source scripts/lib/help.sh   >/dev/null 2>&1
  '"$1"; }
pyi() { "$PY" -c "
from scripts.setup import config, log
from scripts.setup import help as help_mod
$1"; }

# ANSI + CR + timestamps; mask the timestamped LOG_FILE path; drop epilogue/blanks-collapse.
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#Log file: .*#Log file: LOGFILE#' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d'; }

FAIL=0
cmp() { local n="$1" b p; b="$(printf '%s' "$2" | norm)"; p="$(printf '%s' "$3" | norm)"
  if [ "$b" = "$p" ]; then echo "PASS  $n"
  else FAIL=1; echo "FAIL  $n"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi; }

PROG='progress_init 10; progress_next "Checking prerequisites"; progress_next "Setting up environment"; progress_next "Starting services"; progress_next "Health checks"'
PROG_PY='log.progress_init(10); log.progress_next("Checking prerequisites"); log.progress_next("Setting up environment"); log.progress_next("Starting services"); log.progress_next("Health checks")'
cmp "progress bar" "$(bsh "$PROG" 2>&1)" "$(pyi "$PROG_PY" 2>&1)"
cmp "print_success_banner" "$(bsh 'print_success_banner' 2>&1)" "$(pyi 'help_mod.print_success_banner()' 2>&1)"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

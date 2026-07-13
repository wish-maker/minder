#!/usr/bin/env bash
# Verify the ported `restart` verb (scripts/setup/restart.py) ORCHESTRATION:
# cmd_restart is just cmd_stop; sleep 3; cmd_start. Both halves are verified verbs
# (stop_verify / start_cmd_verify), so what must match bash is the CALL ORDER.
# (Same reason as start_cmd_verify for not doing a full run: bash-script shims +
# no-healthcheck live waits.)
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2

# bash side: bare calls inside cmd_restart(){ … }, with the cmd_ prefix stripped
# (bash cmd_stop/cmd_start ↔ python stop/start modules). `sleep 3` has an arg so
# it's excluded by the bare-name filter.
bash_order="$(awk '/^cmd_restart\(\)/{f=1;next} f&&/^\}/{exit} f' scripts/lib/commands.sh \
  | sed -E 's/^[[:space:]]+//' | grep -E '^[a-z_]+$' | sed -E 's/^cmd_//')"

py_order="$("$PY" -c "
from scripts.setup import restart, start, stop
import time
calls = []
stop.run = lambda *a, **k: (calls.append('stop'), 0)[1]
start.run = lambda *a, **k: (calls.append('start'), 0)[1]
time.sleep = lambda *a, **k: None
restart.run()
print(chr(10).join(calls))
")"
py_order="${py_order//$'\r'/}"

if [ "$bash_order" = "$py_order" ]; then
  echo "PASS  restart orchestration — call order matches bash cmd_restart"
  echo "$py_order" | sed 's/^/    /'
  echo "----"; echo "ALL PASS"; exit 0
else
  echo "FAIL  restart orchestration — call order differs"
  diff <(printf '%s\n' "$bash_order") <(printf '%s\n' "$py_order") | sed 's/^/    /'
  echo "----"; echo "SOME FAILED"; exit 1
fi

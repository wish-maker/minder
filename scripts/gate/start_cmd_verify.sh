#!/usr/bin/env bash
# Verify the ported `start` verb (scripts/setup/start.py) ORCHESTRATION: cmd_start
# is pure sequencing — it just calls the ported steps in order — so what must
# match bash is the CALL ORDER. Each step BODY is verified by its own gate script
# (check_prerequisites/gpu/access → preflight_verify, prepare_env → env_verify,
# create_networks → infra_verify, start_services → lifecycle_verify,
# run_health_checks → health_verify, the waits → wait_verify).
#
# Why order-only (not a full bash-vs-python run): the gate's docker shims are bash
# scripts that native-Windows python's subprocess can't exec (no shebang honoring),
# and a live run would block on wait_for_services' no-healthcheck 120s timeouts.
# On Linux/Pi the shim path also works; here we lock the sequence deterministically.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root

# bash side: the bare function-call lines inside cmd_start(){ … }.
bash_order="$(awk '/^cmd_start\(\)/{f=1;next} f&&/^\}/{exit} f' scripts/lib/commands.sh \
  | sed -E 's/^[[:space:]]+//' | grep -E '^[a-z_]+$')"

# python side: monkeypatch each step to record its name, run start.run(), print order.
py_order="$("$PY" -c "
from scripts.setup import start, preflight, env, infra, lifecycle, health
calls = []
def rec(n):
    def _f(*a, **k):
        calls.append(n)
        return 0
    return _f
preflight.check_prerequisites = rec('check_prerequisites')
env.prepare_env = rec('prepare_env')
preflight.validate_gpu_environment = rec('validate_gpu_environment')
preflight.validate_access_mode = rec('validate_access_mode')
preflight.validate_ai_compute_mode = rec('validate_ai_compute_mode')
preflight.validate_compute_resource_profile = rec('validate_compute_resource_profile')
infra.create_networks = rec('create_networks')
lifecycle.start_services = rec('start_services')
lifecycle.wait_for_services = rec('wait_for_services')
health.run_health_checks = rec('run_health_checks')
start.run()
print(chr(10).join(calls))
")"
py_order="${py_order//$'\r'/}"

if [ "$bash_order" = "$py_order" ]; then
  echo "PASS  start orchestration — call order matches bash cmd_start"
  echo "$py_order" | sed 's/^/    /'
  echo "----"; echo "ALL PASS"; exit 0
else
  echo "FAIL  start orchestration — call order differs"
  diff <(printf '%s\n' "$bash_order") <(printf '%s\n' "$py_order") | sed 's/^/    /'
  echo "----"; echo "SOME FAILED"; exit 1
fi

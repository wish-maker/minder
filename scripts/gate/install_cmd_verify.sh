#!/usr/bin/env bash
# Verify the ported `install` verb (scripts/setup/install.py) vs bash cmd_install.
# cmd_install is pure orchestration over 11 already-ported+verified steps, so the
# 11 heavy steps are STUBBED to no-ops on both sides; what's compared is install's
# OWN output — the clear + banner + the 11 progress phase labels (in order) + the
# success banner — which captures both the scaffolding and the call ORDER. No live
# calls, no waits. (Same reason as start_cmd_verify for not running the steps for
# real: bash-script shims + no-healthcheck 120s waits.)
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2

STUBS='check_prerequisites(){ :;}; prepare_env(){ :;}; create_networks(){ :;}; pull_all_images(){ :;}; initialize_database(){ :;}; initialize_minio(){ :;}; start_services(){ :;}; wait_for_services(){ :;}; download_ollama_models(){ :;}; cmd_migrate(){ :;}; run_health_checks(){ :;}'
bsh() { SCRIPT_DIR="$PWD" TERM=xterm bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'
  SCRIPT_VERSION="1.0.0"; SCRIPT_NAME="setup.sh"
  for m in config log docker env cache versions preflight infra lifecycle health commands help; do
    source "scripts/lib/$m.sh" >/dev/null 2>&1
  done
  '"$STUBS"'
  '"$1"; }
PY_STUBS='
from scripts.setup import preflight, env, infra, versions, lifecycle, health, migrate
_noop = lambda *a, **k: None
preflight.check_prerequisites = _noop
env.prepare_env = _noop
infra.create_networks = _noop
versions.pull_all_images = _noop
infra.initialize_database = _noop
infra.initialize_minio = _noop
lifecycle.start_services = _noop
lifecycle.wait_for_services = _noop
health.download_ollama_models = _noop
migrate.run = _noop
health.run_health_checks = _noop'
pyi() { "$PY" -c "
from scripts.setup import install
$PY_STUBS
$1"; }

# ANSI (incl the clear escape + banner colors) + CR + timestamps; mask the
# timestamped LOG_FILE line; drop epilogue + collapse blank lines.
norm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#Log file: .*#Log file: LOGFILE#' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' -e '/^[[:space:]]*$/d'; }

FAIL=0
b="$(bsh 'cmd_install' 2>&1 | norm)"
p="$(pyi 'install.run()' 2>&1 | norm)"
if [ "$b" = "$p" ]; then echo "PASS  install (scaffolding + phase order)"
else FAIL=1; echo "FAIL  install"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

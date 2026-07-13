#!/usr/bin/env bash
# Verify the ported `doctor` verb (scripts/setup/doctor.py) vs bash cmd_doctor,
# against the LIVE stack under SKIP_VERSION_CHECK=1 (drift section → "skipped").
# Every reading is host-specific (versions, RAM/disk GB, .env perms, port states,
# health, volumes) and the issue count varies, so this compares STRUCTURALLY: the
# section order + labels + per-port line COUNT + the weak-secret findings (same
# repo .env on both sides), with the varying values masked.
set -u
PY="${PY:-python}"
cd "$(dirname "$0")/../.." || exit 2

bsh() { SCRIPT_DIR="$PWD" SKIP_VERSION_CHECK=true bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'; SKIP_VERSION_CHECK=true
  source scripts/lib/config.sh   >/dev/null 2>&1
  source scripts/lib/log.sh      >/dev/null 2>&1
  source scripts/lib/docker.sh   >/dev/null 2>&1
  source scripts/lib/versions.sh >/dev/null 2>&1
  source scripts/lib/commands.sh >/dev/null 2>&1
  '"$1"; }
pyi() { SKIP_VERSION_CHECK=true "$PY" -c "
from scripts.setup import config, doctor
config.SKIP_VERSION_CHECK = True
$1"; }

# Mask every host-specific reading to its label/structure; keep section headers,
# the per-port line shape, the weak-secret findings (deterministic on the shared
# repo .env), and the drift-skipped line.
dnorm() { sed -E -e 's/.*\r//' -e 's/\x1b\[[0-9;]*[A-Za-z]//g' \
                 -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                 -e 's/^  Version: .*/  Version: X/' -e 's/^  Compose: .*/  Compose: X/' \
                 -e 's/.*Docker RAM:.*/RAM/' -e 's/.*Docker has only.*/RAM/' \
                 -e 's/.*Free space:.*/DISK/' -e 's/.*Low disk space:.*/DISK/' \
                 -e 's/.*permissions are.*/PERM/' -e 's/.*Permissions:.*/PERM/' \
                 -e 's/^  :[0-9]+ .*/  :PORT/' \
                 -e 's/.*containers running, none unhealthy.*/HEALTH/' \
                 -e 's/.*Unhealthy containers:.*/HEALTH/' \
                 -e 's/.*Dangling volumes:.*/VOL/' -e 's/.*dangling volumes.*/VOL/' \
                 -e 's/.*issue\(s\) found.*/SUMMARY/' -e 's/.*No issues found.*/SUMMARY/' \
                 -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
          | sed -e '/^[[:space:]]*$/d'; }

FAIL=0
b="$(bsh 'cmd_doctor' 2>&1 | dnorm)"
p="$(pyi 'doctor.run()' 2>&1 | dnorm)"
if [ "$b" = "$p" ]; then echo "PASS  doctor (structural)"
else FAIL=1; echo "FAIL  doctor"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

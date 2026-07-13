#!/usr/bin/env bash
# Verify the ported Phase-4 validators (scripts/setup/preflight.py) behave
# identically to scripts/lib/preflight.sh: validate_ai_compute_mode and
# validate_compute_resource_profile. Both read a mode from .env, print the
# resolved config, and export derived vars — pure/deterministic. Operates on the
# REAL repo .env (both read $ENV_FILE / config.ENV_FILE), so it backs it up and
# ALWAYS restores. Read-only w.r.t. the stack.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root
BAK="$(mktemp)"; HAD_ENV=0
[ -f .env ] && { cp .env "$BAK"; HAD_ENV=1; }
restore() { if [ "$HAD_ENV" = 1 ]; then cp "$BAK" .env; else rm -f .env; fi; rm -f "$BAK"; }
trap restore EXIT

# bash side: source config+log+env+preflight (IFS mirrors setup.sh). log.sh's EXIT
# trap fires spinner_stop (\r\033[K) + the epilogue on non-zero exit — normalized away.
bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"; IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh    >/dev/null 2>&1
  source scripts/lib/log.sh       >/dev/null 2>&1
  source scripts/lib/env.sh       >/dev/null 2>&1
  source scripts/lib/preflight.sh >/dev/null 2>&1
  '"$1"; }
pyi() { "$PY" -c "
import os
from scripts.setup import preflight
$1"; }

# Normalize: ANSI + CR; HH:MM:SS; the OS-specific abs .env path; the _cleanup
# epilogue; then collapse trailing blank lines.
norm() { sed -E -e 's/\x1b\[[0-9;]*[A-Za-z]//g' -e 's/\r//g' \
                -e 's/[0-9]{2}:[0-9]{2}:[0-9]{2}/TS/g' \
                -e 's#[A-Za-z]:[\\/][^ ]*\.env#ENVPATH#g' -e 's#/[^ ]*/\.env#ENVPATH#g' \
                -e '/Script exited unexpectedly/d' -e '/Full log:/d' \
         | sed -e :a -e '/^[[:space:]]*$/{$d;N;ba}'; }

FAIL=0
cmp() { local n="$1" b p; b="$(printf '%s' "$2" | norm)"; p="$(printf '%s' "$3" | norm)"
  if [ "$b" = "$p" ]; then echo "PASS  $n"
  else FAIL=1; echo "FAIL  $n"; diff <(printf '%s\n' "$b") <(printf '%s\n' "$p") | sed 's/^/    /'; fi; }

# ---- validate_ai_compute_mode ----
AI_DUMP_B='validate_ai_compute_mode; echo "EXIT=$?"; echo "S=${AI_ENDPOINT_STRATEGY:-}"; echo "LOC=${AI_LOCAL_OLLAMA_URL:-}"; echo "LAN=${AI_LAN_OLLAMA_URL:-}"; echo "FB=${AI_ENABLE_FALLBACK:-}"; echo "TO=${AI_FALLBACK_TIMEOUT_MS:-}"'
AI_DUMP_P='rc=preflight.validate_ai_compute_mode()
print(f"EXIT={rc}")
for k in ("AI_ENDPOINT_STRATEGY","AI_LOCAL_OLLAMA_URL","AI_LAN_OLLAMA_URL","AI_ENABLE_FALLBACK","AI_FALLBACK_TIMEOUT_MS"):
    print({"AI_ENDPOINT_STRATEGY":"S","AI_LOCAL_OLLAMA_URL":"LOC","AI_LAN_OLLAMA_URL":"LAN","AI_ENABLE_FALLBACK":"FB","AI_FALLBACK_TIMEOUT_MS":"TO"}[k]+"="+os.environ.get(k,""))'
ai_case() {  # $1=name  $2=.env-content
  printf '%s' "$2" > .env
  cmp "ai: $1" "$(bsh "$AI_DUMP_B")" "$(pyi "$AI_DUMP_P")"
}
ai_case "internal"          $'AI_COMPUTE_MODE=internal\n'
ai_case "default (absent)"  $'FOO=bar\n'
ai_case "external ok"       $'AI_COMPUTE_MODE=external\nEXTERNAL_GPU_NODE_URL=http://gpu:11434\n'
ai_case "external no-url"   $'AI_COMPUTE_MODE=external\n'
ai_case "hybrid ok"         $'AI_COMPUTE_MODE=hybrid\nEXTERNAL_GPU_NODE_URL=http://gpu:11434\n'
ai_case "hybrid no-url"     $'AI_COMPUTE_MODE=hybrid\n'
ai_case "invalid"           $'AI_COMPUTE_MODE=bogus\n'

# ---- validate_compute_resource_profile ----
CP_DUMP_B='validate_compute_resource_profile; echo "EXIT=$?"; echo "CPU=${COMPUTE_CPU_LIMIT:-}"; echo "MEM=${COMPUTE_MEMORY_LIMIT:-}"'
CP_DUMP_P='rc=preflight.validate_compute_resource_profile()
print(f"EXIT={rc}")
print("CPU="+os.environ.get("COMPUTE_CPU_LIMIT",""))
print("MEM="+os.environ.get("COMPUTE_MEMORY_LIMIT",""))'
cp_case() {  # $1=name  $2=.env-content  $3=GPU_AVAILABLE(optional)
  printf '%s' "$2" > .env
  local gpu="${3:-}"
  cmp "cp: $1" \
    "$(GPU_AVAILABLE="$gpu" bsh "$CP_DUMP_B")" \
    "$(GPU_AVAILABLE="$gpu" pyi "$CP_DUMP_P")"
}
cp_case "low"               $'COMPUTE_RESOURCE_PROFILE=low\n'
cp_case "medium (absent)"   $'FOO=bar\n'
cp_case "high"              $'COMPUTE_RESOURCE_PROFILE=high\n'
cp_case "enterprise gpu"    $'COMPUTE_RESOURCE_PROFILE=enterprise\n'   true
cp_case "enterprise no-gpu" $'COMPUTE_RESOURCE_PROFILE=enterprise\n'
cp_case "invalid"           $'COMPUTE_RESOURCE_PROFILE=bogus\n'

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

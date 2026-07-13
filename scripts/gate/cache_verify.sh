#!/usr/bin/env bash
# Verify the ported tag-cache helpers (scripts/setup/cache.py) behave identically
# to scripts/lib/cache.sh. Pure/file-based, no live stack. Uses a repo-relative
# temp dir (NOT mktemp) so both bash and native-Windows python resolve the same
# paths against the shared cwd — an MSYS /tmp path would be opaque to python.
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root — the cwd both sides resolve against
TMPD=".verify-cache-tmp"
rm -rf "$TMPD"; mkdir -p "$TMPD"; trap 'rm -rf "$TMPD"' EXIT

# bash side: source config + cache (IFS mirrors setup.sh). cache.sh's only log dep
# is log_debug — STUB it instead of sourcing log.sh, whose `trap _cleanup EXIT`
# would fire spinner_stop (\r\033[K) + the exit epilogue on every subshell exit.
bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"
  IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh >/dev/null 2>&1
  log_debug() { :; }
  source scripts/lib/cache.sh
  '"$1"; }
pyi() { "$PY" -c "
from pathlib import Path
from scripts.setup import config, cache
$1"; }

# path normalize: backslash->slash, strip the abs prefix up to .cache/ (bash builds
# a forward-slash Git-Bash path, Python's Path renders native separators).
pnorm() { sed -E -e 's#\\#/#g' -e 's#^.*/\.cache/#.cache/#'; }
# strip CR (Python's Windows text-mode stdout translates \n->\r\n on print) + any
# stray ANSI (defensive).
FAIL=0
ansi() { sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g'; }
cmp() { local n="$1" b p; b="$(printf '%s' "$2" | ansi)"; p="$(printf '%s' "$3" | ansi)"
  b="${b//$'\r'/}"; p="${p//$'\r'/}"
  if [ "$b" = "$p" ]; then printf 'PASS  %-26s = %q\n' "$n" "$b"
  else FAIL=1; printf 'FAIL  %s\n  bash  : %q\n  python: %q\n' "$n" "$b" "$p"; fi; }

# --- cache_file (pure) ---
for pair in "dockerhub library/postgres" "ghcr open-webui/open-webui" "quay foo/bar/baz"; do
  set -- $pair
  cmp "cache_file $1 $2" \
    "$(bsh "_cache_file '$1' '$2'" | pnorm)" \
    "$(pyi "print(cache.cache_file('$1','$2'))" | pnorm)"
done

# --- cache_expired: fresh / missing / old ---
: > "$TMPD/fresh.json"
touch -d '2 days ago' "$TMPD/old.json" 2>/dev/null || touch -t 202001010000 "$TMPD/old.json"
bx() { bsh "_cache_expired '$1' && echo true || echo false"; }
px() { pyi "print('true' if cache.cache_expired(Path(r'$1')) else 'false', end='')"; }
cmp "expired fresh"   "$(bx "$TMPD/fresh.json")"   "$(px "$TMPD/fresh.json")"
cmp "expired missing" "$(bx "$TMPD/none.json")"    "$(px "$TMPD/none.json")"
cmp "expired old"     "$(bx "$TMPD/old.json")"     "$(px "$TMPD/old.json")"

# --- load_cached_tags: fresh (parsed) / expired (empty) ---
printf '%s\n' '{' '  "timestamp": "2020-01-01T00:00:00Z",' '  "tags": [' \
              '    "1.0",' '    "1.1",' '    "latest"' '  ]' '}' > "$TMPD/tags.json"
cp "$TMPD/tags.json" "$TMPD/tags-old.json"
touch -d '2 days ago' "$TMPD/tags-old.json" 2>/dev/null || touch -t 202001010000 "$TMPD/tags-old.json"
cmp "load fresh"   "$(bsh "_load_cached_tags '$TMPD/tags.json'")"     "$(pyi "print(cache.load_cached_tags(Path(r'$TMPD/tags.json')), end='')")"
cmp "load expired" "$(bsh "_load_cached_tags '$TMPD/tags-old.json'")" "$(pyi "print(cache.load_cached_tags(Path(r'$TMPD/tags-old.json')), end='')")"

# --- cache_tags: write via both, compare (timestamp line normalized) ---
tsn() { sed -E 's/"timestamp": "[^"]*"/"timestamp": "TS"/'; }
# inner printf produces REAL newlines in the tags string for bash _cache_tags.
bsh 'tags=$(printf "3.0\n3.1\nlatest"); _cache_tags "'"$TMPD"'/wb.json" "$tags"' >/dev/null
pyi "cache.cache_tags(Path(r'$TMPD/wp.json'), '3.0\n3.1\nlatest', 'FIXED')"
cmp "cache_tags file" "$(tsn < "$TMPD/wb.json")" "$(tsn < "$TMPD/wp.json")"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

#!/usr/bin/env bash
# Verify the ported pure version helpers (scripts/setup/versions.py) behave
# identically to scripts/lib/versions.sh. Pure/deterministic, no network. Covers
# registry_type / image_repo / strip_v / ver_ge / tag_satisfies_constraint /
# best_tag. (The network + resolve/pull/drift orchestration is not ported yet.)
set -u
PY="${PY:-python}"                     # override e.g. PY=python3 on boxes without `python`
cd "$(dirname "$0")/../.." || exit 2   # repo root

# bash side: source config + versions (IFS mirrors setup.sh). The 6 helpers have
# no log/cache deps at call time, so nothing else is needed.
bsh() { SCRIPT_DIR="$PWD" bash -c '
  SCRIPT_DIR="$PWD"
  IFS=$'"'"'\n\t'"'"'
  source scripts/lib/config.sh   >/dev/null 2>&1
  source scripts/lib/versions.sh >/dev/null 2>&1
  '"$1"; }
pyi() { "$PY" -c "
from scripts.setup import versions as v
$1"; }

FAIL=0
cmp() { local n="$1" b p; b="$(printf '%s' "$2")"; p="$(printf '%s' "$3")"
  b="${b//$'\r'/}"; p="${p//$'\r'/}"
  if [ "$b" = "$p" ]; then printf 'PASS  %-42s = %q\n' "$n" "$b"
  else FAIL=1; printf 'FAIL  %s\n  bash  : %q\n  python: %q\n' "$n" "$b" "$p"; fi; }

# --- registry_type ---
for r in "ghcr.io/open-webui/open-webui:main" "quay.io/prometheus/prometheus:v2" "postgres:16" "grafana/grafana:11"; do
  cmp "registry_type $r" "$(bsh "_registry_type '$r'")" "$(pyi "print(v.registry_type('$r'))")"
done

# --- image_repo ---
for r in "postgres:16" "grafana/grafana:11" "ghcr.io/open-webui/open-webui:main" "quay.io/prometheus/prometheus:v2.5"; do
  cmp "image_repo $r" "$(bsh "_image_repo '$r'")" "$(pyi "print(v.image_repo('$r'))")"
done

# --- strip_v ---
for s in "v1.2.3" "1.2.3" "v2" "version"; do
  cmp "strip_v $s" "$(bsh "_strip_v '$s'")" "$(pyi "print(v.strip_v('$s'))")"
done

# --- ver_ge (echo true/false from exit code) ---
vg() { bsh "_ver_ge '$1' '$2' && echo true || echo false"; }
vp() { pyi "print('true' if v.ver_ge('$1','$2') else 'false')"; }
for pair in "1.2.3 1.2.10:false" "1.2.10 1.2.3:true" "2.0 1.9:true" "1.2 1.2.0:false" \
            "1.2.0 1.2:true" "1.5 1.5:true" "10.0 9.9:true" "v2.0 1.5:true"; do
  a="${pair%%:*}"; set -- $a
  cmp "ver_ge $1 $2" "$(vg "$1" "$2")" "$(vp "$1" "$2")"
done

# --- tag_satisfies_constraint ---
tsc_b() { bsh "_tag_satisfies_constraint '$1' '$2' '$3' && echo true || echo false"; }
tsc_p() { pyi "print('true' if v.tag_satisfies_constraint('$1','$2','$3') else 'false')"; }
while IFS='|' read -r tag pre con; do
  cmp "tsc $tag/$pre/$con" "$(tsc_b "$tag" "$pre" "$con")" "$(tsc_p "$tag" "$pre" "$con")"
done <<'CASES'
1.2.3|1.0.0|major
2.0.0|1.0.0|major
1.5.0|1.2.0|minor
1.2.9|1.2.0|minor
latest|1.0.0|none
1.2.3-rc1|1.0.0|none
1.2.3|1.0.0|none
1.2.3|1.0.0|patch
main|1.0.0|major
CASES

# --- best_tag (bash: newline list via inner printf; python: literal \n in string) ---
bt_b() { bsh 'tags=$(printf "'"$1"'"); _best_tag "$tags" "'"$2"'" "'"$3"'"'; }
cmp "best_tag major"  "$(bt_b '1.0\n1.2\n1.10\n2.0\nlatest' '1.0.0' 'major')" "$(pyi "print(v.best_tag('1.0\n1.2\n1.10\n2.0\nlatest','1.0.0','major'))")"
cmp "best_tag none"   "$(bt_b '1.0\n1.2\n1.10\n2.0\nlatest' '1.0.0' 'none')"  "$(pyi "print(v.best_tag('1.0\n1.2\n1.10\n2.0\nlatest','1.0.0','none'))")"
cmp "best_tag minor"  "$(bt_b '1.0\n1.2\n1.10\n2.0' '1.2.0' 'minor')"         "$(pyi "print(v.best_tag('1.0\n1.2\n1.10\n2.0','1.2.0','minor'))")"
cmp "best_tag empty"  "$(bt_b 'latest\nmain' '1.0.0' 'none')"                 "$(pyi "print(v.best_tag('latest\nmain','1.0.0','none'))")"

echo "----"; [ "$FAIL" = 0 ] && echo "ALL PASS" || echo "SOME FAILED"
exit $FAIL

#!/usr/bin/env bash
###############################################################################
# Minder setup.sh behavior gate — dry-run golden-trace regression harness.
#
# Captures a normalized trace of setup.sh's CLI behavior across the core verbs,
# with a deterministic PATH shim (instant sleep; fixed docker/curl/wget reads) so
# the trace depends ONLY on setup.sh's command structure, not on wall-clock,
# host, or live-stack state. Used to prove a change is behavior-preserving.
#
#   selfdiff          capture twice, diff — MUST be empty (the gate on the gate)
#   baseline          capture current setup.sh -> scripts/gate/.baseline.trace
#   compare           capture current, diff against the saved baseline (drift = exit 1)
#   capture <file>    raw normalized capture to <file>
#
# DEPENDENCY: relies on the DRY_RUN=1 env-var short-circuit in run() (docker.sh,
# commit 7b0edc7c). If that fix were reverted, DRY_RUN=1 would NOT gate mutations
# and the gate would attempt real docker. The PATH shim is the backstop (it shadows
# the real docker binary), but the env-var gate is the primary safety.
#
# Guarantees: catches changes to the command SET/ORDER, step order, service groups,
# and endpoints. Does NOT catch semantic bugs inside a command body that produce the
# same dry-run trace (same residual as bash -n / structure diff) — verify those by
# running for real.
###############################################################################
set -uo pipefail

GATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${GATE_DIR}/../.." && pwd)"          # scripts/gate -> repo root (cygwin/posix form)
SHIM="${GATE_DIR}/shim"
SED_STATIC="${GATE_DIR}/normalize.sed"
BASELINE="${GATE_DIR}/.baseline.trace"

VERBS=( "--help" "stop" "start" "restart" )
# No tracked files are rewritten outside run() anymore: regenerate-compose was removed
# and docker-compose.yml is now a hand-maintained source (not regenerated) — nothing
# mutates a tracked file during a capture, so there is nothing to snapshot/self-heal.
# (Empty array is safe under `set -u` in bash 4.4+; the snapshot loops become no-ops.)
SNAP_FILES=()

# gitignored env files prepare_env() rewrites OUTSIDE run() (start/restart now call it).
# Unlike SNAP_FILES these are UNTRACKED — git checkout can't restore them — so we record
# exact prior state INCLUDING absence and restore/delete accordingly. Before each capture
# a deterministic fully-filled root .env is seeded so prepare_env is a silent no-op
# (nothing to fill → no fill logs, no .env.backup-<ts>, no randomness).
ENV_PATHS=( ".env" "docker/compose/.env" )

SNAP_DIR=""
ENV_SNAP_DIR=""
SED_TMP=""

restore_snapshot() {
    [[ -n "$SNAP_DIR" && -d "$SNAP_DIR" ]] || return 0
    local rel key
    for rel in "${SNAP_FILES[@]}"; do
        key="${rel//\//__}"
        [[ -f "${SNAP_DIR}/${key}" ]] && cp "${SNAP_DIR}/${key}" "${REPO}/${rel}"
    done
}

snapshot_env() {
    ENV_SNAP_DIR="$(mktemp -d)"
    local rel key
    for rel in "${ENV_PATHS[@]}"; do
        key="${rel//\//__}"
        if [[ -f "${REPO}/${rel}" ]]; then
            cp "${REPO}/${rel}" "${ENV_SNAP_DIR}/${key}"
            : > "${ENV_SNAP_DIR}/${key}.present"   # marker: existed before the run
        fi
    done
}

restore_env() {
    [[ -n "$ENV_SNAP_DIR" && -d "$ENV_SNAP_DIR" ]] || return 0
    local rel key
    for rel in "${ENV_PATHS[@]}"; do
        key="${rel//\//__}"
        if [[ -f "${ENV_SNAP_DIR}/${key}.present" ]]; then
            cp "${ENV_SNAP_DIR}/${key}" "${REPO}/${rel}"
        else
            rm -f "${REPO}/${rel}"                 # was absent before → keep it absent
        fi
    done
}

seed_env() {
    # Deterministic, fully-filled root .env: every CHANGEME* placeholder → a fixed
    # non-placeholder value. OLLAMA_BASE_URL= stays empty (not a secret key → ignored
    # by prepare_env). Result: prepare_env finds nothing to heal and stays silent.
    [[ -f "${REPO}/.env.example" ]] || return 0
    sed -E 's/CHANGEME[A-Z0-9_]*/0000000000000000000000000000000000000000000000000000000000000000/g' \
        "${REPO}/.env.example" > "${REPO}/.env"
}

cleanup() {
    # trap backstop: restore tracked files AND env files even on Ctrl-C / error / TERM
    restore_snapshot
    restore_env
    [[ -n "$SNAP_DIR" ]] && rm -rf "$SNAP_DIR"
    [[ -n "$ENV_SNAP_DIR" ]] && rm -rf "$ENV_SNAP_DIR"
    [[ -n "$SED_TMP" ]] && rm -f "$SED_TMP"
}
trap cleanup EXIT INT TERM

build_sed() {
    # static rules + machine-specific masks injected here (kept out of the committed
    # .sed so it stays portable): absolute repo path and hostname.
    local out; out="$(mktemp)"
    {
        printf 's#%s#REPO#g\n' "$REPO"
        printf 's/%s/HOST/g\n' "$(hostname)"
        cat "$SED_STATIC"
    } > "$out"
    echo "$out"
}

capture() {
    local out="$1"
    SED_TMP="$(build_sed)"

    # Self-heal: the trap restores on EXIT/INT/TERM, but a SIGKILL (e.g. a CI hard
    # timeout) is uncatchable and could leave these generated+tracked files in their
    # regenerated state. Reset any that are dirty vs HEAD so the gate always starts
    # from the committed baseline. (They are generated artifacts — don't keep
    # uncommitted edits to them while running the gate.)
    local rel key dirty=()
    for rel in "${SNAP_FILES[@]}"; do
        git -C "$REPO" diff --quiet -- "$rel" 2>/dev/null || dirty+=("$rel")
    done
    if (( ${#dirty[@]} )); then
        echo "gate: pre-dirty generated file(s) reset to HEAD: ${dirty[*]}" >&2
        git -C "$REPO" checkout HEAD -- "${dirty[@]}" 2>/dev/null || true
    fi

    SNAP_DIR="$(mktemp -d)"
    for rel in "${SNAP_FILES[@]}"; do
        key="${rel//\//__}"
        [[ -f "${REPO}/${rel}" ]] && cp "${REPO}/${rel}" "${SNAP_DIR}/${key}"
    done

    # Preserve the real (untracked) env files, then seed a deterministic fully-filled
    # root .env so prepare_env (now invoked by start/restart) is a silent no-op.
    snapshot_env
    seed_env

    local modules; modules="$(cd "$REPO" && ls scripts/lib/*.sh 2>/dev/null | sort | tr '\n' ' ')"
    {
        echo "### GATE TRACE (normalized, value-masked)"
        echo "### modules: ${modules}"
        echo "### verbs:   ${VERBS[*]}"
        echo
        local v
        for v in "${VERBS[@]}"; do
            echo "############################## VERB: ${v} ##############################"
            ( cd "$REPO" && timeout 60 env PATH="${SHIM}:${PATH}" \
                CI=true NONINTERACTIVE=true SKIP_VERSION_CHECK=true DRY_RUN=1 \
                bash setup.bash.sh ${v} 2>&1 ) | sed -E -f "$SED_TMP"
            echo "############################## END: ${v} ##############################"
            echo
        done
    } > "$out"

    # restore immediately (trap is the interrupt backstop), then drop temps
    restore_snapshot
    restore_env
    rm -rf "$SNAP_DIR"; SNAP_DIR=""
    rm -rf "$ENV_SNAP_DIR"; ENV_SNAP_DIR=""
    rm -f "$SED_TMP"; SED_TMP=""
    echo "captured -> ${out}  ($(wc -l < "$out") lines)" >&2
}

case "${1:-}" in
    selfdiff)
        a="$(mktemp)"; b="$(mktemp)"
        capture "$a"; capture "$b"
        if diff -u "$a" "$b"; then
            echo "SELFDIFF: EMPTY ✓ — gate is deterministic on current setup.sh"
            rc=0
        else
            echo "SELFDIFF: NON-EMPTY ✗ — non-determinism; do NOT trust the gate until fixed"
            rc=1
        fi
        rm -f "$a" "$b"; exit "$rc"
        ;;
    baseline)
        capture "$BASELINE"
        echo "baseline saved -> ${BASELINE}"
        ;;
    compare)
        [[ -f "$BASELINE" ]] || { echo "no baseline — run: $0 baseline"; exit 2; }
        cur="$(mktemp)"; capture "$cur"
        if diff -u "$BASELINE" "$cur"; then
            echo "COMPARE: identical to baseline ✓ — behavior preserved"; rc=0
        else
            echo "COMPARE: DRIFT vs baseline ✗ — behavior changed"; rc=1
        fi
        rm -f "$cur"; exit "$rc"
        ;;
    capture)
        capture "${2:?usage: $0 capture <outfile>}"
        ;;
    *)
        echo "usage: $0 {selfdiff | baseline | compare | capture <file>}"
        exit 2
        ;;
esac

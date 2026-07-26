"""`bundle` verb — enable/disable capability bundles + reconcile their services.

A **bundle** is a named group of services delivering a capability (monitoring,
rag, …); it is the enable/disable + refcount unit. See docs/architecture/bundles.md.

The full bundle map (core/inference/rag/…) is **derived from Compose `minder.bundle=`
labels** — the compose file is the single source of truth (#65). The pure claim-graph
brain (map/state parsing + refcount logic) lives in `shared.bundle_graph` so the host
CLI (here) and the future registry API import the SAME logic; this module keeps the
I/O + `docker compose` verbs and delegates the computation.

Enable-state lives in a dedicated, secret-free JSON file (`config.BUNDLES_STATE`,
`bundles.state.json`) — NOT `.env`, which carries secrets the network-facing
registry must not mount. Shape `{"<bundle>": {"enabled": bool}}`; an absent file or
key means enabled, so the default start path + setup gate stay byte-identical. (The
product-default profile is seeded by `install --profile` via `seed_profile`.)

Model: a service is UP iff ≥1 **enabled** bundle **claims** it. `owned`/`shared`
are DERIVED display states, never stored — the operational binary is referenced
(≥1 claimant → keep) vs **orphan** (0 → GC candidate). Disabling a bundle reports
its now-orphaned services and stops them only on `--stop-orphans`. Every action
funnels through `docker compose` — compose stays the single source of truth.
"""

import json
import os

from shared.bundle_graph import ClaimGraph, parse_bundle_labels, parse_state

from . import config, docker, env, log  # config inserts src/ on the path (below)

SCRIPT_NAME = config.SCRIPT_NAME
STATE_FILE = config.BUNDLES_STATE

# Services whose platform-managed container is replaced by an EXTERNAL endpoint when
# its env var is non-empty — the exact binding lifecycle.start_services already reads
# to gate the internal-ollama profile. For an externally-bound service we don't own a
# container: `status` shows it as external (not orphan-drift) and `enable`/`reconcile`
# skip starting it. This is the one binding that exists today (ollama via
# OLLAMA_BASE_URL); the general managed/external/self-host model is Phase 3 (see
# docs/architecture/bundles.md).
EXTERNAL_BINDINGS: dict[str, str] = {"ollama": "OLLAMA_BASE_URL"}


def external_binding(service: str) -> "str | None":
    """The external endpoint a service is bound to (its internal container is NOT
    ours to run), or None when it is platform-managed. Same source of truth as
    lifecycle: an exported env var wins, else root .env; empty → managed."""
    var = EXTERNAL_BINDINGS.get(service)
    if not var:
        return None
    return (os.environ.get(var) or env.get(var)) or None


# The always-on kernel bundle — never disabled, always a claimant.
CORE_BUNDLE = "core"


def _load_claims() -> dict:
    """Derive ``{bundle: (services...)}`` from the Compose `minder.bundle=` labels via
    the shared brain (compose = single source of truth, #65). Raises if no labels are
    present so the map never silently becomes empty."""
    claims = parse_bundle_labels(config.COMPOSE_FILE.read_text(encoding="utf-8"))
    if CORE_BUNDLE not in claims:
        raise RuntimeError(
            f"No minder.bundle labels found in {config.COMPOSE_FILE}; the bundle map "
            "is derived from Compose labels (#65) — the compose file must carry them."
        )
    return claims


# service-claims map (bundle → tuple of services) + the display-shaped BUNDLES facade
# (``{bundle: {"claims": (...)}}``) kept for existing callers (lifecycle/status/verbs).
_CLAIMS: dict = _load_claims()
BUNDLES: dict = {bundle: {"claims": claims} for bundle, claims in _CLAIMS.items()}


def _graph() -> ClaimGraph:
    """A fresh claim-graph over the current enable-state (read each call, so a
    disable/enable within one verb is reflected immediately — matches prior behaviour).
    """
    return ClaimGraph(_CLAIMS, _load_state(), CORE_BUNDLE)


# Optional bundles (everything but core) and install profiles = the optional
# bundles a fresh install turns ON. `standard` (the default) is the AI experience;
# `minimal` is core-only (bring your own services); `full` is everything.
_OPTIONAL_BUNDLES = ("monitoring", "inference", "rag", "graph-rag", "chat", "voice")
PROFILES: dict[str, tuple[str, ...]] = {
    "minimal": (),
    "standard": ("inference", "rag", "chat"),
    "full": _OPTIONAL_BUNDLES,
}

_ACTIONS = ("enable", "disable", "status", "reconcile")


def _load_state() -> dict:
    """Read bundles.state.json and parse it via the shared brain. Missing file → {}
    (everything enabled); corrupt/wrong-shape handled by ``parse_state`` (drops bad
    entries → degrade to enabled). This is the enable-state the CLI I/O owns; the pure
    logic over it lives in ``shared.bundle_graph``."""
    try:
        text = STATE_FILE.read_text(encoding="utf-8")
    except OSError:
        return {}
    return parse_state(text)


def is_enabled(name: str) -> bool:
    """True unless bundles.state.json disables the bundle (`core` is always on)."""
    return _graph().is_enabled(name)


def service_active(service: str) -> bool:
    """Should `service` run? Yes iff a bundle claiming it is enabled (an unclaimed
    service defaults to active). This is what `start` filters each group by — all
    enabled → no-op → the setup gate stays identical."""
    return _graph().service_active(service)


def _enabled_bundles(exclude: "str | None" = None) -> "set[str]":
    return _graph().enabled_bundles(exclude)


def _claimants(service: str, enabled: "set[str]") -> "set[str]":
    """Enabled bundles (from the passed set) that claim `service`. Pure over the claim
    map — no state read (the hot path in `status`)."""
    return {b for b in enabled if service in _CLAIMS.get(b, ())}


def _orphans_after(disabling: str) -> "list[str]":
    """Services of `disabling` no OTHER enabled bundle claims — safe to stop."""
    return _graph().orphans_after(disabling)


def orphaned_services() -> "list[str]":
    """Every service claimed by NO enabled bundle — what `start`/`reconcile` converge
    on (a bundle disabled while running is brought down; state = desired)."""
    return _graph().orphaned_services()


def _set_enabled(name: str, on: bool) -> None:
    """Persist a bundle's enable-state to bundles.state.json (merge, don't clobber
    other bundles). DRY_RUN previews without writing. sort_keys for a stable diff."""
    if config.DRY_RUN:
        log.detail(f"[dry-run] would set {name}.enabled={on} in {STATE_FILE.name}")
        return
    state = _load_state()
    state.setdefault(name, {})["enabled"] = on
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def seed_profile(name: str) -> bool:
    """For a FRESH install, seed bundles.state.json from a profile — record each
    optional bundle's enabled state (core is always on). Returns False (a no-op) if
    the state file already exists (never clobber a user's choices on re-install) or
    under DRY_RUN. Silent so install_cmd_verify stays byte-identical; the resulting
    set is visible via `bundle status`."""
    if config.DRY_RUN or STATE_FILE.exists():
        return False
    on = set(PROFILES.get(name, PROFILES["standard"]))
    state = {b: {"enabled": b in on} for b in _OPTIONAL_BUNDLES}
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return True


def enable(name: str) -> int:
    claims = BUNDLES[name]["claims"]
    already = is_enabled(name)
    _set_enabled(name, True)
    if already:
        log.info(f"Bundle '{name}' already enabled — ensuring its services are up.")
    else:
        log.success(f"Bundle '{name}' → enabled")
    # Bring up every claimed service EXCEPT ones bound to an external endpoint — we
    # don't run their container (starting it would spin an idle duplicate of the
    # external one). Compose reuses already-running ones + orders via depends_on.
    managed = [s for s in sorted(claims) if not external_binding(s)]
    for svc in sorted(claims):
        endpoint = external_binding(svc)
        if endpoint:
            log.detail(f"{svc}: external ({endpoint}) — not started")
    if managed:
        docker.compose("up", "-d", *managed)
    log.detail(
        f"Reconciled: {', '.join(managed) if managed else '(none — all external)'}"
    )
    return 0


def disable(name: str, stop_orphans: bool = False) -> int:
    _set_enabled(name, False)
    log.success(f"Bundle '{name}' → disabled")
    orphans = _orphans_after(name)
    kept = sorted(set(BUNDLES[name]["claims"]) - set(orphans))
    if kept:
        log.detail(f"Kept (still claimed elsewhere): {', '.join(kept)}")
    if not orphans:
        log.info("No orphaned services — every one is still claimed.")
        return 0
    if stop_orphans:
        docker.compose("stop", *orphans)
        log.success(f"Stopped orphaned: {', '.join(orphans)}")
    else:
        log.warn(f"Now claimed by no enabled bundle: {', '.join(orphans)}")
        log.detail(
            f"Left running. Stop them with:  ./{SCRIPT_NAME} bundle disable {name} --stop-orphans"
        )
    return 0


def reconcile(stop_orphans: bool = False) -> int:
    """Converge to the enable-state: bring up every enabled bundle's services;
    detect services orphaned by disabled bundles and report (or stop with
    --stop-orphans). The primitive `start` and the future registry API drive."""
    enabled = _enabled_bundles()
    claimed = sorted({s for b in enabled for s in BUNDLES[b]["claims"]})
    # Externally-bound services aren't ours to start (see external_binding).
    want_up = [s for s in claimed if not external_binding(s)]
    external = [s for s in claimed if external_binding(s)]
    orphans = orphaned_services()
    log.section("🧩  Reconciling bundle services")
    if external:
        log.detail(f"External (not started): {', '.join(external)}")
    if want_up:
        log.info(f"Ensuring up:  {', '.join(want_up)}")
        docker.compose("up", "-d", *want_up)
    if orphans and stop_orphans:
        log.info(f"Stopping orphaned:  {', '.join(orphans)}")
        docker.compose("stop", *orphans)
    elif orphans:
        log.warn(
            f"Orphaned (unclaimed): {', '.join(orphans)} — pass --stop-orphans to stop"
        )
    if not want_up and not orphans:
        log.info("Nothing to do — bundle services already match the enable-state.")
    log.success("Reconcile complete")
    return 0


def status() -> int:
    log.section("🧩  Bundles")
    enabled = _enabled_bundles()
    for name, spec in BUNDLES.items():
        on = name in enabled
        log.info(f"{name}  [{'enabled' if on else 'disabled'}]")
        for svc in spec["claims"]:
            running = docker.container_running(svc)
            health = docker.container_health(svc) if running else "stopped"
            claimants = _claimants(svc, enabled)
            endpoint = external_binding(svc)
            if endpoint:
                # Externally bound: we don't run this container, so a stopped one is
                # NOT drift — show the endpoint. A RUNNING one IS drift (an idle
                # internal duplicate that shouldn't be up).
                mark = "!" if running else "⇄"
                log.detail(f"  {mark} {svc:<20} {health:<9} external → {endpoint}")
                continue
            # drift: a claimed service is down, or a service is up but now orphaned
            mark = "✓" if running else "·"
            if (claimants and not running) or (not claimants and running):
                mark = "!"
            by = ", ".join(sorted(claimants)) if claimants else "— orphaned"
            log.detail(f"  {mark} {svc:<20} {health:<9} claimed by: {by}")
    return 0


def run(action: str = "", name: str = "", stop_orphans: bool = False) -> int:
    if action not in _ACTIONS:
        log.error(
            f"Usage: ./{SCRIPT_NAME} bundle enable|disable <name> [--stop-orphans]"
            f"  |  bundle status|reconcile"
        )
        log.detail(f"  Known bundles: {', '.join(BUNDLES)}")
        return 1
    if action == "status":
        return status()
    if action == "reconcile":
        return reconcile(stop_orphans=stop_orphans)

    if not name:
        log.error(f"./{SCRIPT_NAME} bundle {action} <name>  — bundle name required")
        log.detail(f"  Known bundles: {', '.join(BUNDLES)}")
        return 1
    if name not in BUNDLES:
        log.error(f"Unknown bundle: '{name}'")
        log.detail(f"  Known bundles: {', '.join(BUNDLES)}")
        return 1
    if action == "disable" and name == CORE_BUNDLE:
        log.error("The 'core' bundle is the always-on kernel and cannot be disabled.")
        return 1

    if action == "enable":
        return enable(name)
    return disable(name, stop_orphans=stop_orphans)

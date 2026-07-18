"""`bundle` verb — enable/disable capability bundles + reconcile their services.

A **bundle** is a named group of services delivering a capability (monitoring,
rag, …); it is the enable/disable + refcount unit. See docs/architecture/bundles.md.

Phase 1 wires the **monitoring** bundle only; the full map (core/inference/rag/…),
Compose-label derivation, and binding (managed/external) land in Phase 2 — the
other services are still started unconditionally by lifecycle until then.

Enable-state lives in a dedicated, secret-free JSON file (`config.BUNDLES_STATE`,
`bundles.state.json`) — NOT `.env`, which carries secrets the network-facing
registry must not mount. Shape `{"<bundle>": {"enabled": bool}}`; an absent file or
key means enabled, so the default start path + setup gate stay byte-identical. (The
product-default profile is seeded by `install` separately — Phase 2.)

Model: a service is UP iff ≥1 **enabled** bundle **claims** it. `owned`/`shared`
are DERIVED display states, never stored — the operational binary is referenced
(≥1 claimant → keep) vs **orphan** (0 → GC candidate). Disabling a bundle reports
its now-orphaned services and stops them only on `--stop-orphans`. Every action
funnels through `docker compose` — compose stays the single source of truth.
"""

import json

from . import config, docker, log

SCRIPT_NAME = config.SCRIPT_NAME
STATE_FILE = config.BUNDLES_STATE

# bundle name → services it claims. Phase 1: monitoring only. The claim graph is
# derived here for now; Phase 2 derives it from Compose `minder.bundle=` labels and
# adds core/inference/rag/graph-rag/chat/voice.
BUNDLES: dict[str, dict[str, tuple[str, ...]]] = {
    "monitoring": {
        "claims": (*config.MONITORING_SERVICES, *config.EXPORTER_SERVICES),
    },
}

_ACTIONS = ("enable", "disable", "status", "reconcile")


def _load_state() -> dict:
    """Parse bundles.state.json → {bundle: {enabled: bool}}. Missing/corrupt file
    → {} (everything defaults to enabled), matching the absent-key semantics."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_enabled(name: str) -> bool:
    """True unless bundles.state.json explicitly disables the bundle. Absent file/
    key → enabled, so the default start path (and thus the setup gate) is unchanged."""
    return bool(_load_state().get(name, {}).get("enabled", True))


def _enabled_bundles(exclude: "str | None" = None) -> "set[str]":
    return {n for n in BUNDLES if n != exclude and is_enabled(n)}


def _claimants(service: str, enabled: "set[str]") -> "set[str]":
    """Enabled bundles that claim `service` — everything keeping it alive. Empty →
    the service is orphaned. (Phase 2 folds in core-bundle + cross-bundle claims.)"""
    return {b for b in enabled if service in BUNDLES[b]["claims"]}


def _orphans_after(disabling: str) -> "list[str]":
    """Services of `disabling` that no OTHER enabled bundle claims — safe to stop
    once this bundle is off. Deterministic order."""
    remaining = _enabled_bundles(exclude=disabling)
    return sorted(
        s for s in BUNDLES[disabling]["claims"] if not _claimants(s, remaining)
    )


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


def enable(name: str) -> int:
    claims = BUNDLES[name]["claims"]
    already = is_enabled(name)
    _set_enabled(name, True)
    if already:
        log.info(f"Bundle '{name}' already enabled — ensuring its services are up.")
    else:
        log.success(f"Bundle '{name}' → enabled")
    # Bring up every claimed service (compose reuses already-running ones + orders
    # via depends_on/health). One command keeps the shape close to start_services.
    docker.compose("up", "-d", *sorted(claims))
    log.detail(f"Reconciled: {', '.join(sorted(claims))}")
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
    want_up = sorted({s for b in enabled for s in BUNDLES[b]["claims"]})
    orphans = sorted(
        {
            s
            for b in BUNDLES
            if not is_enabled(b)
            for s in BUNDLES[b]["claims"]
            if not _claimants(s, enabled)
        }
    )
    log.section("🧩  Reconciling bundle services")
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

    if action == "enable":
        return enable(name)
    return disable(name, stop_orphans=stop_orphans)

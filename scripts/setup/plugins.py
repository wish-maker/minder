"""`plugin` verb — enable/disable first-party plugins + reconcile their infra.

The container control-plane: enabling a plugin brings its dependency services up
(reusing any already running); disabling one detects which of its dependencies are
now **orphaned** — used by no other enabled plugin and no core service — and reports
them, stopping them only on explicit `--stop-orphans`.

Enable-state lives in a dedicated, secret-free JSON file (`config.PLUGINS_STATE`,
`plugins.state.json`) — NOT `.env`, which carries secrets the network-facing
registry must not mount. Shape: `{"<plugin>": {"enabled": bool}}`; an absent file
or key means enabled, so the default start path + setup gate stay byte-identical.
The refcount "brain" below (`_consumers` / `_orphans_after`) is decoupled from where
state lives and how containers are stopped, so both the host CLI and the future
registry API can share it.

Dependency model — a uniform refcount, no owned/shared tiers:
- Each plugin declares `deps`: the service containers it needs.
- Each service's CONSUMERS = enabled plugins that declare it  ∪  core (non-plugin)
  services that use it (`CORE_CONSUMERS`). `influxdb` has core consumer `grafana`
  (a datasource edge that is NOT a compose depends_on), so disabling telegraf
  leaves influxdb up while offering to stop telegraf itself. That falls out of the
  graph — no hardcoded never-stop list.

Every mutating action funnels through `docker compose` — compose stays the single
source of truth; no imperative docker.sock start/stop.
"""

import json

from . import config, docker, log

SCRIPT_NAME = config.SCRIPT_NAME
STATE_FILE = config.PLUGINS_STATE

# name → dependency service containers the plugin needs.
PLUGINS: dict[str, dict[str, tuple[str, ...]]] = {
    "telegraf": {"deps": ("telegraf", "influxdb")},
}

# Core (non-plugin) consumers of a shared service — edges the compose depends_on
# graph does NOT capture (e.g. Grafana reads influxdb as a datasource, not a
# startup dependency). A service listed here has a standing consumer, so it never
# becomes orphaned by disabling a plugin.
CORE_CONSUMERS: dict[str, tuple[str, ...]] = {
    "influxdb": ("grafana",),
}

_ACTIONS = ("enable", "disable", "status", "reconcile")


def _load_state() -> dict:
    """Parse plugins.state.json → {plugin: {enabled: bool}}. Missing/corrupt file
    → {} (everything defaults to enabled), matching the .env-absent semantics."""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_enabled(name: str) -> bool:
    """True unless plugins.state.json explicitly disables the plugin. Absent file/
    key → enabled, so the default start path (and thus the setup gate) is unchanged."""
    return bool(_load_state().get(name, {}).get("enabled", True))


def _enabled_plugins(exclude: "str | None" = None) -> "set[str]":
    return {n for n in PLUGINS if n != exclude and is_enabled(n)}


def _consumers(service: str, enabled: "set[str]") -> "set[str]":
    """Everything currently keeping `service` alive: enabled plugins that declare it
    as a dep, plus any core service that uses it. Empty → the service is orphaned."""
    users = {p for p in enabled if service in PLUGINS[p]["deps"]}
    users.update(CORE_CONSUMERS.get(service, ()))
    return users


def _orphans_after(disabling: str) -> "list[str]":
    """Deps of `disabling` that no OTHER enabled plugin and no core service needs —
    i.e. the containers safe to stop once this plugin is off. Deterministic order."""
    remaining = _enabled_plugins(exclude=disabling)
    return sorted(d for d in PLUGINS[disabling]["deps"] if not _consumers(d, remaining))


def _set_enabled(name: str, on: bool) -> None:
    """Persist plugin enable-state to plugins.state.json (merge, don't clobber other
    plugins). DRY_RUN previews without writing. sort_keys for a stable diff."""
    if config.DRY_RUN:
        log.detail(f"[dry-run] would set {name}.enabled={on} in {STATE_FILE.name}")
        return
    state = _load_state()
    state.setdefault(name, {})["enabled"] = on
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def enable(name: str) -> int:
    deps = PLUGINS[name]["deps"]
    already = is_enabled(name)
    _set_enabled(name, True)
    if already:
        log.info(f"Plugin '{name}' already enabled — ensuring its services are up.")
    else:
        log.success(f"Plugin '{name}' → enabled")
    # Bring up every dependency (compose reuses already-running ones + orders via
    # depends_on/health). One command keeps the shape close to start_services.
    docker.compose("up", "-d", *sorted(deps))
    log.detail(f"Reconciled: {', '.join(sorted(deps))}")
    return 0


def disable(name: str, stop_orphans: bool = False) -> int:
    _set_enabled(name, False)
    log.success(f"Plugin '{name}' → disabled")
    orphans = _orphans_after(name)
    kept = sorted(set(PLUGINS[name]["deps"]) - set(orphans))
    if kept:
        log.detail(f"Kept (still used elsewhere): {', '.join(kept)}")
    if not orphans:
        log.info("No orphaned containers — every dependency is still in use.")
        return 0
    if stop_orphans:
        docker.compose("stop", *orphans)
        log.success(f"Stopped orphaned: {', '.join(orphans)}")
    else:
        log.warn(f"Now unused by any plugin or service: {', '.join(orphans)}")
        log.detail(
            f"Left running. Stop them with:  ./{SCRIPT_NAME} plugin disable {name} --stop-orphans"
        )
    return 0


def reconcile(stop_orphans: bool = False) -> int:
    """Converge to the .env flags: bring up every enabled plugin's deps; detect the
    containers orphaned by disabled plugins and report (or stop with --stop-orphans).
    The primitive `start` and the future registry API drive. Idempotent."""
    enabled = _enabled_plugins()
    want_up = sorted({d for p in enabled for d in PLUGINS[p]["deps"]})
    orphans = sorted(
        {
            d
            for p in PLUGINS
            if not is_enabled(p)
            for d in PLUGINS[p]["deps"]
            if not _consumers(d, enabled)
        }
    )
    log.section("🔌  Reconciling plugin containers")
    if want_up:
        log.info(f"Ensuring up:  {', '.join(want_up)}")
        docker.compose("up", "-d", *want_up)
    if orphans and stop_orphans:
        log.info(f"Stopping orphaned:  {', '.join(orphans)}")
        docker.compose("stop", *orphans)
    elif orphans:
        log.warn(
            f"Orphaned (unused): {', '.join(orphans)} — pass --stop-orphans to stop"
        )
    if not want_up and not orphans:
        log.info("Nothing to do — plugin containers already match .env.")
    log.success("Reconcile complete")
    return 0


def status() -> int:
    log.section("🔌  Plugin Container Lifecycle")
    enabled = _enabled_plugins()
    for name, spec in PLUGINS.items():
        on = name in enabled
        log.info(f"{name}  [{'enabled' if on else 'disabled'}]")
        for svc in spec["deps"]:
            running = docker.container_running(svc)
            health = docker.container_health(svc) if running else "stopped"
            users = _consumers(svc, enabled)
            # drift: a needed dep is down, or a dep is up but now orphaned
            mark = "✓" if running else "·"
            if (users and not running) or (not users and running):
                mark = "!"
            users_s = ", ".join(sorted(users)) if users else "— orphaned"
            log.detail(f"  {mark} {svc:<12} {health:<9} used by: {users_s}")
    return 0


def run(action: str = "", name: str = "", stop_orphans: bool = False) -> int:
    if action not in _ACTIONS:
        log.error(
            f"Usage: ./{SCRIPT_NAME} plugin enable|disable <name> [--stop-orphans]"
            f"  |  plugin status|reconcile"
        )
        log.detail(f"  Known plugins: {', '.join(PLUGINS)}")
        return 1
    if action == "status":
        return status()
    if action == "reconcile":
        return reconcile(stop_orphans=stop_orphans)

    if not name:
        log.error(f"./{SCRIPT_NAME} plugin {action} <name>  — plugin name required")
        log.detail(f"  Known plugins: {', '.join(PLUGINS)}")
        return 1
    if name not in PLUGINS:
        log.error(f"Unknown plugin: '{name}'")
        log.detail(f"  Known plugins: {', '.join(PLUGINS)}")
        return 1

    if action == "enable":
        return enable(name)
    return disable(name, stop_orphans=stop_orphans)

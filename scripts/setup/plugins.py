"""`plugin` verb — enable/disable first-party plugins + reconcile their infra.

The container control-plane: enabling a plugin brings its dependency services up
(reusing any already running); disabling one detects which of its dependencies are
now **orphaned** — used by no other enabled plugin and no core service — and reports
them, stopping them only on explicit `--stop-orphans`.

State lives in **.env** for now (`PLUGIN_<NAME>_ENABLED`, absent → enabled); the
API build will move it to a dedicated secret-free `plugins.state` file the registry
can safely share. The refcount "brain" below (`_consumers` / `_orphans_after`) is
decoupled from where state lives and how containers are stopped, so both the host
CLI and the future registry API can share it.

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

from . import config, docker, env, log

SCRIPT_NAME = config.SCRIPT_NAME
ENV_FILE = config.ENV_FILE

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


def _flag_key(name: str) -> str:
    return f"PLUGIN_{name.upper()}_ENABLED"


def is_enabled(name: str) -> bool:
    """True unless .env explicitly disables the plugin. Absent key → enabled, so
    the default start path (and thus the setup gate) is unchanged."""
    raw = env.get(_flag_key(name))
    if raw == "":
        return True
    return config._truthy(raw)


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


def _set_flag(name: str, on: bool) -> None:
    """Upsert PLUGIN_<NAME>_ENABLED=1|0 in .env (sed-style, mirroring ollama.py):
    replace every matching line, else append. newline="" so we never translate
    \\n<->\\r\\n cross-OS. DRY_RUN previews without writing."""
    key = _flag_key(name)
    value = "1" if on else "0"
    if config.DRY_RUN:
        log.detail(f"[dry-run] would set {key}={value} in .env")
        return
    with ENV_FILE.open("r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    prefix = f"{key}="
    lines = raw.split("\n")
    if any(line.startswith(prefix) for line in lines):
        new_raw = "\n".join(
            f"{prefix}{value}" if line.startswith(prefix) else line for line in lines
        )
    else:
        sep = "" if raw.endswith("\n") or raw == "" else "\n"
        new_raw = f"{raw}{sep}{prefix}{value}\n"
    with ENV_FILE.open("w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)


def enable(name: str) -> int:
    deps = PLUGINS[name]["deps"]
    already = is_enabled(name)
    _set_flag(name, True)
    if already:
        log.info(f"Plugin '{name}' already enabled — ensuring its services are up.")
    else:
        log.success(f"Plugin '{name}' → enabled ({_flag_key(name)}=1)")
    # Bring up every dependency (compose reuses already-running ones + orders via
    # depends_on/health). One command keeps the shape close to start_services.
    docker.compose("up", "-d", *sorted(deps))
    log.detail(f"Reconciled: {', '.join(sorted(deps))}")
    return 0


def disable(name: str, stop_orphans: bool = False) -> int:
    _set_flag(name, False)
    log.success(f"Plugin '{name}' → disabled ({_flag_key(name)}=0)")
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
        log.info(f"{name}  [{'enabled' if on else 'disabled'}]  ({_flag_key(name)})")
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
        if not ENV_FILE.is_file():
            log.error(f"No .env at {ENV_FILE} — run ./{SCRIPT_NAME} install first.")
            return 1
        return reconcile(stop_orphans=stop_orphans)

    if not name:
        log.error(f"./{SCRIPT_NAME} plugin {action} <name>  — plugin name required")
        log.detail(f"  Known plugins: {', '.join(PLUGINS)}")
        return 1
    if name not in PLUGINS:
        log.error(f"Unknown plugin: '{name}'")
        log.detail(f"  Known plugins: {', '.join(PLUGINS)}")
        return 1
    if not ENV_FILE.is_file():
        log.error(f"No .env at {ENV_FILE} — run ./{SCRIPT_NAME} install first.")
        return 1

    if action == "enable":
        return enable(name)
    return disable(name, stop_orphans=stop_orphans)

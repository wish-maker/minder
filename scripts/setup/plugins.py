"""`plugin` verb — enable/disable first-party plugins + reconcile their infra.

First slice of the container control-plane (Adım 1). Today it manages the
`telegraf` plugin only; the model is built to generalise (Adım 2 adds a
metadata-driven reconcile over every plugin + real refcounting).

State lives in **.env** (the single source of truth, same as `ollama-mode`):

    PLUGIN_<NAME>_ENABLED=1|0     absent → enabled

The default-enabled-when-absent rule is deliberate: `start_services` reads the
same flag, so a stack with no PLUGIN_* keys behaves exactly as before and the
setup behaviour-gate stays byte-identical (the disabled branch is new surface the
frozen bash reference never had, and the gate never sets the flag).

Each plugin declares its container dependencies in two tiers:

    owned    containers that exist ONLY for this plugin  → stopped on disable
    shared   datastores other services also use          → left running

`influxdb` is shared (Grafana reads it; any plugin may write it), so disabling
telegraf stops the agent but keeps influxdb + its volume — exactly the
"keep the datastore, stop the collector" behaviour we want. Real cross-plugin
refcounting of shared stores is Adım 2; for now shared containers are only ever
brought UP, never torn down.

Every action funnels through `docker compose` so the compose file stays the
single source of truth — no imperative docker.sock start/stop.
"""

from . import config, docker, env, log

SCRIPT_NAME = config.SCRIPT_NAME
ENV_FILE = config.ENV_FILE

# name → {owned: containers 1:1 with the plugin, shared: datastores others use}
PLUGINS: dict[str, dict[str, tuple[str, ...]]] = {
    "telegraf": {"owned": ("telegraf",), "shared": ("influxdb",)},
}

_ACTIONS = ("enable", "disable", "status")


def _flag_key(name: str) -> str:
    return f"PLUGIN_{name.upper()}_ENABLED"


def is_enabled(name: str) -> bool:
    """True unless .env explicitly disables the plugin. Absent key → enabled, so
    the default start path (and thus the gate) is unchanged."""
    raw = env.get(_flag_key(name))
    if raw == "":
        return True
    return config._truthy(raw)


def _set_flag(name: str, on: bool) -> None:
    """Upsert PLUGIN_<NAME>_ENABLED=1|0 in .env (sed-style, mirroring ollama.py):
    replace every matching line, else append. newline="" so we never translate
    \\n<->\\r\\n and mangle the file cross-OS. DRY_RUN previews without writing,
    so the compose calls (already gated) are the only echoed effects."""
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
        # keep the trailing newline tidy whether or not the file ended in one
        sep = "" if raw.endswith("\n") or raw == "" else "\n"
        new_raw = f"{raw}{sep}{prefix}{value}\n"
    with ENV_FILE.open("w", encoding="utf-8", newline="") as fh:
        fh.write(new_raw)


def enable(name: str) -> int:
    spec = PLUGINS[name]
    already = is_enabled(name)
    _set_flag(name, True)
    if already:
        log.info(f"Plugin '{name}' already enabled — ensuring its containers are up.")
    else:
        log.success(f"Plugin '{name}' → enabled ({_flag_key(name)}=1)")
    # Bring up shared datastores first (compose depends_on still orders/health-gates
    # the owned agent), then the owned containers. One `up` command per group keeps
    # the emitted commands close to start_services' shape.
    services = (*spec["shared"], *spec["owned"])
    docker.compose("up", "-d", *services)
    log.detail(f"Reconciled: {', '.join(services)}")
    return 0


def disable(name: str) -> int:
    spec = PLUGINS[name]
    _set_flag(name, False)
    log.success(f"Plugin '{name}' → disabled ({_flag_key(name)}=0)")
    owned = spec["owned"]
    # Stop only the owned containers; shared datastores (e.g. influxdb) stay up for
    # their other consumers, and no volume is removed. `stop` (not `down`) so the
    # container definition + any data volume survive an enable later.
    docker.compose("stop", *owned)
    if spec["shared"]:
        log.detail(
            f"Kept shared: {', '.join(spec['shared'])} (other services use these)"
        )
    log.detail(f"Stopped: {', '.join(owned)}")
    return 0


def status() -> int:
    log.section("🔌  Plugin Container Lifecycle")
    for name, spec in PLUGINS.items():
        state = "enabled" if is_enabled(name) else "disabled"
        log.info(f"{name}  [{state}]  ({_flag_key(name)})")
        for tier in ("owned", "shared"):
            for svc in spec[tier]:
                running = docker.container_running(svc)
                health = docker.container_health(svc) if running else "stopped"
                mark = "✓" if running else "·"
                log.detail(f"  {mark} {svc:<12} {tier:<7} {health}")
    return 0


def run(action: str = "", name: str = "") -> int:
    if action not in _ACTIONS:
        log.error(
            f"Usage: ./{SCRIPT_NAME} plugin enable|disable <name>  |  plugin status"
        )
        log.detail(f"  Known plugins: {', '.join(PLUGINS)}")
        return 1
    if action == "status":
        return status()

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

    return enable(name) if action == "enable" else disable(name)

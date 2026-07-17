# Minder Plugins (first-party module plugins)

First-party plugins live here, one directory per plugin. They are **fixed handlers
that ship in the repo** — not user-uploaded code (the platform runs no arbitrary
uploaded code by design). `telegraf/` is the reference implementation; copy it as
the template for new plugins.

Name a plugin for its **responsibility**: `telegraf` manages the telegraf config +
reload; a future `network` plugin would do network discovery (scan IPs) and feed
targets into `telegraf`'s managed region. Don't conflate the two.

## How they load

- The plugin-registry bind-mounts this directory to `/app/plugins:ro`
  (`PLUGINS_PATH=/app/plugins`) and calls `load_plugins_from_disk()` on startup
  (`core/plugin_loader.py`).
- Because it's a bind mount, you **do not rebuild** the image to iterate — edit the
  plugin and `docker restart minder-plugin-registry`, then check
  `curl http://localhost:8001/v1/plugins`.
- Discovery per directory: a `manifest.{json,yml,yaml}` is loaded as a
  **manifest plugin**; otherwise an `__init__.py` is loaded as a **module plugin**
  (imported as `plugins.<dir>`, so the dir name must be a valid Python identifier).

## Module-plugin contract

The loader picks the class named in `__all__` (else the first class defining
`register`), instantiates it with a storage-config dict, then drives it:

```python
class MyPlugin:
    def __init__(self, config: dict | None = None): ...   # config: {database, redis, influxdb}

    async def register(self) -> PluginMetadata: ...        # returns metadata (see below)
    async def initialize(self) -> None: ...                # startup hook
    async def health_check(self) -> dict: ...              # MUST return {"healthy": bool, ...}
    async def collect_data(self) -> dict: ...              # hourly loop + POST /v1/plugins/<n>/collect
    async def analyze(self) -> dict: ...                   # on-demand analysis
    async def shutdown(self) -> None: ...                  # teardown hook
```

`register()` returns a `PluginMetadata` — import the shared one, don't redefine it:

```python
from plugins._contract import PluginMetadata   # name/version/description/author/
                                                # dependencies/capabilities/
                                                # data_sources/databases/registered_at
```

`plugins._contract` also exposes a `Plugin` `Protocol` documenting the full lifecycle
(type-check against it if you like; plugins are duck-typed so inheriting is optional).
It's a module, not a plugin dir, so the loader never tries to load it.

### Invoking plugin actions (writes)

Reads use `POST /v1/plugins/<name>/collect` (→ `collect_data`) and
`GET /v1/plugins/<name>/analysis` (→ `analyze`). For **state-changing** actions,
a plugin declares a class-level `ACTIONS` frozenset of method names and they become
callable over HTTP:

```
POST /v1/plugins/<name>/actions/<method>   (JWT required; JSON body → method kwargs)
```

Only names in `ACTIONS` are reachable — nothing else on the instance. Example
(telegraf: `ACTIONS = {set_managed_region, clear_managed_region, reload}`):

```bash
curl -X POST http://localhost:8001/v1/plugins/telegraf/actions/set_managed_region \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"body": "[[inputs.internal]]\n  collect_memstats = false"}'
```

### Gotchas (verified live)

- **`health_check()` must return `{"healthy": <bool>}`.** The monitoring loop reads
  `health.get("healthy")`; any other key (e.g. `"status"`) is treated as unhealthy.
- Keep runtime deps to what the registry image already ships (stdlib + `httpx`,
  `influxdb-client`). Anything else must be added to the service's
  `requirements.txt` and the image rebuilt.
- The manual `POST /v1/plugins/<name>/collect` endpoint requires a Bearer JWT; the
  hourly `collect_data` loop runs unauthenticated inside the service.

## Known limitation — module plugins don't expose AI/function-calling tools

The loader treats a plugin dir as **either** manifest-based **or** module-based —
a `manifest.{json,yml,yaml}` takes precedence over `__init__.py` (see
`plugin_loader.load_plugins_from_disk`). So a module plugin (like `telegraf`)
**cannot also ship a manifest** to appear in `GET /v1/plugins/ai/tools` without the
loader instantiating it as a manifest plugin and never creating the class instance.
Module plugins are therefore invoked via the `actions` endpoint above, not via the
AI-tool aggregation. Exposing module-plugin actions as AI tools needs a loader
change (load the manifest for tools AND the module for the instance) — tracked
separately, not wired here.

## Status

- `telegraf/` — manages the telegraf config's "managed region" and reloads telegraf
  (watch-config `poll`, with a docker-restart fallback). Reference/template.
  **Implemented.** Needs the plugin-registry wiring in `docker-compose.yml`:
  `TELEGRAF_CONFIG_PATH` (writable telegraf.conf mount), `TELEGRAF_CONTAINER`, and
  `/var/run/docker.sock` (restart fallback only).
- `network/` (v2) — host/service/SNMP discovery: **nmap** connect scan (`-sT -sV`,
  no root) for open ports + service/product/version, and **SNMP OID lookup** (system
  group via `snmpget`) for SNMP hosts; falls back to a stdlib TCP probe if nmap is
  absent. Emits telegraf inputs (`net_response` per port + `[[inputs.snmp]]` per SNMP
  host) — compose with `telegraf`: GET network `/analysis` → POST its
  `telegraf_config` to telegraf's `set_managed_region`. **Implemented.** Config:
  `NETWORK_SCAN_TARGETS` (empty → scans nothing), `NETWORK_SCAN_PORTS`,
  `NETWORK_SCAN_MAX_HOSTS`, `NETWORK_SNMP_ENABLED`, `NETWORK_SNMP_COMMUNITY`.
  Needs `nmap` + `snmp` in the plugin-registry image (in the Dockerfile).
- crypto / weather / news / tefas — aspirational (issue #34); not yet implemented.
  Do not add them to `default_plugins.yml` until their modules exist here.

# Minder Plugins (first-party module plugins)

First-party plugins live here, one directory per plugin. They are **fixed handlers
that ship in the repo** — not user-uploaded code (the platform runs no arbitrary
uploaded code by design). `network/` is the reference implementation; copy it as
the template for new plugins.

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

`register()` returns an object with these attributes (a dataclass is fine — see
`network/__init__.py`): `name, version, description, author, dependencies,
capabilities, data_sources, databases, registered_at` (a `datetime` — the loader
calls `.isoformat()` on it).

### Gotchas (verified live)

- **`health_check()` must return `{"healthy": <bool>}`.** The monitoring loop reads
  `health.get("healthy")`; any other key (e.g. `"status"`) is treated as unhealthy.
- Keep runtime deps to what the registry image already ships (stdlib + `httpx`,
  `influxdb-client`). Anything else must be added to the service's
  `requirements.txt` and the image rebuilt.
- The manual `POST /v1/plugins/<name>/collect` endpoint requires a Bearer JWT; the
  hourly `collect_data` loop runs unauthenticated inside the service.

## Status

- `network/` — TCP-connect latency to public endpoints (stdlib only, no secrets).
  Reference/template. **Implemented.**
- crypto / weather / news / tefas — aspirational (issue #34); not yet implemented.
  Do not add them to `default_plugins.yml` until their modules exist here.

# plugin-registry

Minder's plugin control plane (`:8001`, FastAPI, ~3.8k LOC). It registers and
runs the manifest-based plugins, exposes their data-collection **actions**, is the
**service-discovery** registry, and hosts the **bundle** control-plane (enable/
disable capability groups → start/stop their containers via the socket-proxy).
Interactive docs at `/docs`.

Plugins are **manifest-based and run no arbitrary code by design** — a new action
is a fixed handler in a first-party module, never uploaded code. Two module
plugins ship in `src/plugins/` (`telegraf/`, `network/`); the registry's disk
loader is what registers them on startup.

## Run / check

```bash
bash setup.sh start plugin-registry

curl http://localhost:8001/health
curl http://localhost:8001/v1/plugins                     # registered plugins
curl http://localhost:8001/v1/bundles                     # bundles + their services + claim graph
curl http://localhost:8001/v1/services                    # service-discovery registry

python scripts/dev/dev.py mypy plugin-registry
DB_PASSWORD=x JWT_SECRET=<32ch> REDIS_PASSWORD=x python -m pytest tests/unit/test_plugin_registry_*.py
```

## What it does

- **Plugin lifecycle** (`routes/plugins.py`, `core/plugin_loader.py`,
  `core/state.py`): load modules from disk → `register` → `initialize` (READY) →
  a 60s `health_check` loop → `collect_data` (hourly or manual) → `analyze` →
  `shutdown`. Install/enable/disable/delete + per-plugin `health`. A module's
  `health_check()` must return `{"healthy": bool}`.
- **Actions** (`routes/plugins.py`, `core/execution_engine.py`): a plugin's fixed
  data-collection handlers, listed at `GET /v1/plugins/{name}/actions/{action}`
  and run via `POST` — e.g. the `network` plugin's nmap/SNMP discovery composes
  into the `telegraf` plugin's managed-region config.
- **Plugin config** (`core/plugin_config.py`): central per-plugin settings —
  `GET`/`PUT /v1/plugins/{name}/config` (#116/#117).
- **Service discovery** (`routes/services.py`): `register` / list / get / delete /
  `health` for downstream services; the proxy resolves them by name. Registration
  is auth-gated (SSRF fix #216).
- **Bundles** (`routes/bundles.py`, `shared/bundle_graph.py`): capability groups
  derived from `minder.bundle=` compose labels. `enable` / `disable` (report
  orphans; `--stop-orphans` to tear down) / `reconcile`; state in a secret-free
  `bundles.state.json`. Enacts container start/stop through the docker-socket-proxy
  (#65 items 1–3, #201/#202).
- **Containers** (`routes/containers.py`): `GET /v1/containers/{name}/logs` —
  JWT-gated, allowlisted, via the socket-proxy (no raw docker.sock).
- **AI tools** (`routes/ai_tools.py`): aggregates plugins' registered AI-tool
  schemas at `/v1/plugins/ai/tools` for the gateway's function-calling bridge.
- **Webhooks** (`core/webhooks.py`): `POST /webhook/{path}` inbound triggers +
  reload.
- **Marketplace sync** (`core/marketplace_sync.py`): pushes module `AI_TOOLS` into
  the marketplace catalog (`SERVICE_SYNC_TOKEN` service-auth, #87).

## Layout

```
plugin-registry/
├── main.py                 # thin app: lifespan (disk-load plugins, start health loop) + routers
├── routes/
│   ├── plugins.py          # register/install/enable/disable/delete, health, collect, actions, config
│   ├── bundles.py          # /v1/bundles enable/disable/reconcile (capability control-plane)
│   ├── services.py         # /v1/services service-discovery registry
│   ├── containers.py       # /v1/containers/{name}/logs via socket-proxy
│   ├── ai_tools.py         # /v1/plugins/ai/tools aggregation
│   └── proxy.py            # /v1/proxy resolve-and-forward
├── core/
│   ├── plugin_loader.py    # disk module discovery + import
│   ├── execution_engine.py # run a plugin action handler
│   ├── plugin_config.py    # central per-plugin config store
│   ├── webhooks.py         # inbound webhook triggers + reload
│   ├── marketplace_sync.py # push AI_TOOLS → marketplace catalog
│   ├── monitoring.py       # the 60s health_check loop
│   ├── database.py         # Postgres persistence
│   └── state.py            # in-process plugin registry state
├── schemas/                # mvp_manifest + validator (plugin manifest contract)
├── models/__init__.py      # Pydantic request/response models
└── config.py               # Settings (bundle paths, socket-proxy, sync token)
```

## Configuration (`config.py`, env-overridable)

- `BUNDLES_COMPOSE_PATH` (`/app/bundles/docker-compose.yml`, read-only mount — the
  bundle map source of truth via `minder.bundle=` labels) and `BUNDLES_STATE_PATH`
  (`/app/bundles/bundles.state.json`, the secret-free enable-state).
- The docker-socket-proxy address (bundle start/stop + container logs).
- `SERVICE_SYNC_TOKEN` — service-auth for the marketplace catalog push (must be in
  `SECRET_SPEC`, #227).
- Secrets (`DB_PASSWORD`/`REDIS_PASSWORD`/`JWT_SECRET`) from `MinderBaseSettings`.

Deliberately omits `JWT_SECRET` from its own settings — the shared middleware owns
JWT verification (#223).

## Notes

- The `network` plugin needs `nmap` + `snmp` in the image; `telegraf` reloads via
  `--watch-config=poll` with a docker.sock restart fallback.
- `default_plugins.yml` is an intentional empty stub (the plugin-state-manager's
  separate bootstrap) — the registry's disk loader is what registers the shipped
  modules. Don't populate it until real plugin impls ship (#34).
- Plugin vs bundle are distinct: a plugin is a manifest/module; a bundle is a group
  of services. See `docs/architecture/bundles.md` and `src/plugins/README.md`.

## Error conventions

Platform-wide `{"detail": ...}` shape + 4xx-for-bad-input / sanitized-5xx — see
**[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_plugin_registry_*.py` + `test_plugin_config.py` /
`test_bundle_graph.py` (loaded by-path, per the one-process conftest harness):
plugin lifecycle, action execution, config get/put, the bundle claim-graph derivation,
and the service-discovery auth gate.

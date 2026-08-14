# plugin-state-manager

Plugin enable/disable **state** + license-gated **AI-tool execution**
(`:8003`, FastAPI, ~2k LOC). It tracks which plugins are enabled, discovers the
tools they expose, and executes a tool only after validating the caller's license
tier — **fail-closed**. Interactive docs at `/docs`.

Sits alongside plugin-registry: the registry owns plugin *lifecycle* + module
loading; this service owns plugin *enablement state* and *tool execution with
licensing*. It reads the tool catalog from the marketplace.

## Run / check

```bash
bash setup.sh start plugin-state-manager   # needs the marketplace DB + registry/marketplace reachable

curl http://localhost:8003/health
curl http://localhost:8003/v1/plugins/state                # plugin enable/disable state
curl http://localhost:8003/v1/tools                        # discoverable AI tools

python scripts/dev/dev.py mypy plugin-state-manager
DB_PASSWORD=x JWT_SECRET=<32ch> REDIS_PASSWORD=x python -m pytest tests/unit/test_plugin_state_manager_*.py
```

## Endpoints (see `/docs` for schemas)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/v1/plugins/state` | List plugin enable/disable state |
| GET | `/v1/plugins/state/{plugin_name}` | State of one plugin |
| POST | `/v1/plugins/state/{plugin_name}/enable` / `/disable` | Toggle a plugin's enabled state |
| PATCH | `/v1/plugins/state/{plugin_name}` | Partial state update |
| GET | `/v1/plugins/{plugin_name}/dependencies` | A plugin's declared dependencies |
| POST | `/v1/plugins/{plugin_name}/dependencies/resolve` | Resolve/validate those dependencies |
| GET | `/v1/tools` | Discover all AI tools exposed by enabled plugins |
| GET | `/v1/tools/{tool_name}` | One tool's schema |
| POST | `/v1/tools/{tool_name}/execute` | Execute a tool — **license-validated first** (fail-closed) |
| GET | `/v1/tools/plugins/{plugin_id}/tools` | Tools for a specific plugin |
| POST | `/v1/tools/validate` | Validate a license without executing |
| GET | `/v1/licensing/plugins/{plugin_name}/license/tier` | Get a plugin's required license tier |
| POST | `/v1/licensing/plugins/{plugin_name}/license/validate` | Validate a license for a plugin |
| PATCH | `/v1/licensing/plugins/{plugin_name}/license` | Update a plugin's required tier |

## Licensing (fail-closed)

`core/license.py` checks the caller's tier against the tool's `required_tier`
(`community` default, ranked via `shared.models.tiers`). Missing/invalid license →
denied, not allowed. **Dev override:** `MINDER_ALLOW_UNVALIDATED_LICENSES=1`
bypasses validation for local work (#47) — never set in prod.

## Layout

```
plugin-state-manager/
├── main.py                  # thin app: include state / tools / licensing routers
├── routes/
│   ├── state.py             # /v1/state — enable/disable/list/get
│   ├── tools.py             # /v1/tools — discovery + license-gated execute + validate
│   └── licensing.py         # /v1/plugins/{name}/license — tier get/validate
├── core/
│   ├── license.py           # tier check (fail-closed) + dev override
│   ├── execution.py         # run a tool's handler
│   ├── database.py          # marketplace-DB access (tool catalog, tiers)
│   ├── default_plugins.py   # the separate bootstrap (default_plugins.yml — intentional empty stub, #34)
│   └── state.py             # in-process enablement state
├── models/                  # plugin_state + tool_execution Pydantic models
└── config.py                # Settings (marketplace DB, MARKETPLACE_URL, PLUGIN_REGISTRY_URL)
```

## Configuration (`config.py`)

- `DB_NAME` (`minder_marketplace`) + the marketplace DB connection — the tool
  catalog + tiers live there.
- `MARKETPLACE_URL` (`http://minder-marketplace:8002`), `PLUGIN_REGISTRY_URL`
  (`http://minder-plugin-registry:8001`).
- Secrets (`DB_PASSWORD`/`REDIS_PASSWORD`/`JWT_SECRET`) from `MinderBaseSettings`.

> `default_plugins.yml` stays an intentional empty stub — this service's separate
> bootstrap, distinct from the registry's disk loader (which already registers
> the shipped crypto/weather/news/tefas/network/telegraf modules, #34 done).
> Whether to populate this stub is independent of those modules existing.

## Error conventions

Platform-wide `{"detail": ...}` shape + 4xx-for-bad-input / sanitized-5xx; a denied
license is a clean 4xx. See
**[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_plugin_state_manager_*.py` — the enable/disable state flow, tool
discovery, and the fail-closed license gate on execute (loaded by-path per the
one-process conftest harness).

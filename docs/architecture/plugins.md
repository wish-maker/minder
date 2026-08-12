# Minder Plugin Architecture

> **Last Updated:** 2026-08-12

## Overview

Minder runs **no arbitrary plugin-supplied code** by design — every plugin action is a fixed,
reviewed handler that ships in the repo. This is a deliberate security constraint (the platform is
internet-exposed): new actions must be implemented as fixed handlers, not uploaded as code.

The loader supports **two plugin flavours** (see `src/plugins/README.md`):

- **Manifest plugins** — declared by a `manifest.{json,yml,yaml}` and driven by built-in handlers.
  Registered over the API and seeded from `default_plugins.yml` (an **intentionally empty** stub).
- **Module plugins** — first-party Python classes under `src/plugins/<name>/`, bind-mounted into
  the registry (`/app/plugins:ro`) and loaded on startup by `load_plugins_from_disk()`. Still
  first-party code, not user uploads.

Plugin lifecycle and discovery are handled by the **Plugin Registry** service (`:8001`), with
runtime state and AI-tool execution handled by the **Plugin State Manager** (`:8003`).

> **Six module plugins ship today** (`telegraf`, `network`, `crypto`, `weather`, `news`, `tefas`
> — see [Shipped Plugins](#shipped-plugins)); #34 is done. All six load from disk on registry
> startup; four (`crypto`, `weather`, `news`, `tefas`) declare a `CONFIG_SCHEMA` reachable via
> `GET/PUT /v1/plugins/{name}/config`. `telegraf`/`network` have no schema (configured via
> Compose env vars instead — see their own sections below) — the config route degrades
> gracefully for them (`"configurable": false`, empty schema) rather than erroring. The
> plugin-state-manager bootstrap `default_plugins.yml` remains an empty stub — a separate mechanism.

## Plugin Lifecycle

The lifecycle implemented in code is a set of methods a plugin (and the registry) move through:

| Stage | Method | Notes |
|-------|--------|-------|
| Register | `register()` | Returns plugin metadata (the only required method) |
| Initialize | `initialize()` | Prepares the plugin; transitions it to READY |
| Health | `health_check()` | Polled on a ~60s loop by the registry |
| Collect | `collect_data()` | Runs hourly or on manual trigger |
| Analyze | `analyze()` | Optional analysis step |
| Shutdown | `shutdown()` | Graceful teardown |

Plugins can additionally be **enabled** / **disabled** at runtime.

> Conceptually this can be framed as a state progression (registered → ready → active → disabled),
> but the code reality is the method set above. Older docs described named hooks
> (`on_register`, `on_install`, `on_activate`, etc.) — those are **not** present in the code and
> should not be relied on.

## Storage Backends Available to Plugins

Plugins may read/write the platform's internal stores (all reached over the internal Docker
network, not host ports):

- **PostgreSQL** — structured/relational data
- **Qdrant** — vector embeddings (semantic search)
- **Neo4j** — graph relationships (entity linking, correlation)
- **MinIO** — raw files and artifacts
- **InfluxDB** — time-series data
- **RabbitMQ** — async events / pipeline triggers

## Shipped Plugins

Six first-party **module plugins** ship in `src/plugins/` and load on registry startup
(`telegraf`, `network`, `crypto`, `weather`, `news`, `tefas`) — all fixed handlers, not user
uploads. See `src/plugins/README.md` for the full contract.

### `telegraf` — config-manager (reference implementation)

Owns a delimited **managed region** of `telegraf.conf` and reloads telegraf (watch-config `poll`,
with a docker-restart fallback via `docker.sock`). It ships the region **empty** and fills it at
runtime — never hand-edit inside the markers.

- **Actions** (`POST /v1/plugins/telegraf/actions/<method>`, JWT): `set_managed_region`,
  `clear_managed_region`, `reload`.
- **Compose wiring**: `TELEGRAF_CONFIG_PATH` (writable telegraf.conf mount), `TELEGRAF_CONTAINER`,
  and `/var/run/docker.sock` (restart fallback only).
- **Container lifecycle**: telegraf belongs to the **`monitoring` bundle** — the whole
  observability stack is enabled/disabled together via `./setup.sh bundle enable|disable
  monitoring [--stop-orphans]`. Enable-state lives in `bundles.state.json` (a dedicated,
  **secret-free** file — not `.env` — so the network-facing registry can safely share it) and
  `start` honours it. A service stays up while ≥1 enabled bundle claims it; disabling a bundle
  reports its now-orphaned services and stops them only on `--stop-orphans`. Every action funnels
  through `docker compose` — compose stays the single source of truth. See the full model,
  vocabulary, and roadmap in **[bundles.md](bundles.md)** (registry-API + capacity-aware inference
  routing are planned there).

### `network` — nmap + SNMP discovery (v2)

Autonomous host/service/SNMP discovery loop that fans findings into telegraf, PostgreSQL, Neo4j,
and RabbitMQ. Uses an **nmap** connect scan (`-sT -sV`, no root) for open ports + service/version,
and **SNMP OID lookup** (`snmpget`, v2c/v3) for SNMP hosts; falls back to a stdlib TCP probe if
nmap is absent. Composes with `telegraf`: `GET network /analysis` → `POST` its `telegraf_config`
to telegraf's `set_managed_region`.

- ⚠️ **Scans nothing until you opt in** via `NETWORK_SCAN_TARGETS` (comma-separated hosts/CIDRs).
  Only scan infrastructure you own or are authorised to scan.
- **Config** (see `.env.example` for the full set): `NETWORK_SCAN_TARGETS`, `NETWORK_SCAN_PORTS`,
  `NETWORK_SCAN_MAX_HOSTS`, `NETWORK_SNMP_ENABLED`, `NETWORK_SNMP_COMMUNITY`, self-expanding
  discovery (`NETWORK_AUTO_EXPAND`), and per-sink toggles (`NETWORK_SINK_*`).
- **Image**: needs `nmap` + `snmp` in the plugin-registry Dockerfile.

## AI Tools (Ollama function-calling)

Plugins advertise **AI tools** for Ollama function-calling; `GET /v1/plugins/ai/tools`
aggregates them into OpenAI/Ollama tool definitions.

- A **module plugin** declares tools in code via an `AI_TOOLS` class attribute — a list
  of `{name, description, parameters (JSON Schema), action}` where `action` is one of the
  plugin's `ACTIONS` (so the tool maps to `POST /v1/plugins/<name>/actions/<action>`).
  See `src/plugins/_contract.py`; the `network` plugin is the reference (`network_scan`,
  `network_reconcile`). Module plugins no longer need a manifest to appear in the
  aggregation (#60).
- A **manifest plugin** lists the same shape under its manifest's `ai_tools` key.

Tool schema (OpenAI/Ollama):
```json
{ "name": "...", "description": "...", "parameters": { "type": "object", "properties": {} }, "action": "..." }
```

**End-to-end function-calling** runs through the API Gateway's
`POST /v1/ai/chat/completions` with `"minder_tools": true` (opt-in — without it, chat is
a plain Ollama passthrough). The gateway offers the aggregated tools to Ollama, executes
any `tool_calls` against the plugin action endpoints **forwarding the caller's JWT** (tools
run as the calling user), and feeds results back for the final answer. A tool failure (e.g.
a 401 when unauthenticated) is fed back to the model, never aborting the chat.

**Read-only actions bypass JWT entirely (#254):** a plugin can additionally declare a
`READ_ONLY_ACTIONS` subset of its `ACTIONS` (e.g. `get_weather`, `get_crypto_price`,
`get_fund_price`, `get_news`) that's reachable **unauthenticated** via
`GET /v1/plugins/<name>/actions/<action>?<query params>`, separate from the POST/JWT path
above. Only actions in that declared subset are exposed this way — mutating actions (e.g.
`refresh`) stay POST-only and JWT-gated. This exists because pure data-lookup tools were
previously gated behind the same JWT requirement as mutating actions purely because both
shared one POST route; a plugin author opts a method into this path deliberately, it isn't
automatic for every action.

## Plugin Dependencies & Required Services (#484)

Two distinct, easily-confused relationships a plugin can declare, both surfaced on the
**Available Plugins** page so a user doesn't have to guess them from behaviour:

- **`PluginMetadata.databases`** — backend *services* (in the [storage-backend list](
  #storage-backends-available-to-plugins) above) the plugin needs at runtime, e.g. `weather`
  declares `["influxdb"]`. Synced into the marketplace catalog as `requires_services` and
  rendered as **"Needs: influxdb"** on the plugin's card — the piece that tells a user *why*
  a plugin might not work yet (its bundle isn't enabled) without them having to inspect bundle
  claims themselves. Not a dependency edge — no graph entry.
- **`PluginMetadata.dependencies`** — other **plugins** this one requires to function, e.g.
  `network` declares `["telegraf"]` because it pushes discovered hosts into telegraf's managed
  config region at runtime (see `network` in [Shipped Plugins](#shipped-plugins)). This *is* a
  graph edge: on every load, `plugin-registry`'s `marketplace_sync.py` resolves each declared
  dependency to its marketplace plugin id (creating a bare placeholder row if the target hasn't
  synced yet — a pure lookup-or-bare-create, never overwriting a target's real metadata) and
  records a `requires` edge via marketplace's `POST /v1/graph/dependencies`. One failed edge
  doesn't block the rest — best-effort per dependency.

Marketplace persists the edges in **Neo4j** (`DEPENDS_ON`/`RECOMMENDS`/`CONFLICTS_WITH`
relationships, keyed by `dependency_type` — `requires`/`suggests`/`conflicts_with`) and exposes
them read-only:

```bash
GET /v1/graph/dependencies/{plugin_id}   # direct + transitive deps (BFS depth)
GET /v1/graph/conflicts/{plugin_id}      # declared conflicts
```

A plugin's card on **Available Plugins** has a collapsible **"Dependencies & conflicts"** panel
(lazy-fetched on first expand) rendering **"Depends on: telegraf"** / **"Conflicts with: ..."**,
or a note that no relationship is recorded yet if the graph has nothing for that plugin —
the dependency graph is built incrementally as plugins declare relationships, not computed
up front.

## API Endpoints

Plugins are managed through the Plugin Registry (`:8001`), typically reached via the API Gateway
(`:8000`). Representative endpoints:

```bash
# List plugins (legacy alias: GET /plugins)
GET /v1/plugins

# Install / register a plugin
POST /v1/plugins/install

# Plugin details
GET /v1/plugins/{name}

# Enable / disable
POST /v1/plugins/{name}/enable
POST /v1/plugins/{name}/disable

# Plugin health
GET /v1/plugins/{name}/health
```

### Example
```bash
# List plugins via the gateway
curl http://localhost:8000/v1/plugins | jq

# Returns the six shipped module plugins (telegraf, network, crypto, weather, news, tefas).
# No manifest plugins are seeded — default_plugins.yml is an empty stub.
```

## Why Manifest-Based (No Code Execution)

- **Security**: the platform is internet-exposed (Raspberry Pi target), so running arbitrary
  plugin code is out of scope by design.
- **Predictability**: actions map to reviewed, fixed handlers.
- **Simplicity**: a plugin is a manifest plus configuration, not a code bundle to sandbox.

## Roadmap

All six module plugins (`telegraf`, `network`, `crypto`, `weather`, `news`, `tefas`) are
implemented and shipped (#34 done) — see [Shipped Plugins](#shipped-plugins). Remaining: the
TEFAS data fetch is blocked from non-TR egress (#120). The plugin-state-manager bootstrap
`default_plugins.yml` stays an empty stub (a separate mechanism). See `roadmap.md`.

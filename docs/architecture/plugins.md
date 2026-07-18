# Minder Plugin Architecture

> **Last Updated:** 2026-07-17

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

> **Two module plugins ship today** (`telegraf`, `network` — see [Shipped Plugins](#shipped-plugins)).
> The remaining domain plugins (crypto, weather, news, tefas) are still aspirational — not
> implemented, not registered (issue #34). `default_plugins.yml` remains an empty stub; populating
> it would try to register non-existent manifest plugins.

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

Two first-party **module plugins** ship in `src/plugins/` and load on registry startup. Both are
fixed handlers — not user uploads. See `src/plugins/README.md` for the full contract.

### `telegraf` — config-manager (reference implementation)

Owns a delimited **managed region** of `telegraf.conf` and reloads telegraf (watch-config `poll`,
with a docker-restart fallback via `docker.sock`). It ships the region **empty** and fills it at
runtime — never hand-edit inside the markers.

- **Actions** (`POST /v1/plugins/telegraf/actions/<method>`, JWT): `set_managed_region`,
  `clear_managed_region`, `reload`.
- **Compose wiring**: `TELEGRAF_CONFIG_PATH` (writable telegraf.conf mount), `TELEGRAF_CONTAINER`,
  and `/var/run/docker.sock` (restart fallback only).

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

> Module plugins are invoked via the `actions` endpoint, not the AI-tool aggregation — the loader
> treats a plugin dir as manifest-based **or** module-based, so a module plugin can't also ship a
> manifest to appear in `/v1/plugins/ai/tools` (tracked separately).

## AI Tools

Plugins may also register as **AI tools** for Ollama function calling. The registry aggregates
tools, the marketplace catalogs them, and the state manager executes them with license validation.

Tool schema:
```json
{ "name": "...", "description": "...", "input_schema": { }, "endpoint": "..." }
```

## API Endpoints

Plugins are managed through the Plugin Registry (`:8001`), typically reached via the API Gateway
(`:8000`). Representative endpoints:

```bash
# List plugins
GET /api/v1/plugins

# Register a plugin manifest
POST /api/v1/plugins/register

# Plugin details
GET /api/v1/plugins/{id}

# Enable / disable
POST /api/v1/plugins/{name}/enable
POST /api/v1/plugins/{name}/disable

# Plugin health
GET /api/v1/plugins/{name}/health
```

### Example
```bash
# List plugins via the gateway
curl http://localhost:8000/api/v1/plugins | jq

# Returns the two shipped module plugins (telegraf, network). No manifest
# plugins are seeded — default_plugins.yml is an empty stub.
```

## Why Manifest-Based (No Code Execution)

- **Security**: the platform is internet-exposed (Raspberry Pi target), so running arbitrary
  plugin code is out of scope by design.
- **Predictability**: actions map to reviewed, fixed handlers.
- **Simplicity**: a plugin is a manifest plus configuration, not a code bundle to sandbox.

## Roadmap

The `telegraf` and `network` module plugins are implemented (see [Shipped Plugins](#shipped-plugins)).
The remaining domain plugins (crypto/weather/news/tefas) — or formally dropping the aspiration —
are tracked as a GitHub issue (#34) in `wish-maker/minder`. Until real implementations exist,
`default_plugins.yml` must remain empty (populating it would try to register non-existent
manifest plugins). See `roadmap.md`.

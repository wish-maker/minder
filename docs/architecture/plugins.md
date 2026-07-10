# Minder Plugin Architecture

> **Last Updated:** 2026-07-10

## Overview

Minder uses a **manifest-based plugin system**. Plugins are declared by a manifest and driven by
fixed, built-in handlers — Minder does **not** execute arbitrary plugin-supplied code. This is a
deliberate security constraint: any new plugin action must be implemented as a fixed handler in
the platform, not as uploaded code.

Plugin lifecycle and discovery are handled by the **Plugin Registry** service (`:8001`), with
runtime state and AI-tool execution handled by the **Plugin State Manager** (`:8003`).

> **No default plugins ship today.** Domain plugins such as crypto, weather, network, news, and
> tefas are aspirational — they are not implemented and are not registered at runtime. The
> `default_plugins.yml` config is an intentional empty stub. Do not assume any of these plugins
> exist until real implementations land.

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

# With no default plugins implemented, this returns an empty list today.
```

## Why Manifest-Based (No Code Execution)

- **Security**: the platform is internet-exposed (Raspberry Pi target), so running arbitrary
  plugin code is out of scope by design.
- **Predictability**: actions map to reviewed, fixed handlers.
- **Simplicity**: a plugin is a manifest plus configuration, not a code bundle to sandbox.

## Roadmap

Implementing real domain plugins (crypto/weather/network/news/tefas) — or formally dropping the
aspiration — is tracked as a GitHub issue in `wish-maker/minder`. Until real implementations
exist, `default_plugins.yml` must remain empty (populating it would try to register
non-existent plugins). See `roadmap.md`.

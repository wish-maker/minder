# Minder Plugin Development Guide

> **Last Updated:** 2026-07-10
> **Platform Version:** 1.0.0
> **Plugins shipped:** six module plugins — telegraf, network, crypto, weather, news, tefas (see [Status](#status))

---

## Table of Contents

1. [Introduction](#introduction)
2. [Status](#status)
3. [Design Principles](#design-principles)
4. [Plugin Lifecycle](#plugin-lifecycle)
5. [Manifest](#manifest)
6. [Storage Access](#storage-access)
7. [AI Tools](#ai-tools)
8. [Registering a Plugin](#registering-a-plugin)
9. [Plugin Registry API](#plugin-registry-api)
10. [Troubleshooting](#troubleshooting)

---

## Introduction

Minder supports a plugin system for extending the platform — collecting data from external
sources, running analysis, and exposing capabilities to the rest of the stack — **without
modifying core services**.

Plugins are managed by the **plugin-registry** service (`minder-plugin-registry`, host port
`8001`). The **plugin-state-manager** service (`minder-plugin-state-manager`, `8003`) owns
plugin state and tool discovery/execution.

## Status

**Six module plugins ship** in `src/plugins/` and load on registry startup (#34 done):
`crypto`, `weather`, `network`, `news`, `tefas`, `telegraf`. They are real, working fixed
handlers (no arbitrary code execution) that declare a central `CONFIG_SCHEMA`
(`GET/PUT /v1/plugins/{name}/config`) and write to the platform's storage backends. Use them
as reference implementations of the contract described below. (The plugin-state-manager
bootstrap `default_plugins.yml` remains an empty stub — a separate mechanism, orthogonal to
these disk-loaded module plugins.)

## Design Principles

Two properties define the plugin system:

1. **Manifest-based.** A plugin is declared by a manifest describing its identity,
   capabilities, storage needs, and any AI tools it exposes. The registry reads the
   manifest to install and manage the plugin.

2. **No arbitrary code execution — by design (security).** The platform does **not**
   execute plugin-supplied arbitrary code as an extension mechanism. New actions must be
   implemented as **fixed, first-party handlers** in the codebase and referenced by the
   manifest. This is a deliberate security boundary: adding a new plugin action means
   adding a reviewed handler, not shipping executable payloads through the registry.

Because of principle 2, "writing a plugin" primarily means: (a) implementing a fixed
handler in the platform, and (b) declaring it via a manifest that the registry installs.

## Plugin Lifecycle

The lifecycle implemented in code (see `src/plugins/_contract.py`) is:

```
register() → initialize()  →  health_check()  →  collect_data()  →  shutdown()
              (READY)          (60s loop)          (hourly/manual)
                                    │
                                    └── analyze()  (on demand)
```

- **`register()`** — the plugin announces its metadata to the registry.
- **`initialize()`** — sets up resources/connections; plugin becomes **READY**.
- **`health_check()`** — polled by the registry on a ~60s loop for liveness.
- **`collect_data()`** — pulls data from the plugin's source (scheduled hourly or invoked
  manually).
- **`analyze()`** — runs analysis over collected data on demand.
- **`shutdown()`** — releases resources on disable/uninstall/platform shutdown.

Plugins can also be **enabled/disabled** through the registry.

> Some older docs frame the lifecycle as
> `REGISTERED → INSTALLED → ACTIVE → SUSPENDED → UNINSTALLED` with `on_*` hooks. That is a
> conceptual state view; the **code reality** is the `register/initialize/health_check/
> collect_data/analyze/shutdown` methods above. Prefer the code reality — do not invent
> hooks that are not in the code.

## Manifest

`POST /v1/plugins/install` validates the manifest against `schemas/mvp_manifest.py`'s
`MVP_MANIFEST_SCHEMA` — a Kubernetes-style envelope around a single, MVP-scoped shape:
webhook trigger → store-vector action. This is the **only** manifest shape the install
route accepts today; a manifest describing anything else (a different trigger/action
type, or the free-form `name`/`capabilities`/`storage`/`tools` shape older drafts of this
doc used) fails validation with a 422 listing the schema errors.

```yaml
apiVersion: minder.dev/v1alpha1   # only this value is accepted
kind: Plugin                      # only this value is accepted
metadata:
  name: discord-ingestor          # ^[a-z][a-z0-9-]*$, 2-63 chars
  version: 0.1.0                  # semantic version
  description: Ingest Discord messages to Qdrant
spec:
  trigger:
    type: webhook                 # only "webhook" is supported in the MVP schema
    webhook:
      path: /discord/webhook      # -> POST /webhook/discord/webhook
      secretRef: discord.webhook.secret   # optional
  action:
    type: store-vector            # only "store-vector" is supported in the MVP schema
    store:
      collection: discord-messages
      input:
        text: "{{ .content }}"           # template for the text to embed
        metadata:
          author: "{{ .author.username }}"
          timestamp: "{{ .timestamp }}"
      embedModel: all-minilm      # or nomic-embed-text, mxbai-embed-large
```

This exact example ships as `DISCORD_INGESTOR_EXAMPLE` in `mvp_manifest.py` — copy that
constant directly rather than retyping it. There is currently no manifest path for
declaring a plugin's `capabilities`/`storage`/`tools` the way the disk-loaded module
plugins (crypto/weather/network/news/tefas/telegraf) do in code — those six ship as
fixed Python handlers, not manifests; see [Status](#status) and [AI Tools](#ai-tools).

## Storage Access

Plugins may write to any of the platform's storage backends and publish async events. The
concrete backends:

| Backend | Container | Purpose |
|---------|-----------|---------|
| postgres | minder-postgres | structured / relational data |
| redis | minder-redis | cache / ephemeral state |
| qdrant | minder-qdrant | vector embeddings (semantic search) |
| neo4j | minder-neo4j | graph relationships / correlation |
| minio | minder-minio | raw files, artifacts, binaries |
| influxdb | minder-influxdb | time-series data |
| rabbitmq | minder-rabbitmq | async events / pipeline triggers (publish) |

All of these are **internal-only** (not exposed on host ports); plugins reach them over the
internal Docker network using service names.

## AI Tools

Plugins advertise **AI tools** that Ollama function-calling can invoke. `GET
/v1/plugins/ai/tools` (plugin-registry `:8001`) aggregates them into OpenAI/Ollama tool
definitions; the API Gateway drives the end-to-end loop.

A **module plugin** declares tools in code via an `AI_TOOLS` class attribute; a
**manifest plugin** lists the same shape under its manifest's `ai_tools` key:

```python
class MyPlugin:
    ACTIONS = frozenset({"get_example_metric"})   # the invocable methods

    AI_TOOLS = [
        {
            "name": "get_example_metric",
            "description": "What the tool does, for the model to reason about",
            "parameters": {                          # JSON Schema for the arguments
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
            "action": "get_example_metric",          # -> POST /v1/plugins/<name>/actions/<action>
        },
    ]
```

- `name` — unique tool identifier the model calls.
- `description` — natural-language description the model reasons about.
- `parameters` — JSON Schema for the tool's arguments (OpenAI/Ollama format).
- `action` — one of the plugin's `ACTIONS`; the tool maps to `POST
  /v1/plugins/<name>/actions/<action>` (or give an explicit `endpoint` instead).

**Invocation:** call the API Gateway's `POST /v1/ai/chat/completions` with
`"minder_tools": true`. The gateway offers the tools to Ollama, executes the model's
`tool_calls` against the action endpoints **as the calling user** (it forwards your JWT),
and feeds results back for the answer. See `src/plugins/_contract.py` and the `network`
plugin for a working reference.

## Registering a Plugin

Plugins register via the **plugin-registry** service (`:8001`) — this is the required path
per platform convention.

```bash
# Health / discovery
curl http://localhost:8001/health
curl http://localhost:8001/v1/plugins

# Enable / disable a plugin (JWT required)
curl -X POST http://localhost:8001/v1/plugins/<name>/enable -H "Authorization: Bearer <token>"
curl -X POST http://localhost:8001/v1/plugins/<name>/disable -H "Authorization: Bearer <token>"

# Plugin health
curl http://localhost:8001/v1/plugins/<name>/health
```

> Exact route prefixes may differ by version; inspect the running service
> (`curl http://localhost:8001/openapi.json`) for the authoritative API surface.

## Plugin Registry API

The registry also handles:

- Manifest install (no code execution).
- Webhook routes.
- A ~60s health loop over registered plugins.
- Service discovery recorded in Redis.
- AI-tool aggregation.
- Marketplace auto-sync.

The marketplace service (`:8002`) provides discovery/search/featured listings, license
tiers (community / pro / enterprise), an AI-tool catalog, and a plugin dependency graph
stored in Neo4j.

## Troubleshooting

### Plugin not appearing

```bash
# Check the registry is healthy
curl http://localhost:8001/health

# List registered plugins
curl http://localhost:8001/plugins

# Registry logs
docker logs minder-plugin-registry --tail 50
```

### Storage connectivity

Storage backends are internal-only. Test connectivity from inside a service container:

```bash
docker exec -it minder-plugin-registry bash
# then, from inside the container, connect using service names:
#   host=minder-postgres port=5432
#   host=minder-redis    port=6379
#   host=minder-qdrant   port=6333
```

### Health checks failing

The registry polls `health_check()` on a ~60s loop. If a plugin flaps, check its handler
logs and confirm its declared storage backends are reachable.

---

**Last Updated:** 2026-07-10
**Platform Version:** 1.0.0

# Minder Platform — API Reference

**Version:** 1.0.0
**Last Updated:** 2026-08-02
**Base URL (via API Gateway):** `http://localhost:8000`

---

## Overview

The Minder Platform exposes RESTful APIs from **8 core FastAPI microservices**. In front of
them sits **Traefik v3** as the reverse proxy (TLS termination, routing via Docker labels).

> **Development environment.** This is a development deployment on a Raspberry Pi 4.
> Production hardening is not yet fully applied. Authelia SSO is **enabled by default**
> and the Traefik forward-auth middleware is wired and **enforced** on five routers
> (minio, api-gateway, grafana, openwebui, jaeger) — unauthenticated requests get a 302
> redirect to the Authelia portal. Full browser SSO still needs real DNS + TLS on the
> deploy. The API Gateway itself implements real JWT + bcrypt authentication and
> Redis-backed rate limiting.

### Core API services

| Service | Container | Port | Summary |
|---------|-----------|------|---------|
| API Gateway | `minder-api-gateway` | 8000 | JWT+bcrypt auth, Redis rate-limit, httpx proxy to registry/rag/models, OpenWebUI function bridge |
| Plugin Registry | `minder-plugin-registry` | 8001 | Manifest install, health loop, service discovery, AI-tool aggregation |
| Marketplace | `minder-marketplace` | 8002 | Discovery/search/featured, license tiers, dependency graph (Neo4j) |
| Plugin State Manager | `minder-plugin-state-manager` | 8003 | Plugin state, tool discovery, tool execution, licensing |
| RAG Pipeline | `minder-rag-pipeline` | 8004 | Knowledge bases, doc ingest, Qdrant vectors; Standard/Conversational/HyDE/Self-RAG/auto/corrective RAG via the query `method` field + adaptive `rerank`/`compress` flags + `hybrid`/`parent_context` retrieval strategies (all wired — see `GET /capabilities`) |
| Model Management | `minder-model-management` | 8005 | Ollama list/pull/delete/test (some endpoints are placeholders) |
| TTS / STT | `minder-tts-stt` | 8006 | Text-to-speech (Piper offline default, WAV; gTTS fallback, MP3), speech-to-text (`speech_recognition`) |
| Graph-RAG | `minder-graph-rag` | 8008 | spaCy NER, Neo4j knowledge-graph construction and retrieval |

**Conventions used below**
- `ANY` = the route accepts `GET, POST, PUT, DELETE, PATCH`.
- `{path:path}` = a catch-all path segment (everything after the prefix is forwarded verbatim).
- Ports are the host-published ports; internally each service also sits behind Traefik.
- **`GET /health`** returns `200` (`healthy`/`degraded`) when the service is serviceable and **`503`** (`unhealthy`) when a *critical* dependency (its Postgres/Redis/Qdrant/Neo4j/Ollama) is unreachable. Each body carries a `status` field and a per-dependency `checks` map plus service-specific fields.

---

## Interactive Documentation

Every FastAPI service serves Swagger UI, ReDoc, and the raw OpenAPI spec on its own port:

```
http://localhost:<port>/docs          # Swagger UI (interactive)
http://localhost:<port>/redoc         # ReDoc
http://localhost:<port>/openapi.json  # OpenAPI schema
```

Ports: `8000` (gateway), `8001` (plugin-registry), `8002` (marketplace),
`8003` (plugin-state-manager), `8004` (rag-pipeline), `8005` (model-management),
`8006` (tts-stt), `8008` (graph-rag).

> The interactive `/docs` page for each service is the **authoritative, always-current**
> source for request/response schemas. The tables below enumerate every route as wired in
> code, but for exact field-level payloads use `/docs`.

---

## API Gateway — `http://localhost:8000`

Central entry point: authentication, rate limiting, request proxying, and the OpenWebUI
function-calling bridge.

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/auth/register` | Create a user — body `{username, email, password (≥8), role?}`. **201** on success, **409** if the username/email exists, **422** on a bad body |
| POST | `/v1/auth/login` | Obtain a JWT — body `{username, password}` → `{access_token, token_type, expires_in, user}` (**401** on bad creds) |
| POST | `/v1/auth/refresh` | Refresh an access token (bearer token in the `Authorization` header) → `{access_token, token_type, expires_in}` |

### Proxy routes

Forwarded over the internal Docker network via httpx to the backing service.

| Method | Path | Target |
|--------|------|--------|
| GET | `/v1/plugins` | plugin-registry (list) |
| ANY | `/v1/plugins/{path:path}` | plugin-registry |
| ANY | `/v1/rag/{path:path}` | rag-pipeline (prefix maps to the service root) |
| GET/POST | `/v1/models` | model-management `/models` (list / pull) |
| ANY | `/v1/models/{path:path}` | model-management `/models/{path}` — the gateway adds the `models/` resource segment, so use `/v1/models/{id}` (not the old `/v1/models/models/{id}`) (#147) |

### AI / OpenWebUI integration (`/v1/ai`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/ai/functions/definitions` | Aggregated AI-tool (function) definitions from all plugins, in OpenAI function schema |
| POST | `/v1/ai/functions/{function_name}` | Execute a named AI tool; proxied to the plugin's endpoint (forwards the caller's JWT), returned in OpenAI function-result format |
| POST | `/v1/ai/chat/completions` | Chat via Ollama. Plugin function-calling is **opt-in** via `"minder_tools": true` (the gateway offers plugin tools, executes the model's `tool_calls` against plugin actions forwarding the caller's JWT, and feeds results back). Without the flag it's a plain Ollama `/api/chat` passthrough |

### Ops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Gateway health + downstream dependency status (no auth) |
| GET | `/metrics` | Prometheus metrics |

**Authentication:** real JWT (HS256) with bcrypt-hashed credentials. Send
`Authorization: Bearer <token>` on protected routes.
**Rate limiting:** Redis-backed, 60-second window, **fail-open** (requests are allowed if
Redis is unreachable).

```bash
# Health
curl -s http://localhost:8000/health | jq '.status'

# Register + login
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "email": "admin@example.com", "password": "..."}'

TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}' | jq -r '.access_token')

# Proxied call
curl -s http://localhost:8000/v1/plugins -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

## Plugin Registry — `http://localhost:8001`

Plugin registration, discovery, and lifecycle management. Plugins are **manifest-based** —
there is **no arbitrary code execution** (security by design). The registry runs a 60-second
health loop, stores service-discovery data in Redis, and auto-syncs with the marketplace.

### Plugins

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/plugins` | List registered plugins (`GET /plugins` is a legacy alias) |
| GET | `/v1/plugins/{plugin_name}` | Plugin details |
| POST | `/v1/plugins/install` | Install a plugin from its manifest (fixed handlers only) |
| DELETE | `/v1/plugins/{plugin_name}` | Uninstall a plugin |
| POST | `/v1/plugins/{plugin_name}/enable` | Enable a plugin |
| POST | `/v1/plugins/{plugin_name}/disable` | Disable a plugin |
| POST | `/v1/plugins/{plugin_name}/collect` | Trigger a data-collection run |
| GET | `/v1/plugins/{plugin_name}/health` | Plugin health status |
| GET | `/v1/plugins/{plugin_name}/analysis` | The plugin's `analyze()` output, returned verbatim (schema is plugin-defined; the registry does not reshape it). 404 unknown / 403 disabled / 503 not-running |
| POST | `/v1/plugins/{plugin_name}/actions/{action}` | Invoke a plugin write/execute action (JWT-gated; only names in the plugin's `ACTIONS`) |
| GET | `/v1/plugins/{plugin_name}/config` | Config schema + effective values, secrets masked (JWT-gated) |
| PUT | `/v1/plugins/{plugin_name}/config` | Update config: validate → persist → apply live, no restart (JWT-gated) |
| GET | `/v1/plugins/ai/tools` | Aggregated AI-tool definitions across all plugins |

A browser UI for the two config endpoints above is served at
`GET /plugin-config` on the API Gateway itself (e.g.
`http://localhost:8000/plugin-config`, or via Traefik once reachable — see
`docs/guides/remote-access.md`) — a form-based settings page for
configurable plugins (news, weather, crypto, tefas today), instead of
hand-crafting these requests.

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/plugins/reload-webhook` | Re-register a plugin's webhook routes |
| POST | `/v1/force-webhooks` | Force re-registration of all webhook routes (JWT-gated; unversioned `/force-webhooks` kept as a deprecated alias) |
| POST | `/webhook/{path:path}` | Generic inbound webhook / event trigger |

### Service discovery

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/services/register` | Register a microservice for discovery |
| GET | `/v1/services` | List registered services |
| GET | `/v1/services/{service_name}` | Service details |
| GET | `/v1/services/{service_name}/health` | Check a registered service's health |
| DELETE | `/v1/services/{service_name}` | Unregister a service |
| GET | `/v1/proxy` | List services that can be proxied |
| ANY | `/v1/proxy/{service_name}/{path:path}` | Dynamic proxy to a registered service |

### Bundles

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/bundles` | The bundle model: each capability bundle, whether it's enabled, its claimed services, and per-service active/orphaned status. Derived from the Compose `minder.bundle=` labels + the secret-free enable-state via the shared brain (`shared.bundle_graph`). `503` if the compose file isn't mounted |
| POST | `/v1/bundles/{name}/enable` | Enable a bundle (JWT-gated). Persists intent to `bundles.state.json` (same file the host CLI writes) and starts already-materialised claimed containers via the least-privilege docker-socket-proxy — it cannot *create* new containers, so a never-materialised service comes back as `pending_create` until the next host `setup.sh start`/`restart` converge |
| POST | `/v1/bundles/{name}/disable` | Disable a bundle (JWT-gated); stops its claimed containers via the docker-socket-proxy, same persistence model as enable |
| POST | `/v1/bundles/reconcile` | Re-apply the persisted enable-state to running containers (JWT-gated) — start/stop drift correction without changing intent |

### Ops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health + plugin/service counts |
| GET | `/metrics` | Prometheus metrics |

> **Note:** Six first-party module plugins ship in `src/plugins/` and are loaded by
> the registry on startup — `crypto`, `weather`, `news`, `tefas`, `network`, `telegraf`
> (see `GET /v1/plugins`). (The plugin-state-manager bootstrap `default_plugins.yml`
> remains an intentional empty stub — that's a separate mechanism.)

---

## Marketplace — `http://localhost:8002`

Plugin/tool discovery, licensing, and dependency management. Catalog data lives in
PostgreSQL; the dependency/conflict graph is backed by **Neo4j**.

### Catalog (`/v1/marketplace`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/marketplace/plugins` | List catalog plugins — filterable; paginated via `limit`/`offset` (canonical; `page`/`page_size` accepted but deprecated). Response carries both `total`/`limit`/`offset` and `page`/`page_size`/`total_pages` |
| GET | `/v1/marketplace/plugins/search` | Full-text search (same `limit`/`offset` pagination) |
| GET | `/v1/marketplace/plugins/featured` | Featured plugins |
| GET | `/v1/marketplace/plugins/{plugin_id}` | Plugin details |
| POST | `/v1/marketplace/plugins` | Create a catalog entry (called by plugin-registry) |
| PUT | `/v1/marketplace/plugins/{plugin_id}` | Update catalog metadata (partial; display_name/description/pricing_model/base_tier/status/featured). 404 if unknown, 422 if empty |

### Installation management (`/v1/marketplace/plugins`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/marketplace/plugins/{plugin_id}/install` | Install from the catalog |
| DELETE | `/v1/marketplace/plugins/{plugin_id}/uninstall` | Uninstall |
| POST | `/v1/marketplace/plugins/{plugin_id}/enable` | Enable |
| POST | `/v1/marketplace/plugins/{plugin_id}/disable` | Disable |
| GET | `/v1/marketplace/plugins/{plugin_id}/installations` | List installations |

### AI-tool catalog (`/v1/marketplace/ai`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/marketplace/ai/tools` | List AI tools (filter by tier / active) |
| GET | `/v1/marketplace/ai/tools/{tool_name}` | Tool details |
| GET | `/v1/marketplace/ai/plugins/{plugin_id}/tools` | Tools for one plugin |
| POST | `/v1/marketplace/ai/sync` | Sync AI tools from a plugin manifest |
| DELETE | `/v1/marketplace/ai/plugins/{plugin_id}/tools` | Remove a plugin's tools |

### Licensing (`/v1/marketplace/licenses`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/marketplace/licenses` | List / inspect licenses |
| POST | `/v1/marketplace/licenses/validate` | Validate a license against a tier |
| POST | `/v1/marketplace/licenses/activate` | Activate a license |

### Dependency graph (`/v1/graph`, Neo4j-backed)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/graph/dependencies/{plugin_id}` | Resolve a plugin's dependencies |
| POST | `/v1/graph/dependencies` | Register/update dependency edges |
| GET | `/v1/graph/conflicts/{plugin_id}` | Detect conflicts |
| POST | `/v1/graph/recommendations` | Recommend related plugins |
| GET | `/v1/graph/health` | Dependency-graph subsystem health |

### Ops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

---

## Plugin State Manager — `http://localhost:8003`

Plugin state control, AI-tool discovery/execution, and per-plugin licensing.

### Plugin state (`/v1/plugins`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/plugins/state` | List all plugin states |
| GET | `/v1/plugins/state/{plugin_name}` | One plugin's state |
| POST | `/v1/plugins/state/{plugin_name}/enable` | Enable a plugin |
| POST | `/v1/plugins/state/{plugin_name}/disable` | Disable a plugin |
| PATCH | `/v1/plugins/state/{plugin_name}` | Update state fields |
| GET | `/v1/plugins/{plugin_name}/dependencies` | List a plugin's dependencies |
| POST | `/v1/plugins/{plugin_name}/dependencies/resolve` | Resolve dependencies |

### Tools (`/v1/tools`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/tools` | Discover all executable tools |
| GET | `/v1/tools/{tool_name}` | Tool details |
| POST | `/v1/tools/{tool_name}/execute` | Execute a tool (license-validated) |
| GET | `/v1/tools/plugins/{plugin_id}/tools` | Tools for one plugin |
| POST | `/v1/tools/validate` | Validate a license tier for a tool |

### Licensing (`/v1/licensing`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/licensing/plugins/{plugin_name}/license/tier` | Get a plugin's license tier |
| POST | `/v1/licensing/plugins/{plugin_name}/license/validate` | Validate license access |
| PATCH | `/v1/licensing/plugins/{plugin_name}/license` | Update license assignment |

### Ops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

---

## RAG Pipeline — `http://localhost:8004`

Chunking, embedding, retrieval, and generation. Documents are embedded into **Qdrant**;
embeddings and generation run through **Ollama**. The live query endpoint supports
**Standard** and **Conversational** RAG (set `conversation_id` for multi-turn history).
Standard, Conversational, **HyDE**, **Self-RAG**, **auto** (decision engine), and
**corrective** RAG are all selectable via the `method` field on
`POST /pipeline/{id}/query` (`standard`/`hyde`/`self_rag`/`auto`/`corrective`).
Orthogonal `rerank` and `compress` flags, and the `hybrid` (dense+BM25) and
`parent_context` (small-to-big) retrieval strategies, are also wired. `GET /capabilities`
reports what's active on the host. See [rag-methods.md](../rag-methods.md).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/initialize` | Initialize the Ollama client / warm the pipeline |
| GET | `/capabilities` | What's actually live on this host (rerank backend, hybrid/parent-context availability, etc.) — see [rag-methods.md](../rag-methods.md) |
| POST | `/knowledge-bases` | Create a knowledge base (`name` required, `description` optional; pick embedding + LLM model) |
| GET | `/knowledge-bases` | List knowledge bases |
| GET | `/knowledge-bases/{kb_id}` | Get a single knowledge base (404 if unknown) |
| DELETE | `/knowledge-bases/{kb_id}` | Delete a KB — drops its Qdrant collection + PostgreSQL row (404 if unknown) |
| POST | `/knowledge-bases/{kb_id}/upload` | Upload a document (PDF / TXT / MD) into a KB. Returns **503** if the embedding backend is unreachable — the doc is NOT indexed (no silent zero-vector) |
| POST | `/pipeline` | Create a RAG pipeline over one or more knowledge bases |
| DELETE | `/pipeline/{pipeline_id}` | Delete a pipeline (referenced KBs are left intact; 404 if unknown) |
| POST | `/pipeline/{pipeline_id}/query` | Query a pipeline (retrieval + generation) |
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

> The singular `/knowledge-base[...]` forms still work as deprecated, hidden aliases (#144).

```bash
# Create a knowledge base, then upload a document into it
KB=$(curl -s -X POST http://localhost:8004/knowledge-bases \
  -H 'Content-Type: application/json' \
  -d '{"name":"My Docs","description":"my documents"}' | jq -r '.id')

curl -X POST "http://localhost:8004/knowledge-bases/$KB/upload" -F "file=@doc.pdf"

# Query: create a pipeline over the KB, then query it
PIPE=$(curl -s -X POST http://localhost:8004/pipeline \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"my-pipe\",\"knowledge_base_ids\":[\"$KB\"]}" | jq -r '.pipeline_id')
curl -X POST "http://localhost:8004/pipeline/$PIPE/query" \
  -H 'Content-Type: application/json' -d '{"question":"What is in my docs?","top_k":3}'
```

---

## Model Management — `http://localhost:8005`

Model lifecycle over the Ollama runtime.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/models` | List local models (live from Ollama) |
| POST | `/models` | Pull a model — body `{"model_id": "..."}`. **201** on a fresh pull, **200** if it already exists |
| GET | `/models/{model_id}` | Model details, including a `capabilities` list (e.g. `tools`) sourced from Ollama's own model metadata — **not** a guarantee the model reliably uses tools when offered them, see [testing.md](../development/testing.md#tool-calling-model-reliability-328) (**404** if unknown) |
| DELETE | `/models/{model_id}` | Delete a local model (**404** if unknown) |
| POST | `/models/{model_id}/test` | Quick test-prompt inference — body `{"prompt": "..."}` |
| POST | `/models/{model_id}/constraints` | Set rate limits — **not implemented (501)** |
| GET | `/models/{model_id}/metrics` | Usage metrics — **not implemented (501)** |
| POST | `/models/fine-tune` | Fine-tune request — **not implemented (501)** |
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

---

## TTS / STT — `http://localhost:8006`

Speech synthesis and recognition. ~12 languages supported; **Turkish is the default**.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tts` | Text-to-speech — Piper offline (WAV) by default, gTTS fallback (MP3) for non-bundled languages |
| GET | `/tts/languages` | Supported TTS languages |
| POST | `/stt` | Speech-to-text via `speech_recognition` (Google backend) |
| GET | `/stt/languages` | Supported STT languages |
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

---

## Graph-RAG — `http://localhost:8008`

Entity extraction and knowledge-graph construction/retrieval, backed by **Neo4j**.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/extract` | spaCy NER entity extraction from text |
| POST | `/construct-graph` | Build a Neo4j knowledge graph from documents/entities |
| POST | `/retrieve` | Graph-based retrieval over entity relationships |
| POST | `/entity-context` | Retrieve context / neighbors around an entity |
| DELETE | `/graph/document/{document_id}` | Delete a document's graph — its relationships, Document node, and orphaned entities (shared entities kept). Idempotent: returns 200 with zero counts if the document is absent (graph-rag queries Neo4j directly, so there's no 404) |
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

---

## Error Handling

Errors follow the standard FastAPI shape:

```json
{ "detail": "Human-readable error message" }
```

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (missing/invalid JWT) |
| 404 | Not found |
| 422 | Validation error (FastAPI request-body validation) |
| 429 | Rate limited |
| 500 | Internal server error |

---

## Plugin System

Plugins are **manifest-based** and support no arbitrary code execution by design. New actions
must be implemented as fixed handlers in the codebase.

Lifecycle (as implemented in code):

```
register() → initialize() (READY) → health_check() (60s loop)
           → collect_data() (hourly or manual) → shutdown()
           + analyze()
```

Plugins advertise **AI tools** for Ollama function-calling. A module plugin declares an
`AI_TOOLS` class attribute (a manifest plugin uses its `ai_tools` key), each tool being:

```json
{ "name": "...", "description": "...", "parameters": { "type": "object", "properties": {} }, "action": "..." }
```

`action` maps to `POST /v1/plugins/<plugin>/actions/<action>`. `GET /v1/plugins/ai/tools`
aggregates these into OpenAI/Ollama tool defs; drive the end-to-end loop via
`POST /v1/ai/chat/completions` with `"minder_tools": true` (see the API Gateway section).

Plugins can write to any storage backend (postgres, qdrant, neo4j, minio, influxdb) and
publish async events through rabbitmq.

See the [Plugin Development Guide](../development/plugin-development.md) for details.

---

## Monitoring

FastAPI services expose Prometheus metrics on `/metrics`; Prometheus scrapes them and Grafana
visualizes the results. See the [Service Access Guide](../operations/service-access.md) for
the full observability port map.

---

## Changelog

### 2026-08-02
- Re-verified every route table against each service's live `/openapi.json` on a real
  deployment (hantal), per #256. Found and fixed real drift:
  - **Bundles section was stale**: documented `POST /v1/bundles/{name}/enable|disable`
    and `POST /v1/bundles/reconcile` as not-yet-implemented ("need the docker-socket-proxy,
    Phase 3"), but they've been live since #65 item 2 PR2 (`87e1845`). Added them.
  - Marketplace, Plugin State Manager, and Graph-RAG Ops sections were missing their
    `GET /metrics` row despite the endpoint being live (and despite the Monitoring
    section below claiming every service exposes one).
  - RAG Pipeline's route table was missing `GET /capabilities`, mentioned only in prose.
  - Fixed a Markdown bug: a blockquote note sat mid-table in the RAG Pipeline section,
    splitting one table into two at render time. Moved it after the table.

### 2026-07-10
- Corrected the service inventory to the 8 real core services (added graph-rag :8008; removed
  the non-existent model-fine-tuning :8007 and ai-service).
- Expanded every service section into a **complete, code-verified route table** with correct
  prefixes and HTTP methods (marketplace, plugin-state-manager, plugin-registry service
  discovery, and the gateway `/v1/ai` bridge were previously undocumented).
- Fixed the API Gateway auth paths (`/v1/auth/*`, not `/auth/*`) and removed the fictional
  `POST /8004/ingest` example (the real flow is `/knowledge-bases` → `/knowledge-bases/{id}/upload`).
- Documented interactive OpenAPI docs at `http://localhost:<port>/docs` for every service.
- Clarified that Authelia SSO is enabled and enforcing forward-auth on five Traefik routers,
  and that the API Gateway's own JWT auth remains the real authentication mechanism for the
  API itself.

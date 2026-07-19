# Minder Platform — API Reference

**Version:** 1.0.0
**Last Updated:** 2026-07-10
**Base URL (via API Gateway):** `http://localhost:8000`

---

## Overview

The Minder Platform exposes RESTful APIs from **8 core FastAPI microservices**. In front of
them sits **Traefik v3** as the reverse proxy (TLS termination, routing via Docker labels).

> **Development environment.** This is a development deployment on a Raspberry Pi 4.
> Production hardening is not yet fully applied. Authelia SSO is **defined but currently
> disabled** (its container is commented out in compose), so the Traefik forward-auth
> middleware is wired on five routers but **not enforced**. The API Gateway itself
> implements real JWT + bcrypt authentication and Redis-backed rate limiting.

### Core API services

| Service | Container | Port | Summary |
|---------|-----------|------|---------|
| API Gateway | `minder-api-gateway` | 8000 | JWT+bcrypt auth, Redis rate-limit, httpx proxy to registry/rag/models, OpenWebUI function bridge |
| Plugin Registry | `minder-plugin-registry` | 8001 | Manifest install, health loop, service discovery, AI-tool aggregation |
| Marketplace | `minder-marketplace` | 8002 | Discovery/search/featured, license tiers, dependency graph (Neo4j) |
| Plugin State Manager | `minder-plugin-state-manager` | 8003 | Plugin state, tool discovery, tool execution, licensing |
| RAG Pipeline | `minder-rag-pipeline` | 8004 | Knowledge bases, doc ingest, Qdrant vectors; Standard + Conversational RAG (HyDE/Self-RAG modules exist but are not wired — #45) |
| Model Management | `minder-model-management` | 8005 | Ollama list/pull/delete/test (some endpoints are placeholders) |
| TTS / STT | `minder-tts-stt` | 8006 | Text-to-speech (gTTS), speech-to-text (`speech_recognition`) |
| Graph-RAG | `minder-graph-rag` | 8008 | spaCy NER, Neo4j knowledge-graph construction and retrieval |

**Conventions used below**
- `ANY` = the route accepts `GET, POST, PUT, DELETE, PATCH`.
- `{path:path}` = a catch-all path segment (everything after the prefix is forwarded verbatim).
- Ports are the host-published ports; internally each service also sits behind Traefik.

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
| POST | `/v1/auth/register` | Create a user (bcrypt-hashed credentials) |
| POST | `/v1/auth/login` | Obtain a JWT access token (username/password → bearer token) |
| POST | `/v1/auth/refresh` | Refresh an access token |

### Proxy routes

Forwarded over the internal Docker network via httpx to the backing service.

| Method | Path | Target |
|--------|------|--------|
| GET | `/v1/plugins` | plugin-registry (list) |
| ANY | `/v1/plugins/{path:path}` | plugin-registry |
| ANY | `/v1/rag/{path:path}` | rag-pipeline |
| ANY | `/v1/models/{path:path}` | model-management |

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
  -d '{"username": "admin", "password": "..."}'

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
| GET | `/v1/plugins/{plugin_name}/analysis` | Plugin analysis output |
| GET | `/v1/plugins/ai/tools` | Aggregated AI-tool definitions across all plugins |

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/plugins/reload-webhook` | Re-register a plugin's webhook routes |
| POST | `/force-webhooks` | Force re-registration of all webhook routes |
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

### Ops

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health + plugin/service counts |
| GET | `/metrics` | Prometheus metrics |

> **Note:** No default plugins ship with the platform. The commonly referenced
> crypto/weather/network/news/tefas plugins are aspirational and **not implemented**.

---

## Marketplace — `http://localhost:8002`

Plugin/tool discovery, licensing, and dependency management. Catalog data lives in
PostgreSQL; the dependency/conflict graph is backed by **Neo4j**.

### Catalog (`/v1/marketplace`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/marketplace/plugins` | List catalog plugins (paginated / filterable) |
| GET | `/v1/marketplace/plugins/search` | Full-text search |
| GET | `/v1/marketplace/plugins/featured` | Featured plugins |
| GET | `/v1/marketplace/plugins/{plugin_id}` | Plugin details |
| POST | `/v1/marketplace/plugins` | Create a catalog entry (called by plugin-registry) |

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

---

## RAG Pipeline — `http://localhost:8004`

Chunking, embedding, retrieval, and generation. Documents are embedded into **Qdrant**;
embeddings and generation run through **Ollama**. The live query endpoint supports
**Standard** and **Conversational** RAG (set `conversation_id` for multi-turn history).
HyDE, Self-RAG, and a decision engine exist as modules but are **not wired into the live
endpoint** ([#45](https://github.com/wish-maker/minder/issues/45)).

| Method | Path | Description |
|--------|------|-------------|
| POST | `/initialize` | Initialize the Ollama client / warm the pipeline |
| POST | `/knowledge-base` | Create a knowledge base (`name` + `description` required; pick embedding + LLM model) |
| GET | `/knowledge-bases` | List knowledge bases |
| GET | `/knowledge-base/{kb_id}` | Get a single knowledge base (404 if unknown) |
| DELETE | `/knowledge-base/{kb_id}` | Delete a KB — drops its Qdrant collection + PostgreSQL row (404 if unknown) |
| POST | `/knowledge-base/{kb_id}/upload` | Upload a document (PDF / TXT / MD) into a KB. Returns **503** if the embedding backend is unreachable — the doc is NOT indexed (no silent zero-vector) |
| POST | `/pipeline` | Create a RAG pipeline over one or more knowledge bases |
| DELETE | `/pipeline/{pipeline_id}` | Delete a pipeline (referenced KBs are left intact; 404 if unknown) |
| POST | `/pipeline/{pipeline_id}/query` | Query a pipeline (retrieval + generation) |
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

```bash
# Create a knowledge base, then upload a document into it
KB=$(curl -s -X POST http://localhost:8004/knowledge-base \
  -H 'Content-Type: application/json' \
  -d '{"name":"My Docs","description":"my documents"}' | jq -r '.id')

curl -X POST "http://localhost:8004/knowledge-base/$KB/upload" -F "file=@doc.pdf"

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
| POST | `/models` | Register / pull a model from the Ollama library |
| GET | `/models/{model_id}` | Model details |
| DELETE | `/models/{model_id}` | Delete a local model |
| POST | `/models/{model_id}/test` | Quick test-prompt inference |
| POST | `/models/{model_id}/constraints` | Set rate limits — **placeholder, not implemented** |
| GET | `/models/{model_id}/metrics` | Usage metrics — **placeholder, returns zeros** |
| POST | `/models/fine-tune` | Fine-tune request — **delegated out; not performed here** |
| GET | `/health` | Service health |
| GET | `/metrics` | Prometheus metrics |

---

## TTS / STT — `http://localhost:8006`

Speech synthesis and recognition. ~12 languages supported; **Turkish is the default**.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tts` | Text-to-speech via gTTS (returns MP3) |
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

### 2026-07-10
- Corrected the service inventory to the 8 real core services (added graph-rag :8008; removed
  the non-existent model-fine-tuning :8007 and ai-service).
- Expanded every service section into a **complete, code-verified route table** with correct
  prefixes and HTTP methods (marketplace, plugin-state-manager, plugin-registry service
  discovery, and the gateway `/v1/ai` bridge were previously undocumented).
- Fixed the API Gateway auth paths (`/v1/auth/*`, not `/auth/*`) and removed the fictional
  `POST /8004/ingest` example (the real flow is `/knowledge-base` → `/knowledge-base/{id}/upload`).
- Documented interactive OpenAPI docs at `http://localhost:<port>/docs` for every service.
- Clarified that Authelia SSO is currently disabled and the API Gateway's own JWT auth is the
  real authentication mechanism; forward-auth is wired on five Traefik routers but not enforced.

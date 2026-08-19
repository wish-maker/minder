# Minder Platform - API Documentation

API documentation for the Minder platform's core services.

All core services are FastAPI applications. Each one serves interactive,
auto-generated API docs at `/docs` (Swagger UI) and `/redoc` (ReDoc), plus a
machine-readable schema at `/openapi.json`. When in doubt, that live schema is
the authoritative reference — this page summarises the most useful endpoints.

> **Note on access.** In a normal deployment the only host-exposed HTTP surface is
> Traefik (ports 80/443). The `localhost:<port>` URLs below are the *internal*
> container ports; they are directly reachable when you run the stack locally on
> the same host (or after publishing a port for debugging), but are not exposed
> to the outside world by default.

## Core Services (8)

| Service | Container | Port | Notes |
|---|---|---|---|
| API Gateway | `minder-api-gateway` | 8000 | JWT auth, rate limiting, reverse proxy to other services |
| Plugin Registry | `minder-plugin-registry` | 8001 | Plugin registration, discovery, lifecycle |
| Marketplace | `minder-marketplace` | 8002 | Plugin discovery/search, licensing, AI-tool catalog |
| Plugin State Manager | `minder-plugin-state-manager` | 8003 | Plugin state, AI-tool discovery/execution |
| RAG Pipeline | `minder-rag-pipeline` | 8004 | Knowledge bases, document ingestion, RAG query |
| Model Management | `minder-model-management` | 8005 | Ollama model list/pull/delete/test |
| TTS/STT | `minder-tts-stt` | 8006 | Text-to-speech / speech-to-text |
| Graph-RAG | `minder-graph-rag` | 8008 | Entity extraction, Neo4j knowledge graph |

Every service exposes `GET /health` (and most expose `GET /metrics` for
Prometheus). The examples below are representative; consult each service's
`/docs` for the complete, current contract.

---

### 1. API Gateway (`http://localhost:8000`)

Central entry point. Handles JWT authentication (bcrypt password hashing),
Redis-backed rate limiting, and proxies requests to the plugin registry, RAG
pipeline, and model-management services via `httpx`.

#### Health
```http
GET /health
```

#### Authentication

```http
POST /v1/auth/register
Content-Type: application/json

{ "username": "alice", "email": "alice@example.com", "password": "..." }
```

```http
POST /v1/auth/login
Content-Type: application/json

{ "username": "alice", "password": "..." }
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": { "id": 1, "username": "alice", "email": "alice@example.com", "role": "user" }
}
```

```http
POST /v1/auth/refresh
Authorization: Bearer <access_token>
```
Refresh takes **no body** — the current token is read from the `Authorization` header.

#### Proxied routes

The gateway forwards these prefixes to the corresponding backend service:

- `/v1/plugins/*`     → plugin registry
- `/v1/bundles/*`     → plugin registry (see [Bundles](#bundles) below)
- `/v1/containers/*`  → plugin registry (container log streaming; JWT-gated, see below)
- `/v1/tools/*`       → plugin state manager
- `/v1/rag/*`         → RAG pipeline
- `/v1/models/*`      → model management
- `/v1/marketplace/*` → marketplace
- `/v1/graph/*`       → marketplace (plugin dependency graph — NOT graph-rag)
- `/v1/graph-rag/*`   → graph-rag (its own routes are unprefixed, e.g. `/v1/graph/stats`
  becomes `/v1/graph-rag/graph/stats` through the gateway — the `graph-rag/` segment
  exists specifically so this doesn't collide with the line above)
- `/v1/tts/*`, `/v1/stt/*` → TTS/STT

#### Status (`/v1/status`)

Native to the gateway, not a proxy — fans out to every core service's own
`/health` over the internal Docker network and returns a combined view:

```http
GET /v1/status
```
```json
{
  "services": [
    { "name": "api-gateway", "reachable": true, "status": "healthy", "version": "1.0.0" }
  ]
}
```
> `version` is a hardcoded string each service's own code carries, not derived
> from the deployed image tag — don't treat it as a deployment-tracking signal.

#### Container logs (`/v1/containers/{name}/logs`)

```http
GET /v1/containers/{name}/logs?tail=200
Authorization: Bearer <token>
```
JWT-gated (log output can contain stack traces or accidentally-logged
secrets); `{name}` is validated against a fixed allowlist of known service
names, not an arbitrary string.

#### AI / OpenWebUI integration (`/v1/ai`)
```http
GET  /v1/ai/functions/definitions        # aggregated plugin AI-tool (function) defs
POST /v1/ai/functions/{function_name}     # execute a named tool (OpenAI function-result format)
POST /v1/ai/chat/completions              # chat via Ollama; plugin function-calling is opt-in via {"minder_tools": true}
```

#### Observability
```http
GET /metrics
```

---

### 2. Plugin Registry (`http://localhost:8001`)

Plugin registration, discovery, and lifecycle management. Plugins are
**manifest-based** — there is no arbitrary code execution by design.

#### Health
```http
GET /health
```

#### List plugins
```http
GET /v1/plugins
```

#### Enable / disable a plugin
```http
POST /v1/plugins/{plugin_name}/enable
Authorization: Bearer <token>
```

> Six first-party module plugins ship in `src/plugins/` and are loaded from disk by
> the registry on startup (`crypto`, `weather`, `news`, `tefas`, `network`, `telegraf`)
> — listed at `GET /v1/plugins`. (The separate plugin-state-manager bootstrap
> `default_plugins.yml` stays an empty stub.)

#### Bundles

Capability bundles group related services (`core`, `inference`, `rag`, `chat`,
`monitoring`, `voice`, `graph-rag`) so they can be enabled/disabled together
instead of one service at a time. Reads are open; all three write endpoints
below require an **admin**-role token, not just any authenticated user.

```http
GET /v1/bundles
```
```json
{
  "bundles": [
    { "name": "monitoring", "core": false, "enabled": false,
      "claims": ["grafana", "prometheus", "..."],
      "services": [{ "name": "grafana", "active": false, "claimants": "", "image": "grafana/grafana:..." }] }
  ],
  "orphaned": ["grafana", "prometheus"],
  "count": 7
}
```
> `orphaned` lists services claimed by NO currently-enabled bundle — a
> declarative computation, not "currently running but shouldn't be". A
> service can show up here even while its container happens to still be
> running (e.g. right after a host restart brought it back via Docker's own
> restart policy, bypassing bundle state) — `reconcile` below is what
> actually converges live containers to match.

```http
POST /v1/bundles/{name}/enable
Authorization: Bearer <token>
```
```http
POST /v1/bundles/{name}/disable
Authorization: Bearer <token>
```
> The `core` bundle can never be disabled (409) — it holds the services
> everything else depends on (Postgres, Redis, Traefik, the gateway itself).
> `disable` always stops the services being orphaned by this specific call
> (no query param — that's a CLI-only concept, `bundle disable --stop-orphans`
> in `scripts/setup`, unrelated to this endpoint).

```http
POST /v1/bundles/reconcile
Authorization: Bearer <token>
```
Starts anything an enabled bundle claims but isn't running yet, and stops
every currently-running service no enabled bundle claims — always both
directions, admin-only, no query params.

---

### 3. Marketplace (`http://localhost:8002`)

Plugin discovery, search, and licensing (community / pro / enterprise tiers).
Maintains an AI-tool catalog and a plugin dependency graph in Neo4j.

#### Health
```http
GET /health
```

#### List / search plugins
```http
GET /v1/marketplace/plugins?limit=10&offset=0
```

See `/docs` for the full set of discovery, search, featured, and dependency
endpoints.

---

### 4. Plugin State Manager (`http://localhost:8003`)

Tracks plugin state and handles AI-tool discovery and execution (with license
validation).

#### Health
```http
GET /health
```

---

### 5. RAG Pipeline (`http://localhost:8004`)

Retrieval-augmented generation. Manages knowledge bases, ingests documents
(PDF/TXT/MD via `pypdf` + a LangChain splitter), stores vectors in Qdrant, and
uses Ollama for embeddings and generation. The live query endpoint supports Standard,
Conversational (`conversation_id`), **HyDE**, **Self-RAG**, **auto** (decision engine),
and **corrective** RAG via the `method` field, plus orthogonal `rerank`/`compress`
flags and `hybrid`/`parent_context` retrieval strategies. `GET /capabilities` reports
what's live. See [rag-methods.md](../rag-methods.md).

#### Health
```http
GET /health
```

#### Knowledge bases
```http
GET    /knowledge-bases
GET    /knowledge-bases/{id}
POST   /knowledge-bases
DELETE /knowledge-bases/{id}
```
> Singular `/knowledge-base[...]` forms still work as deprecated aliases (#144).

#### Upload a document into a knowledge base
```http
POST /knowledge-bases/{id}/upload
Content-Type: multipart/form-data

file: <document_file>
```
> Returns 503 if the embedding backend (Ollama) is unreachable — the document is
> not indexed rather than silently stored with a zero-vector.

#### Pipelines and query
```http
POST   /pipeline
DELETE /pipeline/{id}
POST   /pipeline/{id}/query
Content-Type: application/json

{ "question": "What is machine learning?", "top_k": 3 }
```

> The exact request/response shapes are defined by the service's Pydantic models —
> see `http://localhost:8004/docs`.

---

### 6. Model Management (`http://localhost:8005`)

Manages Ollama models. Real operations: list, pull, delete, and test models.
(`/models/{id}/constraints` and `/models/{id}/metrics` are currently
placeholders.)

#### Health
```http
GET /health
```

#### List models
```http
GET /models
```

---

### 7. TTS/STT (`http://localhost:8006`)

Text-to-speech via **Piper** (offline, on-device; returns WAV) with a **gTTS** fallback
(online, returns MP3) for languages without a bundled Piper voice; speech-to-text via
`speech_recognition` (Google backend). Around 12 languages supported; Turkish is the
default and ships a bundled Piper voice.

#### Text-to-Speech
```http
POST /tts
Content-Type: application/json

{ "text": "Merhaba dünya", "language": "tr" }
```
**Response:** audio — `audio/wav` (Piper) or `audio/mpeg` (gTTS fallback)

#### Speech-to-Text
```http
POST /stt
Content-Type: multipart/form-data

file: <audio_file>
language: tr-TR
```

---

### 8. Graph-RAG (`http://localhost:8008`)

Entity extraction (spaCy NER), Neo4j knowledge-graph construction, and
graph-based retrieval.

#### Health
```http
GET /health
```

#### Endpoints
```http
POST /v1/extract           # extract entities from text
POST /v1/construct-graph   # build/update the knowledge graph
POST /v1/retrieve          # graph-based retrieval
POST /v1/entity-context    # context for a given entity
GET  /v1/graph/stats       # node/relationship/entity-type counts
GET  /v1/graph/documents   # list Document nodes in the graph
```
> Unversioned aliases (`/extract`, `/construct-graph`, etc., no `/v1`) still work
> for backward compatibility. Through the gateway, every one of these is reached
> at `/v1/graph-rag/<path>` (e.g. `/v1/graph-rag/graph/stats`) — see the
> Proxied routes note in the API Gateway section above for why.

---

## Authentication

Authentication is handled by the API Gateway using JWT (HS256) with bcrypt
password hashing. Obtain a token, then pass it as a bearer token.

```http
POST /v1/auth/login
Content-Type: application/json

{ "username": "alice", "password": "..." }
```

```http
GET /v1/plugins
Authorization: Bearer <access_token>
```

See [authentication.md](./authentication.md) for details.

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 404 | Not Found |
| 429 | Rate Limited |
| 500 | Internal Server Error |
| 503 | Service Unavailable |

---

## Rate Limiting

The API Gateway applies Redis-backed rate limiting on a rolling 60-second window.
The limiter is **fail-open** — if Redis is unavailable, requests are allowed
through rather than blocked.

---

## Testing APIs

### cURL
```bash
# Health check
curl http://localhost:8000/health

# Register / login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "..."}'

# Authenticated call
curl http://localhost:8000/v1/plugins \
  -H "Authorization: Bearer <token>"
```

### Python
```python
import httpx

r = httpx.post(
    "http://localhost:8000/v1/auth/login",
    json={"username": "alice", "password": "..."},
)
token = r.json()["access_token"]

r = httpx.get(
    "http://localhost:8000/v1/plugins",
    headers={"Authorization": f"Bearer {token}"},
)
print(r.json())
```

---

## More Information

- **[Complete API Reference](../api/reference.md)** — every route, per service (code-verified)
- Interactive docs per service: `http://localhost:<port>/docs`
- [Authentication guide](./authentication.md)
- [Architecture documentation](../architecture/)

---

**Last Updated:** 2026-07-10

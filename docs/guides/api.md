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

{ "username": "alice", "password": "..." }
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
  "token_type": "bearer"
}
```

```http
POST /v1/auth/refresh
Content-Type: application/json

{ "refresh_token": "..." }
```

#### Proxied routes

The gateway forwards these prefixes to the corresponding backend service:

- `/v1/plugins/*`  → plugin registry
- `/v1/rag/*`      → RAG pipeline
- `/v1/models/*`   → model management

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

> No default plugins ship with the platform today. The registry manages whatever
> plugins are installed; the shipped configuration is an intentional empty stub.

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
GET /plugins?page=1&page_size=10
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
uses Ollama for embeddings and generation. The live query endpoint does Standard and
Conversational RAG (`conversation_id`). HyDE, Self-RAG, and a decision engine exist as
modules but are **not wired into the live endpoint**
([#45](https://github.com/wish-maker/minder/issues/45)).

#### Health
```http
GET /health
```

#### Knowledge bases
```http
GET    /knowledge-bases
GET    /knowledge-base/{id}
POST   /knowledge-base
DELETE /knowledge-base/{id}
```

#### Upload a document into a knowledge base
```http
POST /knowledge-base/{id}/upload
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

Text-to-speech via gTTS (returns MP3) and speech-to-text via
`speech_recognition` (Google backend). Around 12 languages supported; Turkish is
the default.

#### Text-to-Speech
```http
POST /tts
Content-Type: application/json

{ "text": "Merhaba dünya", "language": "tr" }
```
**Response:** audio (`audio/mpeg`)

#### Speech-to-Text
```http
POST /stt
Content-Type: multipart/form-data

audio: <audio_file>
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
POST /extract           # extract entities from text
POST /construct-graph   # build/update the knowledge graph
POST /retrieve          # graph-based retrieval
POST /entity-context    # context for a given entity
```

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

# Microservices Architecture

Detailed microservices architecture for the Minder Platform.

## Current Service Status

**Total Containers:** 35 defined (Authelia + docker-socket-proxy included, both enabled); two
(`ollama-router`, `tts-stt-router`) are failover-mode sidecars inactive by default, so 33 run
in the common case
**With Health Checks:** 30
**No-Healthcheck (by design):** 3 (otel-collector, redis-exporter, rabbitmq-exporter — their images lack the tooling for a healthcheck)
**No-Healthcheck (not configured):** 2 (authelia, docker-socket-proxy)
**Unhealthy:** 0
**AI Runtime:** Ollama with local LLM support (profile-gated)

**Core API Services (8):**
- api-gateway, plugin-registry, marketplace, plugin-state-manager, rag-pipeline, model-management, tts-stt, graph-rag

**Deploy Status:** Clean install proven from zero (`docker compose down -v` → `bash setup.sh start`)

## Overview

Minder is a local AI orchestration platform with eight FastAPI core services running in Docker,
backed by internal data stores and a monitoring stack. All services are Python 3.11/3.12
(`python:3.12-slim`, except graph-rag on `python:3.11-slim`).

## Service Communication

### Synchronous Communication
- **REST APIs** — HTTP/JSON between services
- **API Gateway** — single entry point for external requests, proxies via httpx
- **Service Discovery** — Docker DNS + a registry-maintained record in Redis

### Asynchronous Communication
- **RabbitMQ** — async message bus (available for plugin/pipeline events)
- **Redis** — used for caching, rate limiting, and service-discovery records

## Service Categories

### Edge / Security

#### Traefik (Reverse Proxy)
**Purpose**: Single edge entry point, TLS termination, routing

**Responsibilities**: request routing, TLS, security headers, `forwardauth` integration

**Version**: `traefik:v3.7.10`

**Configuration**: `docker/services/traefik/`

**Host Ports**: 80, 443, 8081 (dashboard, IP whitelist)

#### Authelia (SSO & 2FA) — ENABLED
**Status**: Running (`minder-authelia`) in `docker-compose.yml`, providing SSO/2FA. A Traefik
`forwardauth` middleware references it on five routers (minio, api-gateway, grafana, openwebui,
jaeger), and that auth **is enforced** — unauthenticated requests get a 302 redirect to the
Authelia portal. Full browser SSO still needs real DNS + TLS on the deploy.

### Data Stores (internal-only — not host-exposed)

#### PostgreSQL (`postgres:18.4-trixie`)
**Purpose**: Primary relational database (internal port 5432)

**Databases**:
- `minder` — main application database
- `minder_marketplace` — marketplace data
- `tefas_db`, `weather_db`, `news_db`, `crypto_db` — external data-source databases
- `minder_schemaregistry` — isolated database backing the Apicurio schema registry

#### Redis (`redis:8.8.0-alpine`)
**Purpose**: Caching, sessions, rate limiting, service-discovery records (internal port 6379)

#### Qdrant (`qdrant/qdrant:v1.19`)
**Purpose**: Vector database for RAG embeddings and semantic search (internal port 6333)

#### Neo4j (`neo4j:2026.06.0-community`)
**Purpose**: Graph database (internal 7687/7474). Used by the marketplace (plugin dependency
graph) and graph-rag (knowledge graph). The browser is routed via Traefik with an IP whitelist.

#### MinIO (`minio/minio:RELEASE.2025-09-07T16-13-09Z`)
**Purpose**: S3-compatible object store (internal 9000/9001). Buckets: `rag-documents`,
`tts-artifacts`, `fine-tuning-datasets`, `model-checkpoints`, `plugin-packages`,
`backup-archives`. Console routed via Traefik.

#### RabbitMQ (`rabbitmq:4.3.2-management`)
**Purpose**: Async message bus (internal 5672/15672). Management UI routed via Traefik with an
IP whitelist.

#### Schema Registry (`apicurio/apicurio-registry-sql:2.6.13.Final`)
**Purpose**: Schema registry (internal 8080), backed by the isolated `minder_schemaregistry`
PostgreSQL database.

### Inference

#### Ollama (`ollama/ollama:0.32.1`)
**Purpose**: Local LLM inference (internal port 11434). Profile-gated `internal-ollama`: runs
only when `OLLAMA_BASE_URL` is empty (local mode); when set, an external/native host is used and
the container stays inactive. Models auto-pulled via `OLLAMA_PULL_MODELS` into the
`/root/.ollama/models` volume.

#### Ollama Router (`nginx:1.27-alpine`, mode-gated)
**Purpose**: Failover-mode-only reverse proxy (`minder-ollama-router`, internal port 11434,
profile `ollama-router`) sitting in front of an external **primary** Ollama with the internal
`minder-ollama` container as automatic backup. All services point `OLLAMA_BASE_URL` at it, so
failover is transparent — no per-service code. Only present when `ollama-mode failover` is set
(via `OLLAMA_FAILOVER_PRIMARY`); absent in plain internal/external mode. See
[Ollama modes](../getting-started/ai-setup.md#ollama-modes-internal-external-failover).

### Core APIs

All core APIs expose a `/health` endpoint. Route prefixes vary per service (e.g.
`/v1/plugins`, `/v1/marketplace`, bare `/models`, bare `/tts`) — see
[`docs/api/reference.md`](../api/reference.md) for the code-verified route tables.

#### API Gateway (Port 8000)
**Purpose**: Single entry point for all API requests

**Responsibilities**: routing, JWT authentication (bcrypt), Redis-backed rate limiting
(fail-open), request validation, httpx proxy to downstream services

#### Plugin Registry (Port 8001)
**Purpose**: Plugin discovery and lifecycle management (manifest-based, no code execution)

**Endpoints (representative)**:
- `POST /v1/plugins/install` — install/register a plugin
- `GET /v1/plugins` — list plugins (legacy alias `GET /plugins`)
- `GET /v1/plugins/{name}` — plugin details
- `POST /v1/plugins/{name}/enable` / `.../disable` — toggle a plugin
- `GET /v1/plugins/{name}/health` — plugin health
- `GET`/`PUT /v1/plugins/{name}/config` — central plugin config (PUT is JWT-gated)

#### Marketplace (Port 8002)
**Purpose**: Plugin/tool discovery and licensing

**Endpoints (representative)**:
- `GET /v1/marketplace/plugins` — discovery / search / featured
- `GET /v1/marketplace/licenses` — license tiers (community / pro / enterprise)
- `GET /v1/graph/...` — dependency graph (maintained in Neo4j)

#### Plugin State Manager (Port 8003)
**Purpose**: Plugin state and AI-tool execution

**Endpoints (representative)**:
- `GET /v1/plugins/state` · `GET /v1/plugins/state/{plugin_name}` — plugin state
- `POST /v1/plugins/state/{plugin_name}/enable` / `.../disable` — state toggles
- `/v1/tools/...` — tool discovery and execution (with license validation)

#### RAG Pipeline (Port 8004)
**Purpose**: Retrieval-augmented generation

**Endpoints (representative)**:
- `POST /knowledge-bases` — create a knowledge base (name required, description optional)
- `GET /knowledge-bases` · `GET /knowledge-bases/{kb_id}` — list / get one
- `DELETE /knowledge-bases/{kb_id}` — delete a KB (Qdrant collection + PostgreSQL row)
- `POST /knowledge-bases/{kb_id}/upload` — ingest a document (PDF/TXT/MD via pypdf + LangChain splitter; 503 if the embedding backend is unreachable — no silent zero-vector)
- The singular `/knowledge-base[...]` paths remain as deprecated, hidden aliases (#144)
- `POST /pipeline` · `DELETE /pipeline/{pipeline_id}` — create / delete a RAG pipeline over one or more KBs
- `POST /pipeline/{pipeline_id}/query` — query (retrieval + generation)

**Pipeline**: query → embed (Ollama) → search (Qdrant) → retrieve context → generate (Ollama LLM).
The live query endpoint selects the RAG method via the `method` field: `standard`, `hyde` (HyDE), `self_rag` (Self-RAG), `auto` (decision engine), or `corrective` (CRAG) — plus Conversational via `conversation_id`. Orthogonal `rerank`/`compress` flags and the `hybrid` (dense+BM25) / `parent_context` (small-to-big) retrieval strategies are also wired (#45). `GET /capabilities` reports what's active.

#### Model Management (Port 8005)
**Purpose**: Model registry and lifecycle over Ollama

**Endpoints (representative)**:
- `GET /models` — list models
- `POST /models` — register a model
- `GET`/`DELETE /models/{model_id}`, `POST /models/{model_id}/test` — get / delete / test
- model list / pull / delete / test are real; `/models/{model_id}/constraints` and
  `/models/{model_id}/metrics` are placeholders

#### TTS/STT Service (Port 8006)
**Purpose**: Text-to-speech and speech-to-text

**Endpoints (representative)**:
- `POST /tts` — text to speech (Piper offline WAV default, gTTS MP3 fallback)
- `POST /stt` — speech to text (speech_recognition, Google)
- `GET /tts/languages` · `GET /stt/languages` — supported language lists

**Languages**: ~12, Turkish default

#### Graph RAG (Port 8008)
**Purpose**: Entity extraction and Neo4j knowledge-graph construction/retrieval

**Endpoints**:
- `POST /extract` — spaCy NER entity extraction
- `POST /construct-graph` — build the knowledge graph in Neo4j
- `POST /retrieve` — graph retrieval
- `POST /entity-context` — entity context lookup
- `DELETE /graph/document/{document_id}` — delete a document's graph (relationships + orphaned entities)

### Web UI

#### OpenWebUI (internal port 8080, reached via Traefik)
**Purpose**: Web-based chat interface (Ollama frontend)

**Features**: chat, RAG integration, tool calling, model selection. Depends on postgres,
rag-pipeline, and optionally ollama. This is the only user-facing web app; there is no custom
frontend framework.

### Monitoring

#### Prometheus (`prom/prometheus:v3.13.1`, host 9090)
Metrics storage and querying. Scrapes core services and the exporters below.

#### Grafana (`grafana/grafana:13.1`, host 3000)
Dashboards. Traefik route has an Authelia `forwardauth` middleware, and since Authelia is
enabled that auth is enforced.

#### InfluxDB (`influxdb:3.10.3-core`, host 8086)
Time-series storage (fed by Telegraf).

#### Telegraf (`telegraf:1.39.1`, no host port)
Metrics collection agent.

#### Alertmanager (`prom/alertmanager:v0.33.1`, host 9093)
Alert routing.

#### Jaeger (`jaegertracing/all-in-one:1.76.0`, host 16686)
Distributed tracing UI plus OTLP/thrift/zipkin ingest ports.

#### OpenTelemetry Collector (`otel/opentelemetry-collector:0.156.0`)
OTLP gRPC 14317 / HTTP 14318, metrics 18888. No healthcheck (image lacks the tooling).

#### Exporters (internal, scraped by Prometheus)
postgres-exporter (v0.20.1), redis-exporter (v1.87.0, no healthcheck), rabbitmq-exporter
(v1.0.0-RC9, healthcheck disabled), node-exporter (v1.12.1), cadvisor (v0.55.1),
blackbox-exporter (v0.28.0).

## Service Dependencies

```
traefik
  ├── api-gateway
  │   └── redis (rate limiting)
  ├── plugin-registry
  │   ├── postgres
  │   └── redis
  ├── marketplace
  │   ├── postgres
  │   ├── neo4j (dependency graph)
  │   └── plugin-registry
  ├── plugin-state-manager
  │   ├── postgres
  │   └── redis
  ├── rag-pipeline
  │   ├── qdrant
  │   ├── ollama (optional; external if OLLAMA_BASE_URL set)
  │   └── postgres
  ├── model-management
  │   ├── postgres
  │   └── ollama
  ├── tts-stt
  ├── graph-rag
  │   └── neo4j
  ├── openwebui
  │   ├── postgres
  │   ├── rag-pipeline
  │   └── ollama (optional)
  └── monitoring (prometheus, grafana, influxdb, jaeger, alertmanager, exporters)
```

(Authelia sits in front of five routers: minio, api-gateway, grafana, openwebui, jaeger.)

## Data Flow

### API Request Flow
```
Client → Traefik → API Gateway → Service → Database/Cache
```
(Authelia forwardauth is wired and enforced on five routers.)

### RAG Query Flow
```
Client → API Gateway → RAG Pipeline → Qdrant (search) + Ollama (generate) → Response
```

### Plugin Execution Flow
```
Client → API Gateway → State Manager → fixed manifest handler → State Update → Response
```

## Scaling Strategies

### Horizontal Scaling
Stateless services (API Gateway, Plugin Registry, Marketplace, State Manager) can be scaled:
```bash
docker compose --file docker/docker-compose.yml up -d --scale api-gateway=3
```

### Vertical Scaling
Stateful services (PostgreSQL, Redis, Qdrant, Neo4j) scale vertically by adjusting resource
limits in `docker-compose.yml`.

## Service Configuration

### Environment Variables
- Edited in root `./.env` (single source of truth)
- `setup.sh` mirrors it to `docker/.env` (the file Compose reads) — auto-generated, do not edit
- Template in root `./.env.example`
- Never commit `.env`

### Health Checks
30/35 services define an active container healthcheck (`/health` for the core APIs). Five lack
one: `otel-collector`, `rabbitmq-exporter`, and `redis-exporter` because their images cannot run
one; `authelia` and `docker-socket-proxy` simply don't have one configured.

### Restart Policies
Services use `restart: on-failure`.

## Security

### Network Segmentation
- **Edge**: only Traefik and the monitoring services expose host ports.
- **Storage**: PostgreSQL, Redis, Qdrant, Neo4j, MinIO, RabbitMQ, and the schema registry are
  internal-only; management UIs are Traefik-routed with IP whitelists.
- **Networks**: `minder-network` (all services) and `minder-monitoring` (attachable, prepared).

### Authentication
- JWT for API authentication (bcrypt password hashing)
- Authelia SSO is enabled, enforcing on five Traefik routers
- **RBAC is not implemented**

## Monitoring

### Metrics Collection
- Prometheus: service + exporter metrics
- Telegraf: system/agent metrics → InfluxDB

### Logging
- Structured JSON logs per service (no centralized log store in this repo)

### Alerting
- Alertmanager routing (integrations to be configured)

## Future Improvements

Forward work is tracked as GitHub issues in `wish-maker/minder` (see `roadmap.md`). Themes under
consideration include the ARM/Pi deployment and completing Authelia's browser-SSO rollout (real
DNS + TLS). (Offline TTS via Piper and the stricter mypy CI gate are already done.)

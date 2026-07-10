# Microservices Architecture

Detailed microservices architecture for the Minder Platform.

## Current Service Status

**Total Containers:** 31 (Authelia is defined but disabled, and not counted)
**With Health Checks:** 28
**No-Healthcheck (by design):** 3 (otel-collector, redis-exporter, rabbitmq-exporter — their images lack the tooling for a healthcheck)
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

**Version**: `traefik:v3.7.7`

**Configuration**: `docker/services/traefik/`

**Host Ports**: 80, 443, 8081 (dashboard, IP whitelist)

#### Authelia (SSO & 2FA) — DISABLED
**Status**: Commented out in `docker-compose.yml`. Would provide SSO/2FA, but is currently
disabled due to a crash loop (missing database + NTP sync). A Traefik `forwardauth` middleware
references it on five routers (minio, api-gateway, grafana, openwebui, jaeger), but with the
container down, that auth is **not enforced**.
Keep-vs-drop is an open decision.

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

#### Qdrant (`qdrant/qdrant:v1.18.2`)
**Purpose**: Vector database for RAG embeddings and semantic search (internal port 6333)

#### Neo4j (`neo4j:2026.05.0-community`)
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

#### Ollama (`ollama/ollama:0.31.2`)
**Purpose**: Local LLM inference (internal port 11434). Profile-gated `internal-ollama`: runs
only when `OLLAMA_BASE_URL` is empty (local mode); when set, an external/native host is used and
the container stays inactive. Models auto-pulled via `OLLAMA_PULL_MODELS` into the
`/root/.ollama/models` volume.

### Core APIs

All core APIs expose `/api/v1/*` routes and a `/health` endpoint.

#### API Gateway (Port 8000)
**Purpose**: Single entry point for all API requests

**Responsibilities**: routing, JWT authentication (bcrypt), Redis-backed rate limiting
(fail-open), request validation, httpx proxy to downstream services

#### Plugin Registry (Port 8001)
**Purpose**: Plugin discovery and lifecycle management (manifest-based, no code execution)

**Endpoints (representative)**:
- `POST /api/v1/plugins/register` — register a plugin manifest
- `GET /api/v1/plugins` — list plugins
- `GET /api/v1/plugins/{id}` — plugin details
- `POST /api/v1/plugins/{name}/enable` / `.../disable` — toggle a plugin
- `GET /api/v1/plugins/{name}/health` — plugin health

#### Marketplace (Port 8002)
**Purpose**: Plugin/tool discovery and licensing

**Endpoints (representative)**:
- `GET /api/v1/marketplace/plugins` — discovery / search / featured
- `GET /api/v1/marketplace/licenses` — license tiers (community / pro / enterprise)
- Dependency graph is maintained in Neo4j

#### Plugin State Manager (Port 8003)
**Purpose**: Plugin state and AI-tool execution

**Endpoints (representative)**:
- `GET /api/v1/state/plugins/{id}` — plugin state
- tool discovery and tool execution (with license validation)

#### RAG Pipeline (Port 8004)
**Purpose**: Retrieval-augmented generation

**Endpoints (representative)**:
- `POST /v1/knowledge-base` — create a knowledge base
- `POST /v1/documents` — ingest a document (PDF/TXT/MD via pypdf + LangChain splitter)
- `GET /v1/documents/search` — semantic search

**Pipeline**: query → embed (Ollama) → search (Qdrant) → retrieve context → generate (Ollama LLM).
Includes HyDE, Self-RAG, a decision engine, and conversational RAG.

#### Model Management (Port 8005)
**Purpose**: Model registry and lifecycle over Ollama

**Endpoints (representative)**:
- `GET /v1/models` — list models
- `POST /v1/models` — register a model
- model list / pull / delete / test are real; `/models/{id}/constraints` and
  `/models/{id}/metrics` are placeholders

#### TTS/STT Service (Port 8006)
**Purpose**: Text-to-speech and speech-to-text

**Endpoints (representative)**:
- `POST /v1/tts` — text to speech (gTTS, MP3)
- `POST /v1/stt` — speech to text (speech_recognition, Google)

**Languages**: ~12, Turkish default

#### Graph RAG (Port 8008)
**Purpose**: Entity extraction and Neo4j knowledge-graph construction/retrieval

**Endpoints**:
- `POST /extract` — spaCy NER entity extraction
- `POST /construct-graph` — build the knowledge graph in Neo4j
- `POST /retrieve` — graph retrieval
- `POST /entity-context` — entity context lookup

### Web UI

#### OpenWebUI (internal port 8080, reached via Traefik)
**Purpose**: Web-based chat interface (Ollama frontend)

**Features**: chat, RAG integration, tool calling, model selection. Depends on postgres,
rag-pipeline, and optionally ollama. This is the only user-facing web app; there is no custom
frontend framework.

### Monitoring

#### Prometheus (`prom/prometheus:v3.13.0`, host 9090)
Metrics storage and querying. Scrapes core services and the exporters below.

#### Grafana (`grafana/grafana:13.1`, host 3000)
Dashboards. Traefik route has an Authelia `forwardauth` middleware, but since Authelia is
disabled that auth is not currently enforced.

#### InfluxDB (`influxdb:3.10.1-core`, host 8086)
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
postgres-exporter (v0.20.1), redis-exporter (v1.86.0, no healthcheck), rabbitmq-exporter
(v1.0.0-RC9, healthcheck disabled), node-exporter (v1.11.1), cadvisor (v0.55.1),
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

(Authelia would sit in front of some routers but is disabled.)

## Data Flow

### API Request Flow
```
Client → Traefik → API Gateway → Service → Database/Cache
```
(Authelia forwardauth is wired on some routers but disabled.)

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
docker compose --file docker/compose/docker-compose.yml up -d --scale api-gateway=3
```

### Vertical Scaling
Stateful services (PostgreSQL, Redis, Qdrant, Neo4j) scale vertically by adjusting resource
limits in `docker-compose.yml`.

## Service Configuration

### Environment Variables
- Edited in root `./.env` (single source of truth)
- `setup.sh` mirrors it to `docker/compose/.env` (the file Compose reads) — auto-generated, do not edit
- Template in root `./.env.example`
- Never commit `.env`

### Health Checks
28/31 services define container healthchecks (`/health` for the core APIs). Three services lack a
healthcheck because their images cannot run one.

### Restart Policies
Services use `restart: unless-stopped`.

## Security

### Network Segmentation
- **Edge**: only Traefik and the monitoring services expose host ports.
- **Storage**: PostgreSQL, Redis, Qdrant, Neo4j, MinIO, RabbitMQ, and the schema registry are
  internal-only; management UIs are Traefik-routed with IP whitelists.
- **Networks**: `minder-network` (all services) and `minder-monitoring` (attachable, prepared).

### Authentication
- JWT for API authentication (bcrypt password hashing)
- Authelia SSO is present but disabled
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
consideration include stricter CI gates, offline TTS (Piper), completing the Traefik
dynamic/access config, and Authelia keep-vs-drop.

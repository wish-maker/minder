# Minder Platform - System Overview

## Current Status

**Platform Version:** 1.0.0
**Last Updated:** 2026-08-08
**Containers:** 36 defined (Authelia + docker-socket-proxy included — enabled). Two are
failover-mode sidecars (`ollama-router`, `tts-stt-router`) that stay inactive unless their
respective `OLLAMA_FAILOVER_PRIMARY`/`TTS_STT_FAILOVER_PRIMARY` env var is set — the common
default (internal mode, no failover) runs 34. `setup.sh install` seeds the
**standard** bundle profile (core + inference + rag + chat); monitoring, graph-rag, and
voice are opt-in (`setup.sh bundle enable <name>`, or `install --profile full` to start
every non-failover-gated service). `start` then honours the recorded bundle state
(`bundles.state.json`). Started services run healthy; 5 carry no active healthcheck
(otel-collector, redis-exporter, rabbitmq-exporter, authelia, docker-socket-proxy). See
[Service Bundles](bundles.md).
**Core API Services:** 8 (api-gateway, plugin-registry, marketplace, plugin-state-manager, rag-pipeline, model-management, tts-stt, graph-rag)
**Data Stores:** 7 (PostgreSQL, Redis, Qdrant, Neo4j, RabbitMQ, MinIO, schema-registry)
**AI Runtime:** Ollama with local LLM support (profile-gated; disabled when using an external/native Ollama host)
**Deploy Status:** Clean install proven from zero (`docker compose down -v` → `bash setup.sh start`)

**Deferred / Disabled:**
- ⏸️ Role-based access control — NOT implemented. Only JWT authentication exists today.

**Enabled:**
- ✅ Authelia SSO/2FA — enabled, enforcing forward-auth on 6 Traefik routers (minio, api-gateway, grafana, openwebui, jaeger, client).

> Five services ship without an active healthcheck: `otel-collector`, `redis-exporter`, and
> `rabbitmq-exporter` because their images lack the tooling to run one (report "no-healthcheck",
> not "unhealthy"); `authelia` and `docker-socket-proxy` simply don't have one configured.

## Architecture Overview

Minder is a local AI orchestration platform providing JWT-authenticated APIs, RAG pipelines
(Standard/Conversational/HyDE/Self-RAG/auto via the query `method`; corrective wired + adaptive rerank/compress flags + hybrid/parent-child retrieval strategies — all wired, #45), a knowledge-graph service, a manifest-based plugin system, and a
full observability stack. All services run in Docker and are provisioned by a single `setup.sh`
entrypoint — a thin shim over the native-Python setup CLI (`python -m scripts.setup`; the
original bash is preserved as `setup.bash.sh` for behavior-gate parity only).

### System Capabilities

- **Plugin Management** - Manifest-based plugins with a defined lifecycle (no arbitrary code execution)
- **RAG** - Document ingestion, chunking, embeddings, vector retrieval; Standard/Conversational/HyDE/Self-RAG/auto RAG live via the query `method` field (corrective wired + adaptive rerank/compress flags + hybrid/parent-child retrieval strategies — all wired, #45)
- **Knowledge Graph** - spaCy NER entity extraction and Neo4j graph construction/retrieval (graph-rag)
- **Authentication** - JWT-based auth (bcrypt password hashing) on core services
- **Observability** - Prometheus, Grafana, InfluxDB, Alertmanager, Jaeger, OpenTelemetry collector
- **Speech** - TTS (Piper offline default, gTTS fallback) and STT (speech_recognition), ~12 languages, Turkish default

## Service Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        SECURITY / EDGE                          │
│  ┌──────────────┐              ┌──────────────────────────────┐ │
│  │   Traefik    │ (80/443)     │  Authelia (9091) — ENABLED   │ │
│  │ Reverse Proxy│ v3.7.10      │  (forward-auth, 6 routers)   │ │
│  └──────────────┘              └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                          CORE API (8)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   API    │ │ Plugin   │ │ Market   │ │  State   │          │
│  │ Gateway  │ │ Registry │ │ place    │ │ Manager  │          │
│  │  :8000   │ │  :8001   │ │  :8002   │ │  :8003   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   RAG    │ │  Model   │ │ TTS/STT  │ │  Graph   │          │
│  │ Pipeline │ │ Mgmt     │ │          │ │  RAG     │          │
│  │  :8004   │ │  :8005   │ │  :8006   │ │  :8008   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│              INFERENCE + WEB UI (internal network)              │
│  ┌──────────┐ ┌────────────────────┐ ┌─────────────────────┐    │
│  │  Ollama  │ │OpenWebUI (chat UI) │ │ client :8009 (admin)│    │
│  │  :11434  │ │reached via Traefik │ │ React/Vite, own repo│    │
│  └──────────┘ └────────────────────┘ └─────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│           STORAGE (internal only — NOT host-exposed)            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │PostgreSQL│ │  Redis   │ │  Neo4j   │ │ Qdrant   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌────────────────────┐             │
│  │ RabbitMQ │ │  MinIO   │ │ schema-registry    │             │
│  └──────────┘ └──────────┘ └────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                        OBSERVABILITY                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │Prometheus│ │ Grafana  │ │ Jaeger   │ │ Alertmgr │          │
│  │  :9090   │ │  :3000   │ │  :16686  │ │  :9093   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  InfluxDB :8086 · Telegraf · OTel Collector · 6 exporters      │
└─────────────────────────────────────────────────────────────────┘

Total: 36 services defined across core APIs, inference, storage, and observability
(includes Authelia and docker-socket-proxy, both enabled); 34 run in the common default
(internal Ollama/TTS-STT, no failover) — see Current Status above.
```

## Service Descriptions

### Edge / Security

#### Traefik (Host 80/443, dashboard 8081)
- Reverse proxy, TLS termination, routing via Docker labels (`exposedByDefault: false`)
- The only host-facing entry point besides directly-exposed monitoring services
- Version: `traefik:v3.7.10`

#### Authelia (9091) — ✅ ENABLED
- Provides SSO and 2FA, running as `minder-authelia` in `docker-compose.yml`
- A `forwardauth` middleware is wired on six Traefik routers (minio, api-gateway, grafana,
  openwebui, jaeger, client), and that auth **is enforced** — unauthenticated requests get a 302
  redirect to the Authelia portal. Full browser SSO still needs real DNS + TLS on the deploy.

### Core APIs

All eight core APIs are FastAPI services with real implementations.

#### API Gateway (Port 8000)
- Single entry point; JWT + bcrypt auth, Redis-backed rate limiting (fail-open), httpx proxy to
  registry / RAG / model-management

#### Plugin Registry (Port 8001)
- Manifest-based plugin install (no code execution), webhook routes, 60s health loop,
  service discovery in Redis, AI-tool aggregation, marketplace auto-sync

#### Marketplace (Port 8002)
- Discovery / search / featured listings, license tiers (community / pro / enterprise),
  AI-tool catalog, plugin dependency graph stored in Neo4j

#### Plugin State Manager (Port 8003)
- Plugin state, tool discovery, and tool execution with license validation

#### RAG Pipeline (Port 8004)
- Knowledge bases, document upload (PDF/TXT/MD via pypdf + LangChain splitter), Qdrant vectors,
  Ollama embeddings + LLM; Standard/Conversational/HyDE/Self-RAG/auto RAG live via the query `method` field (corrective wired + adaptive rerank/compress flags + hybrid/parent-child retrieval strategies — all wired, #45)

#### Model Management (Port 8005)
- Ollama model list / pull / delete / test (real). `/models/{id}/constraints` and
  `/models/{id}/metrics` are placeholders; fine-tuning delegates out.

#### TTS/STT (Port 8006)
- Text-to-speech via Piper (offline, WAV) with gTTS (MP3) fallback, speech-to-text via speech_recognition (Google), ~12 languages,
  Turkish default

#### Graph RAG (Port 8008)
- spaCy NER entity extraction, Neo4j knowledge-graph construction, graph retrieval, entity context.
  Endpoints: `POST /extract`, `/construct-graph`, `/retrieve`, `/entity-context`, `DELETE /graph/document/{id}`

### Inference & Web UI

#### Ollama (internal 11434)
- Local LLM runtime. Profile-gated (`internal-ollama`): runs only when `OLLAMA_BASE_URL` is empty
  (local mode). When set, an external/native host is used and the container stays inactive.
  Models are auto-pulled into the `/root/.ollama/models` volume; set `OLLAMA_MODELS` in
  `.env` to choose which (compose maps it internally to `OLLAMA_PULL_MODELS` for the container).
- **Third mode: failover.** A mode-gated `minder-ollama-router` (nginx, profile `ollama-router`)
  fronts an external primary with automatic fallback to the internal container, transparent to
  every consumer (`OLLAMA_BASE_URL` points at the router). See
  [Ollama modes](../getting-started/ai-setup.md#ollama-modes-internal-external-failover) for the
  full internal/external/failover breakdown.

#### OpenWebUI (internal 8080, reached via Traefik)
- Web-based chat UI. Depends on postgres, rag-pipeline, and optionally ollama.

#### client (host 8009, `src/services/client/`)
- Bespoke React/Vite admin frontend — the control-plane for everything
  OpenWebUI's chat UI doesn't cover: RAG (knowledge bases, pipelines, a
  spaCy/Neo4j knowledge-graph explorer distinct from vector search), plugins
  (marketplace, per-plugin config, AI-tool catalog), and platform ops (Ollama
  model lifecycle, feature-bundle toggles, fleet health/logs, a TTS/STT
  tester). A static SPA, not a FastAPI service — no `/docs`/OpenAPI schema of
  its own. See `docs/api/reference.md` for the exact page-to-endpoint mapping.

## Data Flow

### Plugin Registration Flow
```
User → API Gateway → Plugin Registry → PostgreSQL
                         ↓
                    Health loop (60s) → State Manager → Monitoring
```

### RAG Request Flow
```
User → API Gateway → RAG Pipeline (:8004) → Ollama (embed) → Qdrant (search)
                                    ↓
                              Ollama (LLM generate) → Response → User
```

### Marketplace Flow
```
User → API Gateway → Marketplace → license-tier check → Neo4j (dependency graph)
                          ↓
                     Plugin Registry (install manifest)
```

## Technology Stack

### Backend
- **Framework**: FastAPI on Python 3.11/3.12 (services use `python:3.12-slim`; graph-rag uses `python:3.11-slim`)
- **Databases**: PostgreSQL 18.4, Redis 8.10, Qdrant 1.19, Neo4j 2026.06 (community)
- **Object store**: MinIO · **Message bus**: RabbitMQ 4.3 · **Schema registry**: Apicurio (SQL)
- **LLM**: Ollama with local models
- **Authentication**: JWT (bcrypt) at the gateway, plus Authelia SSO/2FA on 6 Traefik routers. No RBAC.

### Infrastructure
- **Containers**: Docker + Docker Compose (`docker/docker-compose.yml`, hand-maintained)
- **Reverse Proxy**: Traefik v3
- **Monitoring**: Prometheus + Grafana + InfluxDB + Alertmanager + Jaeger + OpenTelemetry
- **CI/CD**: GitHub Actions

### Web UI
- **OpenWebUI** (Ollama chat frontend) for chat.
- **client** (React 18 + Vite + Tailwind CSS v4, `react-router-dom`) for everything else — the platform's admin/control-plane surface.

## Security Architecture

### Authentication Flow
1. Requests enter through Traefik (TLS termination, routing).
2. Traefik has an Authelia `forwardauth` middleware wired on six routers (minio, api-gateway,
   grafana, openwebui, jaeger, client); Authelia is enabled, so unauthenticated requests are
   302-redirected to the Authelia portal.
3. Core APIs validate JWT tokens (issued by the API Gateway, bcrypt-hashed credentials).

### Authorization
- JWT token validation only. **Role-based access control is not implemented.**

### Network Security
- **Internal isolation**: services communicate on the `minder-network` Docker network.
- **Storage backends are internal-only** — PostgreSQL, Redis, Qdrant, Neo4j, MinIO, RabbitMQ, and
  the schema registry are not published to host ports. Where a UI is needed (Neo4j browser, MinIO
  console, RabbitMQ management) it is routed through Traefik with an IP whitelist.
- **External access**: only Traefik (80/443) plus the monitoring services that intentionally
  expose host ports (Prometheus 9090, Grafana 3000, Alertmanager 9093, InfluxDB 8086, Jaeger
  16686, OTel collector 14317/14318).
- **Secrets**: environment variables only. Root `./.env` is the single source of truth; `setup.sh`
  mirrors it to `docker/.env` (auto-generated, do not edit).

## Monitoring & Observability

- **Metrics**: Prometheus scrapes core services and six exporters (postgres, redis, rabbitmq,
  node, cAdvisor, blackbox); Telegraf feeds InfluxDB for time-series data.
- **Dashboards**: Grafana.
- **Tracing**: Jaeger + an OpenTelemetry collector.
- **Health checks**: `/health` endpoints on the core APIs; container-level healthchecks on 31/36
  services (5 without an active one — see Current Status above).

## Development Workflow

```bash
# Start everything
bash setup.sh start

# Start a specific service
docker compose --file docker/docker-compose.yml up -d api-gateway

# View logs
docker compose --file docker/docker-compose.yml logs -f <service>

# Rebuild and restart
docker compose --file docker/docker-compose.yml up -d --build <service>

# Run tests
pytest tests/unit/ -v
```

## Roadmap

Development work is now tracked as GitHub issues in `wish-maker/minder` (see `roadmap.md`).
This is a development environment; production hardening for the Raspberry Pi 4 target is ongoing.

# Minder Platform - System Overview

## Current Status

**Platform Version:** 1.0.0
**Last Updated:** 2026-07-10
**Containers:** 31 services are defined in compose (Authelia excluded — disabled). A full
`bash setup.sh install` actually runs **30** — `schema-registry` is defined but not wired
into `setup.sh` and never starts ([#42](https://github.com/wish-maker/minder/issues/42)).
`bash setup.sh start` alone runs **29** (MinIO is initialized only by `install`,
[#43](https://github.com/wish-maker/minder/issues/43)). Everything else runs healthy;
only 3 services carry no healthcheck by design (otel-collector, redis-exporter,
rabbitmq-exporter).
**Core API Services:** 8 (api-gateway, plugin-registry, marketplace, plugin-state-manager, rag-pipeline, model-management, tts-stt, graph-rag)
**Data Stores:** 7 (PostgreSQL, Redis, Qdrant, Neo4j, RabbitMQ, MinIO, schema-registry)
**AI Runtime:** Ollama with local LLM support (profile-gated; disabled when using an external/native Ollama host)
**Deploy Status:** Clean install proven from zero (`docker compose down -v` → `bash setup.sh start`)

**Deferred / Disabled:**
- ⏸️ Authelia SSO/2FA — DISABLED (commented out in `docker-compose.yml`); crash loop from missing DB + NTP. Keep-vs-drop is an open decision.
- ⏸️ Role-based access control — NOT implemented. Only JWT authentication exists today.

> Three services (`otel-collector`, `redis-exporter`, `rabbitmq-exporter`) ship without a healthcheck because their images lack the tooling to run one. They report "no-healthcheck", not "unhealthy".

## Architecture Overview

Minder is a local AI orchestration platform providing JWT-authenticated APIs, RAG pipelines
(Standard + Conversational; HyDE/Self-RAG exist as unwired modules — #45), a knowledge-graph service, a manifest-based plugin system, and a
full observability stack. All services run in Docker and are provisioned by a single `setup.sh`.

### System Capabilities

- **Plugin Management** - Manifest-based plugins with a defined lifecycle (no arbitrary code execution)
- **RAG** - Document ingestion, chunking, embeddings, vector retrieval; Standard + Conversational RAG live (HyDE/Self-RAG modules present but unwired — #45)
- **Knowledge Graph** - spaCy NER entity extraction and Neo4j graph construction/retrieval (graph-rag)
- **Authentication** - JWT-based auth (bcrypt password hashing) on core services
- **Observability** - Prometheus, Grafana, InfluxDB, Alertmanager, Jaeger, OpenTelemetry collector
- **Speech** - TTS (gTTS) and STT (speech_recognition), ~12 languages, Turkish default

## Service Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        SECURITY / EDGE                          │
│  ┌──────────────┐              ┌──────────────────────────────┐ │
│  │   Traefik    │ (80/443)     │  Authelia (9091) — DISABLED  │ │
│  │ Reverse Proxy│ v3.7.7       │  (commented out in compose)  │ │
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
│  ┌──────────┐  ┌────────────────────────────────────────────┐  │
│  │  Ollama  │  │ OpenWebUI (chat UI, reached via Traefik)   │  │
│  │  :11434  │  │ (there is NO custom frontend app)          │  │
│  └──────────┘  └────────────────────────────────────────────┘  │
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

Total: 31 containers across core APIs, inference, storage, and observability
(Authelia is defined but disabled and is not counted in the 31.)
```

## Service Descriptions

### Edge / Security

#### Traefik (Host 80/443, dashboard 8081)
- Reverse proxy, TLS termination, routing via Docker labels (`exposedByDefault: false`)
- The only host-facing entry point besides directly-exposed monitoring services
- Version: `traefik:v3.7.7`

#### Authelia (9091) — ⏸️ DISABLED
- Would provide SSO and 2FA, but is **commented out** in `docker-compose.yml`
- Disabled due to a crash loop (missing database + NTP sync). A `forwardauth` middleware is still
  wired on four Traefik routers (api-gateway, grafana, openwebui, jaeger), but because the
  container is down, that auth is **not enforced**. Keep-vs-drop remains an open decision.

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
  Ollama embeddings + LLM; Standard + Conversational RAG live (HyDE/Self-RAG/decision-engine are unwired modules — #45)

#### Model Management (Port 8005)
- Ollama model list / pull / delete / test (real). `/models/{id}/constraints` and
  `/models/{id}/metrics` are placeholders; fine-tuning delegates out.

#### TTS/STT (Port 8006)
- Text-to-speech via gTTS (MP3), speech-to-text via speech_recognition (Google), ~12 languages,
  Turkish default

#### Graph RAG (Port 8008)
- spaCy NER entity extraction, Neo4j knowledge-graph construction, graph retrieval, entity context.
  Endpoints: `POST /extract`, `/construct-graph`, `/retrieve`, `/entity-context`

### Inference & Web UI

#### Ollama (internal 11434)
- Local LLM runtime. Profile-gated (`internal-ollama`): runs only when `OLLAMA_BASE_URL` is empty
  (local mode). When set, an external/native host is used and the container stays inactive.
  Models are auto-pulled via `OLLAMA_PULL_MODELS` into the `/root/.ollama/models` volume.

#### OpenWebUI (internal 8080, reached via Traefik)
- Web-based chat UI (the platform's only user-facing web app). Depends on postgres, rag-pipeline,
  and optionally ollama. There is **no** custom Next.js/React frontend.

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
- **Databases**: PostgreSQL 18.4, Redis 8.8, Qdrant 1.18, Neo4j 2026.05 (community)
- **Object store**: MinIO · **Message bus**: RabbitMQ 4.3 · **Schema registry**: Apicurio (SQL)
- **LLM**: Ollama with local models
- **Authentication**: JWT (bcrypt). No RBAC. Authelia is present but disabled.

### Infrastructure
- **Containers**: Docker + Docker Compose (`docker/compose/docker-compose.yml`, hand-maintained)
- **Reverse Proxy**: Traefik v3
- **Monitoring**: Prometheus + Grafana + InfluxDB + Alertmanager + Jaeger + OpenTelemetry
- **CI/CD**: GitHub Actions

### Web UI
- **OpenWebUI** (Ollama chat frontend). There is no bespoke frontend framework in this repo.

## Security Architecture

### Authentication Flow
1. Requests enter through Traefik (TLS termination, routing).
2. Traefik has an Authelia `forwardauth` middleware wired on some routers, but Authelia is
   currently disabled, so that step is a no-op.
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
  mirrors it to `docker/compose/.env` (auto-generated, do not edit).

## Monitoring & Observability

- **Metrics**: Prometheus scrapes core services and six exporters (postgres, redis, rabbitmq,
  node, cAdvisor, blackbox); Telegraf feeds InfluxDB for time-series data.
- **Dashboards**: Grafana.
- **Tracing**: Jaeger + an OpenTelemetry collector.
- **Health checks**: `/health` endpoints on the core APIs; container-level healthchecks on 28/31
  services.

## Development Workflow

```bash
# Start everything
bash setup.sh start

# Start a specific service
docker compose --file docker/compose/docker-compose.yml up -d api-gateway

# View logs
docker compose --file docker/compose/docker-compose.yml logs -f <service>

# Rebuild and restart
docker compose --file docker/compose/docker-compose.yml up -d --build <service>

# Run tests
pytest tests/unit/ -v
```

## Roadmap

Development work is now tracked as GitHub issues in `wish-maker/minder` (see `roadmap.md`).
This is a development environment; production hardening for the Raspberry Pi 4 target is ongoing.

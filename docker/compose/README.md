# Minder Platform

Minder is a full-stack AI orchestration platform running on a Raspberry Pi 4 (RPi-4-01).
It enables local LLM inference, RAG pipelines, large-scale data correlation analysis,
plugin-driven data ingestion, and custom chatbot creation.
All services run in Docker and are provisioned via a single `setup.sh` script.

## Service Map

### Minder Core API
- `minder-api-gateway`             :8000 — Central entry point for all external requests
- `minder-plugin-registry`         :8001 — Plugin registration, discovery, lifecycle management
- `minder-marketplace`             :8002 — Plugin/tool marketplace and package management
- `minder-plugin-state-manager`    :8003 — Plugin state machine and hook dispatch engine
- `minder-rag-pipeline`            :8004 — Chunking, embedding, vector retrieval
- `minder-model-management`      :8005 — Model versioning, deployment lifecycle
- `minder-tts-stt`                :8006 — Speech-to-text / text-to-speech
- `minder-model-fine-tuning`       :8007 — Local model fine-tuning and customization

### Inference
- `minder-ollama`    :11434 — Local LLM runtime (Llama, Mistral, etc.)
- `minder-openwebui` :8080  — Web-based chat UI (Ollama frontend)

### Storage
- `minder-postgres`  :5432 — Relational data: users, sessions, metadata
- `minder-redis`     :6379 — Cache, session management, pub/sub
- `minder-qdrant`    :6333 — Vector DB for RAG embeddings
- `minder-neo4j`     :7687 — Graph DB for entity relationships and correlation analysis
- `minder-minio`     :9000 — S3-compatible object store: files, models, artifacts
- `minder-rabbitmq`  :5672 — Async message queue and hook trigger bus

### Observability
- `minder-grafana`       :3000  — Metrics dashboard
- `minder-prometheus`    :9090  — Metrics collection and storage
- `minder-jaeger`        :16686 — Distributed tracing
- `minder-influxdb`      :8086  — Time-series data
- `minder-alertmanager`  :9093  — Alert routing
- `minder-otel-collector` :14317 — OpenTelemetry collector ⚠️ currently unhealthy
- `minder-telegraf`      —      — Metrics collection agent

### Security & Networking
- `minder-traefik`   :80/:443 — Reverse proxy, SSL termination, routing
- `minder-authelia`  :9091    — SSO, MFA, access control

## Plugin System

Plugins follow this lifecycle:
`REGISTERED → INSTALLED → ACTIVE → SUSPENDED → UNINSTALLED`

Each transition dispatches the corresponding hook:
`on_register`, `on_install`, `on_activate`, `on_suspend`, `on_error`, `on_uninstall`

Plugins can write to any storage backend:
- **postgres**  → structured/relational data
- **qdrant**    → vector embeddings (semantic search)
- **neo4j**     — graph relationships (entity linking, correlation discovery)
- **minio**     → raw files, model artifacts, binaries
- **influxdb**  → time-stamped series data
- **rabbitmq**  → async events, pipeline triggers

Plugins can also register as **AI tools** for Ollama function calling:
Schema: `{ name, description, input_schema, endpoint }`

## Current Status

### ✅ **Working & Tested Services (2)**
1. **minder-api-gateway** (:8000) - Authentication with Authelia, JWT validation, rate limiting
2. **minder-rag-pipeline** (:8004) - Full RAG functionality with PostgreSQL persistence tested

### 🚧 **In Development**
- All other services are in various stages of development
- Infrastructure components (Docker, networking, databases) are configured
- Most services have basic scaffolding but are not fully implemented

### ⚠️ **Known Issues**
| Service | Status | Likely Cause |
|---------|--------|-------------|
| `minder-redis-exporter` | unhealthy | Redis connectivity or auth config |
| `minder-otel-collector` | unhealthy | OTLP endpoint misconfiguration |

## Common Commands

```bash
# Health overview
docker ps -a --filter health=unhealthy

# Stream service logs
docker logs minder-<service> --tail 50 -f

# Restart a service
cd ~/minder && docker compose restart <service>

# Resource usage
docker stats --no-stream

# API health checks
curl http://localhost:8000/health          # api-gateway
curl http://localhost:8001/plugins         # plugin-registry
curl http://localhost:8004/health          # rag-pipeline
curl http://localhost:11434/api/tags       # ollama model list

# Ingest a document into RAG
curl -X POST http://localhost:8004/ingest -F "file=@doc.pdf"
```

## Development Conventions

- New plugins MUST register via `minder-plugin-registry` API (:8001)
- Semantic/vector search → always use `minder-qdrant` (:6333)
- Graph relationships and correlation discovery → `minder-neo4j` (:7687)
- All async work → queue through `minder-rabbitmq` (:5672)
- LLM inference → `minder-ollama` (:11434) directly
- Instrument all services with OpenTelemetry → `minder-otel-collector` (:14317)
- This is a development environment — production hardening is not yet applied

## Platform

Host: RPi-4-01 (Raspberry Pi 4) · Setup: `bash setup.sh` · Containers: 32

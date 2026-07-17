# Minder Platform - Development Roadmap

> **Last Updated:** 2026-07-10
> **Status:** Development environment on a Raspberry Pi 4; production hardening ongoing.
> **Live tracker:** GitHub issues in `wish-maker/minder` are the source of truth for planned work.

---

## How the Roadmap Works

This document is intentionally **conceptual**. The detailed, up-to-date backlog lives as GitHub
issues (`wish-maker/minder`, currently roughly #7–#36) grouped under the "ARM Pi Production
Deploy" milestone. When this file and the issue tracker disagree, **the tracker wins**.

Use the tracker for concrete, actionable items; use this document for the shape of the platform
and where it is headed.

---

## What Exists Today

The platform runs as 31 Docker containers provisioned by `bash setup.sh`. See
`docs/architecture/overview.md` and `docs/architecture/microservices.md` for the current,
authoritative service breakdown.

**Core APIs (8, all FastAPI, real implementations):**
- API Gateway (8000) — JWT + bcrypt auth, Redis rate limiting, httpx proxy
- Plugin Registry (8001) — manifest-based plugin lifecycle (no code execution)
- Marketplace (8002) — discovery/licensing, dependency graph in Neo4j
- Plugin State Manager (8003) — plugin state + AI-tool execution
- RAG Pipeline (8004) — ingestion, embeddings, retrieval; Standard + Conversational RAG live (HyDE/Self-RAG modules unwired — #45)
- Model Management (8005) — Ollama model lifecycle (constraints/metrics are placeholders)
- TTS/STT (8006) — gTTS + speech_recognition, ~12 languages
- Graph RAG (8008) — spaCy NER + Neo4j knowledge graph

**Storage (internal-only):** PostgreSQL 18.4, Redis 8.8, Qdrant 1.18, Neo4j 2026.05, MinIO,
RabbitMQ 4.3, Apicurio schema registry.

**Inference & UI:** Ollama (profile-gated), OpenWebUI (chat frontend).

**Observability:** Prometheus, Grafana, InfluxDB, Telegraf, Alertmanager, Jaeger, OpenTelemetry
collector, plus six exporters.

**Not present / not implemented (do not expect these):**
- Model fine-tuning service — **removed** (do not re-add)
- Standalone `ai-service` — **removed**
- Custom frontend app (Next.js/React) — there is none; the UI is OpenWebUI
- RBAC — only JWT auth exists
- Default domain plugins (crypto/weather/network/news/tefas) — aspirational, none shipped
- Authelia SSO/2FA — defined but **disabled** (commented out in compose)

---

## Thematic Direction

These are the broad themes the GitHub backlog is organized around. Each maps to one or more issues
in `wish-maker/minder`.

### 1. Raspberry Pi Production Deploy (milestone)
ARM deployment hardening: image/version pinning, Traefik router completion, resolving remaining
per-service config landmines, and clean-install reliability on the Pi.

### 2. RAG Enhancements
Continued work on the retrieval pipeline. HyDE and Self-RAG are implemented as modules but are
**not yet wired into the live query endpoint** ([#45](https://github.com/wish-maker/minder/issues/45));
wiring them in (plus further retrieval-quality work) is tracked on the backlog.

### 3. Authelia Decision
Authelia is currently disabled. Whether to finish wiring it (DB auto-init + NTP) or drop it is an
open decision on the tracker.

### 4. Setup / Tooling — Python port (DONE)
`setup.sh` was split into `scripts/lib/` bash modules (Stage 1), then **fully ported to
native Python** under `scripts/setup/` (Stage 2, issue #7 — closed). `setup.sh` is now a
thin shim that execs `python -m scripts.setup`; the original bash lives on as
`setup.bash.sh` + `scripts/lib/*.sh`, used only as the parity reference for the behavior
gate (`scripts/gate/`). No bash dependency remains in the setup path (Linux/macOS/Windows).
Remaining tooling work: deriving image versions from the compose file (issue #12).

### 5. CI Quality Gates
CI is consolidated into a fast quality gate, a test workflow, a deep security workflow, and a
Docker image-update workflow. Evaluating stricter gates (mypy, coverage thresholds, bandit) is on
the backlog.

### 6. Config Consolidation
Per-service config lives under `docker/services/`; `docker/compose/docker-compose.yml` is the
hand-maintained source of truth. Reconciling remaining mounted config dirs (traefik dynamic,
rabbitmq definitions) is tracked on the backlog.

### 7. Plugin Implementations
Deciding whether to implement the aspirational domain plugins or formally drop them. Until real
implementations exist, `default_plugins.yml` stays an empty stub.

### 8. Speech (Offline TTS)
Evaluating offline TTS (Piper) to reduce dependence on gTTS/network.

---

## Longer-Term Considerations

These are not committed and may or may not become issues:

- Container orchestration beyond Docker Compose (e.g. Kubernetes/Helm) for the production target
- Load testing and performance tuning (no measured benchmarks are published today)
- Centralized logging
- Multi-region / HA deployment

---

## References

- `docs/architecture/overview.md` — system overview
- `docs/architecture/microservices.md` — service breakdown
- `docs/architecture/plugins.md` — plugin system
- `docs/architecture/project-structure.md` — repository layout
- GitHub issues in `wish-maker/minder` — the live backlog

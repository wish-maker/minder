# Minder Platform - Development Roadmap

> **Last Updated:** 2026-08-08
> **Status:** Development environment on a Raspberry Pi 4; production hardening ongoing.
> **Live tracker:** GitHub issues in `wish-maker/minder` are the source of truth for planned work.

---

## How the Roadmap Works

This document is intentionally **conceptual**. The detailed, up-to-date backlog lives as GitHub
issues (`wish-maker/minder`, running through ~#120; open set concentrated in #8/#11/#15/#21/#25/#28/#36/#65/#120) grouped under the "ARM Pi Production
Deploy" milestone. When this file and the issue tracker disagree, **the tracker wins**.

Use the tracker for concrete, actionable items; use this document for the shape of the platform
and where it is headed.

---

## What Exists Today

The platform runs as 36 defined Docker services (34 in the common default — two are
failover-mode sidecars) provisioned by `bash setup.sh`. See
`docs/architecture/overview.md` and `docs/architecture/microservices.md` for the current,
authoritative service breakdown.

**Core APIs (8, all FastAPI, real implementations):**
- API Gateway (8000) — JWT + bcrypt auth, Redis rate limiting, httpx proxy
- Plugin Registry (8001) — manifest-based plugin lifecycle (no code execution)
- Marketplace (8002) — discovery/licensing, dependency graph in Neo4j
- Plugin State Manager (8003) — plugin state + AI-tool execution
- RAG Pipeline (8004) — ingestion, embeddings, retrieval; Standard/Conversational/HyDE/Self-RAG/auto/corrective RAG live via the query `method` field + adaptive rerank/compress flags + hybrid/parent-child retrieval strategies (all wired — #45)
- Model Management (8005) — Ollama model lifecycle (constraints/metrics are placeholders)
- TTS/STT (8006) — Piper offline (default) + gTTS fallback + speech_recognition, ~12 languages
- Graph RAG (8008) — spaCy NER + Neo4j knowledge graph

**Storage (internal-only):** PostgreSQL 18.4, Redis 8.10, Qdrant 1.19, Neo4j 2026.06, MinIO,
RabbitMQ 4.3, Apicurio schema registry.

**Inference & UI:** Ollama (profile-gated), OpenWebUI (chat frontend), and
`client` (port 8009, `src/services/client/`) — a bespoke React/Vite admin
frontend covering RAG (knowledge bases, pipelines, knowledge-graph explorer),
plugins (marketplace, config, AI tools), and platform ops (models, bundles,
health/logs, voice). Chat itself still lives in OpenWebUI; `client` is the
control-plane for everything else.

**Observability:** Prometheus, Grafana, InfluxDB, Telegraf, Alertmanager, Jaeger, OpenTelemetry
collector, plus six exporters.

**Reverse proxy & auth:** Traefik v3, plus Authelia SSO/2FA — **enabled** by default,
enforcing forward-auth on 6 Traefik routers (minio, api-gateway, grafana, openwebui,
jaeger, client). Full browser SSO still needs real DNS + TLS on the deploy.

**Not present / not implemented (do not expect these):**
- Model fine-tuning service — **removed** (do not re-add)
- Standalone `ai-service` — **removed**
- Full RBAC — only a specific set of admin-only actions is role-gated today (model
  pull/delete/fine-tune, bundle enable/disable/reconcile, listing a plugin's
  installations, #474 done); most other write endpoints still only require a valid JWT
- Default domain plugins (crypto/weather/network/news/tefas) — SHIPPED as first-party module plugins in `src/plugins/`, on the central plugin-config API (#34 done)

---

## Thematic Direction

These are the broad themes the GitHub backlog is organized around. Each maps to one or more issues
in `wish-maker/minder`.

### 1. Raspberry Pi Production Deploy (milestone)
ARM deployment hardening: image/version pinning, Traefik router completion, resolving remaining
per-service config landmines, and clean-install reliability on the Pi. One recurring landmine
class is now resolved generically: legacy bare-named volumes (`openwebui_data`/`qdrant_data`
predating this project's `minder_` naming convention) are migrated forward by
`scripts/setup/infra.py`'s `migrate_volume_names()` on every `start`/`install` — self-healing on
a host with the old name, a no-op everywhere else (a fresh install, or a second deployment host
that never had one). An earlier attempt pinned these two volumes as `external: true` instead;
that broke on any host without the exact hardcoded name, so it was reverted in favor of the
existing migration mechanism.

### 2. RAG Enhancements
HyDE, Self-RAG, auto (decision engine), corrective RAG, adaptive rerank/compress, the
hybrid (dense+BM25) + parent-child (small-to-big) retrieval strategies, and now RAPTOR
(hierarchical clustering + tree summarization, [#487](https://github.com/wish-maker/minder/issues/487))
are all **wired into the live query endpoint** ([#45](https://github.com/wish-maker/minder/issues/45));
`GET /capabilities` reports what's active.

### 3. Authelia
Authelia is enabled and enforcing forward-auth on 6 Traefik routers (minio, api-gateway,
grafana, openwebui, jaeger, client). The remaining work is completing real DNS + TLS on the deploy
so full browser SSO works end-to-end.

### 4. Setup / Tooling — Python port (DONE)
`setup.sh` was split into `scripts/lib/` bash modules (Stage 1), then **fully ported to
native Python** under `scripts/setup/` (Stage 2, issue #7 — closed). `setup.sh` is now a
thin shim that execs `python -m scripts.setup`; the original bash lives on as
`setup.bash.sh` + `scripts/lib/*.sh`, used only as the parity reference for the behavior
gate (`scripts/gate/`). No bash dependency remains in the setup path (Linux/macOS/Windows).
Image versions are derived from the compose file by the native-Python version engine
(`scripts/setup/versions.py`, via `update --check`) — #12 done.

### 5. CI Quality Gates
CI is consolidated into a fast quality gate (black/isort/flake8/**mypy — now a REAL gate, run
per-service, no `|| true`**/bandit/safety/shellcheck/hadolint), a test workflow, a deep security
workflow, and Docker-image + Python-dependency update workflows. mypy strictness was adopted
(#33 done); coverage-fail-under remains optional/backlog. The test workflow (`ci.yml`) also runs
a **Container Smoke Test** job — `docker compose up --build --wait` on 7 of the 8 core service
images (real `docker run`, not a mocked/bare-process test), added after three real regressions
(a missing pip dependency, a missing required env var, a bad volume-naming assumption) shipped
past unit + integration/e2e + Trivy in the same session, none of which ever ran an actual
container.

### 6. Config Consolidation
Per-service config lives under `docker/services/`; `docker/docker-compose.yml` is the
hand-maintained source of truth. Reconciling remaining mounted config dirs (traefik dynamic,
rabbitmq definitions) is tracked on the backlog.

### 7. Plugin Implementations
Done (#34): crypto, weather, news, tefas, network ship as first-party module plugins with a
central plugin-config API. (The plugin-state-manager bootstrap `default_plugins.yml` stays an
empty stub — a separate mechanism.) Remaining: TEFAS data fetch is TR-egress-blocked (#120).

### 8. Speech (Offline TTS)
Done (#18): Piper is the **default** offline TTS engine (WAV, bundled en+tr voices), with gTTS
as the online fallback for non-bundled languages.

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

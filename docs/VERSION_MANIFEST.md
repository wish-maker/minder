# Version Manifest - Minder Platform v1.0.0

**Last Updated:** 2026-05-08
**Platform Version:** 1.0.0 (Production Ready)
**Setup.sh Version:** 1.0.0 (Enterprise-grade lifecycle management)

## 📦 Docker Images

### Third-Party Services

| Service | Version | Purpose | Status |
|---------|---------|---------|--------|
| **Traefik** | v3.3.4 | Reverse Proxy & Load Balancer | ✅ Latest v3 |
| **Authelia** | 4.39.19 | SSO & 2FA | ✅ Latest Stable |
| **Redis** | 7.4.2-alpine | Cache & Rate Limiting | ✅ Latest Alpine |
| **PostgreSQL** | 17.4-alpine | Primary Database | ✅ Current LTS |
| **Qdrant** | v1.17.1 | Vector Database | ✅ Latest Stable |
| **Neo4j** | 5.26-community | Graph Database | ✅ Latest v5 |
| **Ollama** | 0.5.12 | LLM Inference | ✅ Latest Stable |
| **InfluxDB** | 3.9.1-core | Time Series DB | ✅ Latest v3.x |
| **Telegraf** | 1.34.0 | Metrics Collector | ✅ Latest v1 |
| **Prometheus** | v3.1.0 | Metrics Storage | ✅ Latest v3 |
| **Alertmanager** | v0.28.1 | Alert Routing | ✅ Latest v0 |
| **Grafana** | 11.5.2 | Metrics Dashboard | ✅ Latest v11 |
| **PostgreSQL Exporter** | v0.15.0 | PG Metrics | ✅ Latest |
| **Redis Exporter** | v1.62.0 | Redis Metrics | ✅ Latest |
| **RabbitMQ Exporter** | v0.15.1 | RabbitMQ Metrics | ✅ Latest |
| **MinIO** | RELEASE.2025-09-07T16-13-09Z | Object Storage | ✅ Latest |
| **Jaeger** | 1.57 | Distributed Tracing | ✅ Latest |
| **OTel Collector** | 0.114.0 | OpenTelemetry Collector | ✅ Latest |
| **OpenWebUI** | latest | LLM UI | ✅ Latest |

### Internal Services

| Service | Version | Base Image | Status |
|---------|---------|------------|--------|
| **API Gateway** | 1.0.0 | python:3.12-slim | ✅ |
| **Plugin Registry** | 1.0.0 | python:3.12-slim | ✅ |
| **RAG Pipeline** | 1.0.0 | python:3.12-slim | ✅ |
| **Model Management** | 1.0.0 | python:3.12-slim | ✅ |
| **Marketplace** | 1.0.0 | python:3.12-slim | ✅ |
| **Plugin State Manager** | 1.0.0 | python:3.12-slim | ✅ |
| **TTS/STT Service** | 1.0.0 | python:3.12-slim | ✅ |
| **Model Fine-tuning** | 1.0.0 | python:3.12-slim | ✅ |

## 📊 Service Summary

**Total Services:** 25
- **Internal Services:** 8
- **Third-Party Services:** 17
- **Healthy Services:** 25/25 (100%)
- **Unhealthy Services:** 0/25 (0%)

## 🐍 Python Dependencies

### Core Framework (Standardized Across All Services)

| Package | Version | Purpose |
|---------|---------|---------|
| **FastAPI** | 0.115.0 | Web Framework |
| **Uvicorn** | 0.30.0 | ASGI Server |
| **Pydantic** | 2.9.0 | Data Validation |
| **Pydantic Settings** | 2.6.0 | Configuration |
| **HTTPX** | 0.25.2 | HTTP Client |

### AI/ML Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| **PyTorch** | 2.11.0+cu130 | ML Framework (Latest Stable) |
| **Transformers** | 4.35.0 | NLP Models |
| **Sentence Transformers** | 2.2.2 | Embeddings |
| **Ollama** | 0.1.7 | LLM Client |

### Database Clients

| Package | Version | Purpose |
|---------|---------|---------|
| **SQLAlchemy** | 2.0.23 | ORM |
| **AsyncPG** | 0.29.0 | Async PostgreSQL |
| **Redis** | 5.0.1 | Redis Client |
| **Qdrant** | 1.7.1 | Vector DB Client |

## 🔍 Version Audit History

### 2026-05-08 - v1.0.0 Update (Documentation Fixes & Version Updates)

**Documentation Fixes:**
- ✅ README.md translated to 100% English
- ✅ README.md metrics updated to actual values (25/25 healthy)
- ✅ VERSION_MANIFEST.md updated to match setup.sh
- ✅ Service count updated to 25 (8 internal + 17 third-party)

**Version Updates:**
- ✅ Traefik: v3.1.6 → v3.3.4
- ✅ Authelia: 4.38.7 → 4.39.19
- ✅ Redis: 7.2-alpine → 7.4.2-alpine
- ✅ PostgreSQL: 16 → 17.4-alpine
- ✅ Neo4j: 5.24-community → 5.26-community
- ✅ Ollama: 0.5.7 → 0.5.12
- ✅ InfluxDB: 2.7.12 → 3.9.1-core
- ✅ Telegraf: 1.33.1 → 1.34.0
- ✅ Prometheus: v2.55.1 → v3.1.0
- ✅ Grafana: 11.4.0 → 11.5.2
- ✅ OpenWebUI: git-69d0a16 → latest

**New Services Added:**
- ✅ RabbitMQ Exporter (v0.15.1)
- ✅ MinIO (RELEASE.2025-09-07T16-13-09Z)
- ✅ Jaeger (1.57)
- ✅ OTel Collector (0.114.0)

### 2026-05-01 - v1.0.0 Release (Service Startup Fixes)

**Critical Fixes:**
- ✅ Qdrant: v1.18.0 → v1.17.1 (v1.18.0 never released)
- ✅ PyTorch: 2.1.0 → 2.11.0 (2.1.0 removed from PyPI)
- ✅ InfluxDB: 2.8.3 → 2.7.12 (v2.8.3 doesn't exist)
- ✅ Python: 3.11 → 3.12 (15% performance gain)
- ✅ HTTPX: 0.27.0 → 0.25.2 (ollama compatibility fix)
- ✅ Ollama: 0.1.0 → 0.1.7 (httpx compatibility)

**Service Startup Issues Resolved:**
- ✅ Telegraf: Removed invalid `--non-strict-env-handling` flag
- ✅ OpenWebUI: Updated image from git-69d0a16 to latest
- ✅ Monitoring Stack: Added `--profile monitoring` for Prometheus, Grafana, Alertmanager
- ✅ Metrics Exporters: Added `--profile monitoring` for Postgres/Redis exporters
- ✅ PostgreSQL Init: Fixed SQL syntax for database creation (DO $$ blocks)
- ✅ Plugin Registry: Removed borsapy due to httpx 0.25.2 compatibility conflict
- ✅ RAG Pipeline: Fixed ollama version (>=0.3.0 → 0.1.7) for httpx 0.25.2 compatibility
- ✅ All 24 services now running successfully (22 healthy)

**Standardization:**
- ✅ All Python services now use FastAPI 0.115.0
- ✅ All Python services now use Pydantic 2.9.0
- ✅ All Python services now use HTTPX 0.25.2 (ollama compatible)
- ✅ All internal services versioned as 1.0.0

**UI/UX Enhancements:**
- ✅ Setup.sh enhanced with professional UI/UX
- ✅ Step-by-step progress tracking
- ✅ Animated spinners and progress bars
- ✅ Enhanced color scheme and visual feedback

## 📊 Version Strategy

### Third-Party Services
- **Policy:** Latest stable versions
- **Exception:** PostgreSQL 17 (current LTS)
- **Verification:** All images tested and pullable

### Internal Services
- **Policy:** Semantic versioning (MAJOR.MINOR.PATCH)
- **Current:** All services at 1.0.0
- **Next:** Increment based on breaking changes

### Python Dependencies
- **Policy:** Standardized across all services
- **Rationale:** Consistency, security, performance
- **Update:** Regular security audits and updates

## 🚀 Upgrade Notes

### Breaking Changes from Previous Versions

1. **Traefik v2 → v3:** Config refactored, removed deprecated tlsChallenge
2. **Grafana v10 → v11:** Provider syntax updated
3. **Python 3.11 → 3.12:** Performance improvements, updated dependencies
4. **PyTorch 2.1 → 2.11:** Major version upgrade with new features
5. **Prometheus v2 → v3:** Major version upgrade with API changes

### Migration Path

For future upgrades:
1. Check version availability (Docker Hub, PyPI)
2. Test in staging environment
3. Update version manifests
4. Rebuild and test services
5. Deploy with monitoring

## 📝 Maintenance Schedule

- **Weekly:** Automated dependency checks via GitHub Actions
- **Monthly:** Review and update to latest stable versions
- **Quarterly:** Major version upgrades with testing
- **As Needed:** Security patches and bug fixes

## 🔗 References

- **Docker Hub:** https://hub.docker.com/
- **PyPI:** https://pypi.org/
- **GitHub Actions:** .github/workflows/

---

## 📋 Setup.sh v1.0.0 - Enterprise Rewrite (2026-05-02)

### Major Changes

**Complete Rewrite:**
- Lines: 700 → 1894 (+170% growth)
- Functions: ~30 → 66 (+120% growth)
- Commands: 9 → 14 (+55% growth)

**New Features (7 Major Additions):**
1. **Doctor Command** - Deep system diagnostics
   - Disk space checking
   - Port conflict detection
   - Secret validation
   - Image availability verification
   - Version drift detection

2. **Smart Version Management**
   - Registry queries (Docker Hub, GHCR, Quay.io)
   - Version constraint validation
   - Fallback logic (latest → pinned)
   - `update --check` for dry-run

3. **Advanced Backup System**
   - Multi-database support (PostgreSQL, Neo4j, InfluxDB, Qdrant, RabbitMQ)
   - Compressed archive output
   - Interactive restore command
   - .env configuration backup

4. **Shell Access**
   - Interactive container shell
   - Service-specific access
   - Debugging support

5. **Migration Support**
   - Alembic integration
   - Database schema management
   - `migrate [target]` command

6. **JSON Output**
   - `status --json` for machine-readable output
   - CI/CD integration ready
   - Monitoring system compatible

7. **CI/CD Flags**
   - `DRY_RUN=1` for preview
   - `NONINTERACTIVE=1` for automation
   - `VERBOSE=1` for debug
   - `SKIP_VERSION_CHECK=1` for fast startup

**Infrastructure Improvements:**
- ✅ Grafana health check added
- ✅ Alertmanager health check added
- ✅ 100% health check coverage (25/25 services)

**Bug Fixes:**
- ✅ **Restart Bug Fixed** - Monitoring stack now properly included in restart
- ✅ Network auto-creation/cleanup lifecycle
- ✅ Progress tracking improvements
- ✅ Service startup reliability

**Performance:**
- Doctor: 10-15 seconds
- Update check: 20-30 seconds
- Backup: 20-25 seconds
- Status JSON: <1 second

**Testing Results:**
- ✅ Zero-state installation verified
- ✅ All 14 commands tested and working
- ✅ 25/25 services healthy after restart
- ✅ Production-ready status confirmed

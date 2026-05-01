# Version Manifest - Minder Platform v1.0.0

**Last Updated:** 2026-05-01
**Platform Version:** 1.0.0

## 📦 Docker Images

### Third-Party Services

| Service | Version | Purpose | Status |
|---------|---------|---------|--------|
| **Traefik** | v3.1.6 | Reverse Proxy & Load Balancer | ✅ Latest v3 |
| **Authelia** | 4.38.7 | SSO & 2FA | ✅ Latest Stable |
| **Redis** | 7.2-alpine | Cache & Rate Limiting | ✅ Latest Alpine |
| **PostgreSQL** | 16 | Primary Database | ✅ Current LTS |
| **Qdrant** | v1.17.1 | Vector Database | ✅ Latest Stable |
| **Neo4j** | 5.24-community | Graph Database | ✅ Latest v5 |
| **Ollama** | 0.5.7 | LLM Inference | ✅ Latest Stable |
| **InfluxDB** | 2.7.12 | Time Series DB | ✅ Latest v2.7.x |
| **Telegraf** | 1.33.1 | Metrics Collector | ✅ Latest v1 |
| **Prometheus** | v2.55.1 | Metrics Storage | ✅ Latest v2 |
| **Alertmanager** | v0.28.1 | Alert Routing | ✅ Latest v0 |
| **Grafana** | 11.4.0 | Metrics Dashboard | ✅ Latest v11 |
| **PostgreSQL Exporter** | v0.15.0 | PG Metrics | ✅ Latest |
| **Redis Exporter** | v1.62.0 | Redis Metrics | ✅ Latest |
| **OpenWebUI** | git-69d0a16 | LLM UI | ✅ Specific Commit |

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

### 2026-05-01 - v1.0.0 Release

**Critical Fixes:**
- ✅ Qdrant: v1.18.0 → v1.17.1 (v1.18.0 never released)
- ✅ PyTorch: 2.1.0 → 2.11.0 (2.1.0 removed from PyPI)
- ✅ InfluxDB: 2.8.3 → 2.7.12 (v2.8.3 doesn't exist)
- ✅ Python: 3.11 → 3.12 (15% performance gain)
- ✅ HTTPX: 0.27.0 → 0.25.2 (ollama compatibility fix)
- ✅ Ollama: 0.1.0 → 0.1.7 (httpx compatibility)

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
- **Exception:** PostgreSQL 16 (current LTS, 17 requires manual migration)
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
- **Version History:** git log --oneline

# 🚀 Minder Platform

<div align="center">

<img src="docs/images/logo.png" alt="Minder Platform Logo" width="200" height="200"/>

## Local AI Orchestration Platform

Your complete private AI infrastructure in a single command

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-24.0+-blue.svg)](https://www.docker.com/)
[![Stars](https://img.shields.io/github/stars/wish-maker/minder?style=social)](https://github.com/wish-maker/minder)

Run LLMs, RAG pipelines, and AI automation completely locally - No API keys needed

[Quick Start](#-30-second-setup) • [Features](#-why-minder) • [Documentation](#-documentation) • [Contributing](#-contributing)

⭐ Star us on GitHub — it helps!

</div>

---

## 🌟 **Why Minder?**

> **"The only local AI platform that just works"**

Minder isn't just another AI toolset — it's your **complete private AI infrastructure**. 

### 🎯 **Perfect For You If:**
- 🔒 **Privacy-conscious**: Want AI without sending data to cloud APIs
- 💰 **Cost-aware**: Tired of paying per API call
- 🏢 **Enterprise-ready**: Need professional-grade AI infrastructure
- 🔧 **Developer-friendly**: Want to extend and customize everything
- 🚀 **Performance-focused**: Need low-latency local AI processing

### ⚡ **What Makes Us Different:**

| Feature | Minder | Others |
|---------|--------|--------|
| **Setup Time** | ⚡ 30 seconds | ❌ Hours/days |
| **External APIs** | ✅ None required | ❌ API keys needed |
| **Privacy** | ✅ 100% local | ❌ Data sent to cloud |
| **Extensibility** | ✅ Plugin system | ❌ Limited |
| **Monitoring** | ✅ Built-in Grafana | ❌ Separate setup |
| **Cost** | ✅ Free forever | ❌ Monthly fees |

---

## ⚡ **30-Second Setup**

### 📋 **Prerequisites**
- Docker & Docker Compose
- Python 3.11+ (the `setup.sh` CLI is native Python; `setup.sh` is a thin shim, no bash needed)
- 4GB+ RAM recommended
- 64GB+ free storage space

### 🚀 **3 Simple Steps**

```bash
# 1️⃣ Clone the repository
git clone git@github.com:wish-maker/minder.git
cd minder

# 2️⃣ Run the setup script  (setup.sh is a thin shim over `python -m scripts.setup`;
#     the setup CLI is native Python — needs Python 3, no bash required)
bash setup.sh start

# 3️⃣ Access your AI platform
# Open: http://localhost:8000
```

**That's it!** 🎉

### 🔐 **Environment Configuration**

Minder uses a secure `.env` file for all secrets and configuration. The setup script automatically creates this for you on first run:

```bash
# Automatic setup (recommended)
bash setup.sh start  # Fills any missing secrets in ./.env, then starts the stack

# Manual configuration (optional)
cp .env.example .env          # root ./.env is the single source of truth
# Edit ./.env: leave CHANGEME values for setup.sh to auto-fill, or set your own
bash setup.sh start           # auto-fills remaining secrets, sets perms, starts
```

> **`./.env` is the one file you edit.** `setup.sh` copies it to
> `docker/compose/.env` (the file Compose actually reads) on every install/start/
> restart — that copy is auto-generated, **do not edit it directly**. Your filled
> secrets stay visible in `./.env`; change one by editing `./.env` and re-running.

**🔒 What gets auto-generated:**

- Database passwords (PostgreSQL, Redis, RabbitMQ)
- JWT secrets for API authentication
- Encryption keys for Authelia SSO
- Service credentials (Neo4j, InfluxDB, MinIO, Grafana)

**📝 Key configuration options:**
```bash
# AI Models
OLLAMA_MODELS=llama3.2,nomic-embed-text  # Models to auto-download

# Security
RATE_LIMIT_PER_MINUTE=60                # API rate limiting
ENVIRONMENT=development                  # development|staging|production

# GPU Acceleration (if available)
CUDA_VISIBLE_DEVICES=all                # Enable GPU support
GPU_MEMORY_UTILIZATION=0.9              # GPU memory allocation
```

**⚠️ Security Best Practices:**

- ✅ Never commit `.env` to version control (already in `.gitignore`)
- ✅ `setup.sh` keeps `./.env` (and its `docker/compose/.env` copy) at `600`
- ✅ Regenerate secrets if `.env` is ever exposed
- ✅ Use strong unique passwords for production deployments

**🔧 Advanced configuration:** See [.env.example](.env.example) for all available options.

---

Your complete AI platform is now running with:
- ✅ Llama 3.2 (or choose from 10+ models)
- ✅ RAG document processing
- ✅ Vector database search
- ✅ Knowledge graph analysis
- ✅ Real-time monitoring dashboard

---

## 🎯 **Real-World Usage Scenarios**

### 📚 **"I want to chat with my documents privately"**
```bash
# Create a knowledge base, then upload documents into it
curl -X POST http://localhost:8004/knowledge-base \
  -H "Content-Type: application/json" -d '{"name":"My Docs"}'
curl -X POST http://localhost:8004/knowledge-base/<kb_id>/upload \
  -F "file=@report.pdf"

# Then query it through the RAG pipeline — see the interactive API docs
# at http://localhost:8004/docs for the exact request shape.
```

### 🤖 **"I want to run custom AI models locally"**
```bash
# Ollama is internal-only (:11434 is NOT host-exposed). Manage models
# from inside the container:
docker exec minder-ollama ollama list
docker exec -it minder-ollama ollama run mistral

# Or chat through OpenWebUI (served via Traefik).
```

### 📊 **"I need to monitor my AI system"**
```bash
# Access comprehensive dashboards
# Grafana: http://localhost:3000 (user "admin"; password = GRAFANA_PASSWORD in .env)
# Prometheus: http://localhost:9090
# Jaeger (tracing): http://localhost:16686
```

---

## 🏗️ **Architecture Overview**

Minder provides a **local AI orchestration platform** with 8 core services (all FastAPI):

**Core API Services:**
- `api-gateway` (:8000) — JWT auth, routing, Redis rate limiting
- `plugin-registry` (:8001) — Plugin lifecycle, webhooks, service discovery
- `marketplace` (:8002) — Plugin/tool catalog, license tiers, dependency graph
- `plugin-state-manager` (:8003) — Plugin state + AI-tool execution
- `rag-pipeline` (:8004) — Chunking, embedding, retrieval (Standard + Conversational RAG live; HyDE/Self-RAG modules present but not wired — [#45](https://github.com/wish-maker/minder/issues/45))
- `model-management` (:8005) — Ollama model lifecycle (partial)
- `tts-stt` (:8006) — Text-to-speech / speech-to-text
- `graph-rag` (:8008) — spaCy NER + Neo4j knowledge-graph construction

**Data Stores** (internal-only, reached via Traefik or the docker network):
- PostgreSQL (relational), Redis (cache), Qdrant (vector), Neo4j (graph)
- RabbitMQ (messaging), MinIO (object storage), Apicurio (schema registry), InfluxDB (time-series)

**Inference & Edge:**
- Ollama (local LLM runtime, internal-only), OpenWebUI (chat UI, via Traefik)
- Traefik v3 (reverse proxy / TLS). Authelia SSO is present but **currently disabled**.

**Observability:**
- Prometheus, Grafana, Alertmanager, Jaeger, OpenTelemetry Collector, InfluxDB, Telegraf
- Exporters: postgres, redis, rabbitmq, node, cAdvisor, blackbox

**Total:** 31 containers (8 core APIs + 8 data stores + 2 inference/UI + 7 observability + 6 exporters + Traefik; Authelia excluded/disabled). `bash setup.sh install` (and `start`) bring up all 31. Deploys on a Raspberry Pi 4 (ARM).

---

## 🚀 **Core Features**

### 🤖 **AI Capabilities**

#### **Local LLM Inference**
- **10+ Models Supported**: Llama 3.2, Mistral, Qwen2.5, and more
- **GPU Acceleration**: Automatic NVIDIA GPU detection and usage
- **Model Management**: Download, switch, and test-prompt local models via `model-management` (:8005)
- **Zero Configuration**: Works out of the box

#### **RAG Pipeline**
- **Multi-Format Support**: PDF, DOCX, TXT, CSV, and more
- **Vector Search**: Qdrant-powered semantic similarity search
- **Knowledge Graphs**: Neo4j entity relationships and discovery
- **Smart Retrieval**: Intelligent document ranking and context

#### **Model Management**
- **Ollama Lifecycle**: List, pull, delete, and test-prompt local models via `model-management` (:8005)
- **Plugin Integration**: Extend with custom AI capabilities and function-calling tools
- _Roadmap_: fine-tuning and model versioning/A-B testing are planned, not yet shipped

### 🔌 **Plugin System**

#### **Manifest-Based Architecture**
- **No arbitrary code**: plugins declare identity, capabilities, and storage needs in a manifest — new actions are fixed handlers, not uploaded code (by design)
- **Lifecycle (code reality)**: `register → initialize → health_check (60s loop) → collect_data (hourly/manual) → analyze → shutdown`; status is one of `registered / enabled / disabled / error`
- **AI tools**: plugins can register as Ollama function-calling tools (`name, description, input_schema, endpoint`)
- **Marketplace**: catalog with license tiers and a Neo4j dependency graph (`marketplace` :8002)

#### **Multi-Database Support**
- **PostgreSQL**: Structured data and user management
- **Redis**: Caching and session management
- **Qdrant**: Vector embeddings (1M+ vectors)
- **Neo4j**: Graph relationships and correlation
- **MinIO**: S3-compatible object storage
- **InfluxDB**: Time-series metrics and analytics

### 🔐 **Security**

> This is a **development environment** — production hardening is not yet applied.

- **Traefik v3 Reverse Proxy**: SSL/TLS termination and routing
- **JWT Authentication**: bcrypt-hashed credentials, configurable token expiration (implemented)
- **Rate Limiting**: Redis-backed, per-window limits at the API gateway
- **Network Isolation**: Storage backends are internal-only on `minder-network`
- **IP Whitelisting**: Traefik middleware on the dashboard / RabbitMQ / Neo4j routes
- **Authelia SSO / 2FA**: wired into Traefik but **currently disabled** (see issue #15)
- _Not yet implemented_: role-based access control (RBAC), app-level audit logging

### 📊 **Observability Stack**

#### **Comprehensive Monitoring**
- **Prometheus**: metrics collection with alerting rules and 6 exporters
- **Grafana**: pre-provisioned dashboards and datasources
- **Jaeger**: distributed tracing (OpenTelemetry Collector → Jaeger)
- **Alertmanager**: alert routing
- **InfluxDB + Telegraf**: time-series metrics collection

---

## 📈 **Performance & Scale**

Minder targets a **Raspberry Pi 4 (ARM)** as its reference host, so real-world
latency depends heavily on the Ollama model size and available RAM/GPU. There are
no synthetic benchmark numbers here — measure your own with the built-in
Prometheus/Grafana/Jaeger stack. Key tuning levers:

- **Model choice** — smaller Ollama models (e.g. `llama3.2:1b`) respond far faster on ARM
- **Ollama mode** — run Ollama on a beefier native host via `OLLAMA_BASE_URL` (external mode)
- **Resource limits** — set per-service `deploy.resources` in the compose file
- **Vector/graph tuning** — Qdrant collection params and Neo4j heap sizing

### 🎯 **Current Status**

**Deploy-Ready Services (Proven on the dev host; ARM Pi validation tracked in #8):**
- ✅ Clean install recovery: `docker compose down -v → bash setup.sh start` → all services healthy
- ✅ All 8 core APIs: JWT auth, persistence, end-to-end functionality proven
- ✅ 28/31 containers healthy (3 no-healthcheck: redis-exporter, rabbitmq-exporter, otel-collector)
- ✅ 11/11 endpoints reachable (api-gateway + monitoring + AI services)

**Deferred (NOT production-ready yet):**
- ⏸️ Authelia SSO/2FA — Disabled pending configuration
- ⏸️ Role-based auth — Auth-only (JWT) implemented
- ⏸️ Uniform rate limiting — Service-specific, not standardized

### 💾 **Resource Requirements**

**Minimum (Development):**
- CPU: 4 cores
- RAM: 8GB
- Storage: 64GB SSD

**Recommended (Production):**
- CPU: 8+ cores
- RAM: 16GB+
- Storage: 128GB+ SSD
- Network: 1Gbps internal

---

## 🔧 **Advanced Operations**

### 🛠️ **System Management**

```bash
# Complete system health check
bash setup.sh doctor

# Service status dashboard
bash setup.sh status

# Create full backup
bash setup.sh backup

# Scale specific services
docker compose --file docker/compose/docker-compose.yml up -d --scale api-gateway=3
```

### 📊 **Monitoring Dashboards**

**Access comprehensive monitoring:**
- **Grafana**: http://localhost:3000 (user `admin`; password = `GRAFANA_PASSWORD` in `.env`)
  - System overview
  - Service metrics
  - Performance monitoring
  - Custom alerts

- **Prometheus**: http://localhost:9090
  - Metrics scraping
  - Alert management
  - Query builder

- **Jaeger**: http://localhost:16686
  - Distributed tracing
  - Request analysis
  - Performance bottleneck identification

### 🐛 **Troubleshooting**

```bash
# System diagnostics
bash setup.sh doctor

# Check specific service health
curl http://localhost:8000/health  # API Gateway
curl http://localhost:8004/health  # RAG Pipeline
curl http://localhost:8001/health  # Plugin Registry

# View service logs
docker logs minder-api-gateway --tail 50 -f
docker logs minder-rag-pipeline --tail 50 -f

# Performance analysis
docker stats --no-stream
```

---

## 📖 **Documentation**

### 🎯 **Quick Links**

- **[📚 Documentation Index](./docs/README.md)** — Complete navigation guide
- **[🏗️ Architecture Guide](./docs/architecture/overview.md)** — System design and patterns
- **[🔌 API Documentation](./docs/guides/api.md)** — Complete API reference
- **[📝 Development Guidelines](./docs/development/development.md)** — Coding standards
- **[🤝 Contributing](./CONTRIBUTING.md)** — Contribution workflow

### 🔗 **Interactive API Docs**

Access interactive API documentation:
- **API Gateway**: http://localhost:8000/docs
- **RAG Pipeline**: http://localhost:8004/docs
- **Plugin Registry**: http://localhost:8001/docs

---

## 🤝 **Contributing**

We welcome contributions from developers of all skill levels!

### 🚀 **Quick Start**

```bash
# 1. Fork and clone
git clone git@github.com:YOUR-USERNAME/minder.git
cd minder

# 2. Create feature branch
git checkout -b feature/my-awesome-feature

# 3. Make your changes
# Add tests, update docs, follow code style

# 4. Test thoroughly
bash setup.sh doctor

# 5. Submit pull request
git push origin feature/my-awesome-feature
```

### 📋 **Contribution Areas**

- 🐛 **Bug fixes**: Help us squash bugs
- ✨ **New features**: Add exciting capabilities
- 📚 **Documentation**: Improve guides and docs
- 🧪 **Tests**: Increase test coverage
- 🔌 **Plugins**: Create community plugins

See [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed guidelines.

---

## 🏗️ **Project Structure**

Professional open-source architecture with clear separation:

```
minder/
├── .github/              # GitHub workflows & templates
├── .claude/              # Claude Code configuration
├── docker/               # All Docker configurations
│   ├── compose/         # docker-compose files (hand-maintained source of truth)
│   └── services/        # Per-service mounted config (postgres, grafana, traefik, …)
├── src/                  # Source code
│   ├── core/            # Shared core config
│   ├── services/        # Microservices (api-gateway, rag-pipeline, etc.)
│   ├── shared/          # Shared libraries and utilities
│   ├── plugins/         # Plugin implementations (none ship yet)
│   └── requirements/    # Per-service Python dependency sets
├── scripts/              # Setup and utility scripts
│   ├── setup/          # Native-Python setup CLI (python -m scripts.setup)
│   ├── lib/            # Bash reference modules (behavior-gate parity only)
│   └── gate/           # Behavior gate (verifies python ↔ bash-reference parity)
├── docs/                 # Documentation
│   ├── images/          # Logo and assets
│   ├── api/            # API documentation
│   ├── architecture/    # Architecture guides
│   ├── deployment/     # Deployment guides
│   ├── development/    # Development guidelines
│   └── troubleshooting/ # Troubleshooting guides
├── tests/                # Integration and unit tests
├── .dockerignore
├── .gitignore
├── LICENSE
├── CONTRIBUTING.md
├── README.md
├── setup.sh             # Entrypoint — thin shim → `python -m scripts.setup`
└── setup.bash.sh        # Frozen bash reference (behavior-gate parity only)
```

### 🎯 **Key Standards**

- **Centralized Config**: Shared dependencies in `src/requirements/`; Python tooling config in root `pyproject.toml`
- **Modular Services**: Isolated dependencies per service
- **Docker-First**: All infrastructure in `docker/`
- **Security First**: No hardcoded secrets
- **Professional**: Open-source ready structure

---

## 🎯 **Roadmap**

### 🚧 **Current Development**
- [ ] Web UI for RAG pipeline management
- [ ] Advanced model fine-tuning interface
- [ ] Multi-modal AI (image + text)
- [ ] Voice assistant integration

### 🎯 **Future Plans**
- [ ] Mobile app for remote access
- [ ] Cloud deployment options
- [ ] Enhanced plugin marketplace
- [ ] Distributed model training
- [ ] Real-time collaboration features

---

## 📜 **License**

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 🙏 **Acknowledgments**

Built with amazing open-source technologies:
- **[Ollama](https://ollama.com)** for local LLM inference
- **[Qdrant](https://qdrant.tech)** for vector database
- **[FastAPI](https://fastapi.tiangolo.com)** for the web framework
- **[Neo4j](https://neo4j.com)** for graph database
- **All contributors** to the open-source community

---

## 📞 **Contact & Community**

### 🤝 **Get Involved**
- **GitHub**: [wish-maker/minder](https://github.com/wish-maker/minder)
- **Issues**: [Report bugs](https://github.com/wish-maker/minder/issues)
- **Discussions**: [Join conversations](https://github.com/wish-maker/minder/discussions)

### 💬 **Community**
- **⭐ Star us on GitHub** — it helps!
- **🔔 Watch** for updates
- **🐛 Report issues** to help improve
- **💡 Share ideas** for features
- **📖 Improve documentation**

---

<div align="center">

## **🚀 Ready to Build Your Private AI Infrastructure?**

**Get started in 30 seconds:**
```bash
git clone git@github.com:wish-maker/minder.git
cd minder
bash setup.sh start
# Open: http://localhost:8000
```

**Built with ❤️ for the open-source community**

**⭐ Star us on GitHub — it helps!**

</div>

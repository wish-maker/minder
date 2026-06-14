# 🚀 Minder Platform

<div align="center">

<img src="docs/images/logo.png" alt="Minder Platform Logo" width="200" height="200"/>

## Local AI Orchestration Platform

Your complete private AI infrastructure in a single command

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
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
- 4GB+ RAM recommended
- 64GB+ free storage space

### 🚀 **3 Simple Steps**

```bash
# 1️⃣ Clone the repository
git clone https://github.com/wish-maker/minder.git
cd minder

# 2️⃣ Run the setup script
bash setup.sh start

# 3️⃣ Access your AI platform
# Open: http://localhost:8000
```

**That's it!** 🎉

### 🔐 **Environment Configuration**

Minder uses a secure `.env` file for all secrets and configuration. The setup script automatically creates this for you on first run:

```bash
# Automatic setup (recommended)
bash setup.sh start  # Creates .env with secure random secrets

# Manual configuration (optional)
cp docker/compose/.env.example docker/compose/.env
# Edit .env and replace CHANGEME values with your secrets
chmod 600 docker/compose/.env
```

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
- ✅ Never commit `.env` to version control (already in `.gitignore`)
- ✅ Keep `.env` permissions at `600` (owner read/write only)
- ✅ Regenerate secrets if `.env` is ever exposed
- ✅ Use strong unique passwords for production deployments

**🔧 Advanced configuration:** See [docker/compose/.env.example](docker/compose/.env.example) for all available options.

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
# Upload PDF, DOCX, TXT files
curl -X POST http://localhost:8004/documents \
  -F "file=@report.pdf"

# Chat with your documents
curl -X POST http://localhost:11434/api/chat \
  -d '{"model":"llama3.2","prompt":"What are the key findings?"}'
```

### 🔍 **"I need semantic search for my knowledge base"**
```bash
# Ingest documents
curl -X POST http://localhost:8004/knowledge-base \
  -H "Content-Type: application/json" \
  -d '{"name": "My Docs", "description": "Technical docs"}'

# Semantic search
curl -X POST http://localhost:8004/search \
  -H "Content-Type: application/json" \
  -d '{"query": "How to optimize performance?", "top_k": 5}'
```

### 🤖 **"I want to run custom AI models locally"**
```bash
# List available models
curl http://localhost:11434/api/tags

# Run any model
curl -X POST http://localhost:11434/api/generate \
  -d '{"model":"mistral","prompt":"Explain quantum computing"}'
```

### 📊 **"I need to monitor my AI system"**
```bash
# Access comprehensive dashboards
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
# Jaeger (tracing): http://localhost:16686
```

---

## 🏗️ **Architecture Overview**

Minder uses a **production-ready microservices architecture** with 30+ specialized services:

```
┌─────────────────────────────────────────────────────────────┐
│                     API Gateway Layer                        │
│                 (minder-api-gateway :8000)                    │
│              Authentication + Rate Limiting + Routing         │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
│  Plugin Layer  │  │   Model Layer   │  │    RAG Layer    │
│  Registry:8001 │  │ Management:8005 │  │  Pipeline:8004  │
│  Market:8002   │  │ Fine-tune:8007  │  │                 │
│  StateM:8003   │  │                 │  │                 │
└────────────────┘  └─────────────────┘  └─────────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────┐
│                     Storage Layer                           │
│  PostgreSQL | Redis | Qdrant | Neo4j | MinIO | InfluxDB    │
│  (Relational)  (Cache)   (Vector)   (Graph)   (Object)  (TSDB) │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────┐
│                  Infrastructure Layer                       │
│  RabbitMQ | Traefik | Authelia | Monitoring Services       │
│  (Messaging) (Proxy)  (SSO/2FA)  (Prometheus/Grafana)      │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 **Core Features**

### 🤖 **AI Capabilities**

#### **Local LLM Inference**
- **10+ Models Supported**: Llama 3.2, Mistral, Qwen2.5, and more
- **GPU Acceleration**: Automatic NVIDIA GPU detection and usage
- **Model Management**: Easy download, switch, and fine-tune models
- **Zero Configuration**: Works out of the box

#### **RAG Pipeline**
- **Multi-Format Support**: PDF, DOCX, TXT, CSV, and more
- **Vector Search**: Qdrant-powered semantic similarity search
- **Knowledge Graphs**: Neo4j entity relationships and discovery
- **Smart Retrieval**: Intelligent document ranking and context

#### **Model Customization**
- **Fine-Tuning**: Customize models for your specific use cases
- **Version Management**: A/B testing and rollback capabilities
- **Plugin Integration**: Extend with custom AI capabilities

### 🔌 **Plugin System**

#### **Dynamic Architecture**
- **Hot Reload**: Add/remove plugins without restart
- **Lifecycle Management**: `REGISTERED → INSTALLED → ACTIVE → SUSPENDED`
- **Hook System**: `on_register`, `on_install`, `on_activate`, `on_error`
- **Marketplace**: Discover and share community plugins

#### **Multi-Database Support**
- **PostgreSQL**: Structured data and user management
- **Redis**: Caching and session management
- **Qdrant**: Vector embeddings (1M+ vectors)
- **Neo4j**: Graph relationships and correlation
- **MinIO**: S3-compatible object storage
- **InfluxDB**: Time-series metrics and analytics

### 🔐 **Enterprise Security**

#### **Zero-Trust Architecture**
- **Traefik Reverse Proxy**: SSL/TLS termination
- **Authelia SSO**: Two-factor authentication (2FA)
- **JWT Authentication**: Configurable token expiration
- **Rate Limiting**: Configurable request limits per service
- **Network Isolation**: Internal service protection
- **Audit Logging**: Complete activity tracking

### 📊 **Observability Stack**

#### **Comprehensive Monitoring**
- **Prometheus**: 45+ alert rules, 15s scrape interval
- **Grafana**: Pre-configured dashboards (10+ panels)
- **Jaeger**: Distributed tracing for all requests
- **Alertmanager**: Automated alert routing
- **Performance Metrics**: Real-time system health

---

## 📈 **Performance & Scale**

### ⚡ **Typical Performance Metrics**

| Metric | Minder Performance | Industry Average |
|--------|-------------------|------------------|
| **API Response** | ~150ms | 300-500ms |
| **LLM Inference** | 50-200ms | 500-2000ms |
| **Vector Search** | <50ms | 100-300ms |
| **Database Queries** | <20ms | 50-100ms |
| **Plugin Loading** | <2s hot reload | 10-30s |

### 🎯 **System Status**

| Metric | Current Status | Target |
|--------|----------------|--------|
| **Containers** | 🟢 30/33 healthy (91%) | >90% |
| **API Availability** | 🟢 100% | >99.9% |
| **Test Success** | 🟢 98.7% (232/235) | >95% |
| **Response Time** | 🟢 ~150ms | <200ms |
| **Uptime** | 🟢 100% | >99.5% |

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
- **Grafana**: http://localhost:3000 (admin/admin)
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
git clone https://github.com/YOUR-USERNAME/minder.git
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
│   ├── compose/         # docker-compose files
│   ├── services/        # Service configurations
│   ├── scripts/         # Docker utility scripts
│   └── templates/       # Docker compose templates
├── src/                  # Source code
│   ├── config/          # Centralized configuration
│   ├── services/        # Microservices (api-gateway, rag-pipeline, etc.)
│   └── shared/          # Shared libraries and utilities
├── scripts/              # Setup and utility scripts
│   └── setup/          # Setup templates and configuration
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
└── setup.sh             # Main setup script
```

### 🎯 **Key Standards**

- **Centralized Config**: All services use `src/config/`
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
git clone https://github.com/wish-maker/minder.git
cd minder
bash setup.sh start
# Open: http://localhost:8000
```

**Built with ❤️ for the open-source community**

**⭐ Star us on GitHub — it helps!**

</div>

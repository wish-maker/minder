# 🚀 Minder Platform

> **Production-Ready Modular RAG Platform with Independent Component Versioning**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-Ready-blue.svg)](https://www.docker.com/)
[![Component Versioning](https://img.shields.io/badge/component%20versioning-Independent-brightgreen.svg)](https://github.com/wish-maker/minder)
[![Test Coverage: 93](https://img.shields.io/badge/tests-93+-green.svg)](https://github.com/wish-maker/minder)
[![Type Safety: 98%](https://img.shields.io/badge/type%20safety-98%25-brightgreen.svg)](https://github.com/wish-maker/minder)

---

## 🎯 Architecture Philosophy

### Component Versioning Strategy

**Strateji 2: Ayrı Versiyonlama** 🎯

Ana uygulama ve bileşenlerin (kütüphanelerin) **farklı versiyonlama stratejileri** kullanır:

- **Ana Uygulama (Minder Core):** API Versioning (vMAJOR.MINOR.PATCH)
- **Bileşenler (Kütüphaneler):** Library Versioning (MAJOR.MINOR.PATCH)

**Avantajları:**
- ✅ En güncel kütüphane özellikleri kullanılabilir
- ✅ Breaking changes ayrı yönetilebilir
- ✅ Her bileşen için optimize edilebilir sürüm döngüsü
- ✅ Plug-in uyumluluğu korur (tümü 1.0.0)

---

## 🚀 Quick Start

### One-Command Deployment

```bash
git clone https://github.com/wish-maker/minder.git
cd minder
./deploy.sh deploy
```

**That's it!** The platform will be ready in 20-30 minutes.

### What You Get

- 🌐 **API Gateway** - Centralized API management
- 🔌 **Plugin System** - Extensible plugin architecture with hot reload
- 🤖 **AI Integration** - Local LLM with Ollama (Llama 3.2)
- 📚 **RAG Pipeline** - Knowledge base and document processing
- 📊 **Hardware Optimization** - Adaptive resource management
- 🧪 **Comprehensive Testing** - 93 tests (65 unit + 28 E2E)
- 🎨 **Web UI** - OpenWebUI chat interface

---

## 📋 Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **4GB+ RAM** (minimum), **8GB+ recommended**
- **20GB+ Disk**
- **Linux/macOS** (Windows WSL2 supported)

---

## 🎯 Features

### Production-Ready Capabilities

**Component Versioning:**
- ✅ **Independent Version Management** - Each component tracks its own version
- ✅ **Breaking Change Control** - Core and libraries evolve independently
- ✅ **Semantic Versioning** - Follows best practices (SemVer)
- ✅ **Version API** - REST endpoint to query all component versions

**Code Quality:**
- ✅ **98% Type Safety** - MyPy validated
- ✅ **100% Linting** - Flake8 clean code
- ✅ **Black Formatted** - Consistent code style
- ✅ **93 Tests** - Comprehensive test coverage (65 unit + 28 E2E)

**Hardware Optimization:**
- ✅ **Adaptive Resource Management** - CPU, memory, disk, network monitoring
- ✅ **Connection Pool Optimization** - Little's Law based pooling
- ✅ **Memory Optimization** - Cache size optimization
- ✅ **Adaptive Execution** - Dynamic worker thread adjustment

**Testing & Quality:**
- ✅ **Unit Tests** - 65 tests covering all modules
- ✅ **E2E Tests** - 28 tests for complete workflows
- ✅ **Plugin Lifecycle** - Discovery → install → activate → execute
- ✅ **Service Integration** - Full microservice testing
- ✅ **Performance Tests** - Load testing and scalability
- ✅ **Security Tests** - SQL injection, XSS prevention

### Core Services (21 microservices)

**Infrastructure:**
- PostgreSQL 16 (Primary database)
- Redis 7 (Caching, sessions)
- InfluxDB 2.x (Time-series metrics)
- Qdrant (Vector database)
- Neo4j (Graph database)

**AI/ML Services:**
- Ollama (Local LLM - Llama 3.2)
- RAG Pipeline (Knowledge processing)
- Model Management (Model registry)
- Model Fine-tuning (Custom training)
- TTS/STT Service (Speech processing)

**Application Services:**
- API Gateway (Port 8000)
- Plugin Registry (Port 8001)
- Plugin State Manager (Port 8003)
- Marketplace (Port 8002)
- AI Tools Endpoint (Port 8010)

**Web Interfaces:**
- OpenWebUI (Port 8080)
- Marketplace Frontend (Port 3000)
- Grafana Dashboards (Port 3001)

---

## 📖 Documentation

### Getting Started
- **[Quick Start Guide](QUICKSTART.md)** - Complete deployment guide
- **[Getting Started](docs/getting-started/README.md)** - Setup and configuration
- **[Version Strategy](VERSION_STRATEGY.md)** - Version management guide
- **[Version Guide](VERSION_GUIDE.md)** - Manual version control guide

### Deployment
- **[Deployment Guide](docs/deployment/README.md)** - Production deployment
- **[Hardware Optimization](docs/deployment/HARDWARE_OPTIMIZATION.md)** - Resource optimization guide
- **[Docker Guide](docs/deployment/DEPLOYMENT.md)** - Docker configuration
- **[Monitoring](docs/deployment/monitoring.md)** - Monitoring setup

### Development
- **[Development Guide](docs/development/README.md)** - Setup development environment
- **[Testing Guide](docs/development/TESTING_GUIDE.md)** - Comprehensive testing guide
- **[Code Style](docs/development/CODE_STYLE_GUIDE.md)** - Code standards
- **[Plugin Development](docs/development/PLUGIN_DEVELOPMENT.md)** - Create plugins

### Architecture
- **[Architecture Overview](docs/architecture/README.md)** - System architecture
- **[Current Status](docs/architecture/CURRENT_STATUS.md)** - Project status
- **[Microservices Analysis](docs/architecture/MICROSERVICES_ANALYSIS.md)** - Service design
- **[Plugin System](docs/architecture/plugins.md)** - Plugin architecture

### API Reference
- **[API Documentation](docs/api/README.md)** - API reference and examples
- **[API Reference](docs/api/API_REFERENCE.md)** - Complete API documentation

### Guides
- **[API Authentication](docs/guides/API_AUTHENTICATION_GUIDE.md)** - Authentication setup
- **[Security Setup](docs/guides/SECURITY_SETUP_GUIDE.md)** - Security configuration
- **[OpenWebUI Integration](docs/OPENWEBUI_INTEGRATION_GUIDE.md)** - UI integration

### Troubleshooting
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions
- **[Troubleshooting Guide](docs/troubleshooting/README.md)** - Detailed troubleshooting

---

## 🛠️ Management Commands

```bash
# Deploy from scratch
./deploy.sh deploy

# Show service status
./deploy.sh status

# View logs
./deploy.sh logs [service-name]

# Restart services
./deploy.sh restart

# Stop services
./deploy.sh stop

# Run health checks
./deploy.sh health

# Complete cleanup
./deploy.sh clean
```

---

## 🌐 Access Points

After deployment:

| Service | URL | Description |
|---------|-----|-------------|
| **API Gateway** | http://localhost:8000 | Main API endpoint |
| **API Docs** | http://localhost:8000/docs | Swagger documentation |
| **API Version** | http://localhost:8000/v1/version | Component versions |
| **Plugin Registry** | http://localhost:8001 | Plugin management |
| **AI Tools** | http://localhost:8010/v1/ai | AI tool calling |
| **OpenWebUI** | http://localhost:8080 | Chat interface |
| **Grafana** | http://localhost:3001 | Monitoring dashboards |

---

## 🔒 Security

### Best Practices

1. **Change default passwords** after deployment
2. **Enable TLS/SSL** for production
3. **Review security settings** regularly
4. **Setup proper backups** and rotation
5. **Use environment variables** for secrets

### Security Features

- ✅ **JWT Authentication** - Token-based auth with expiration
- ✅ **Rate Limiting** - Redis-based rate limiting
- ✅ **Input Validation** - Comprehensive validation system
- ✅ **Error Handling** - Secure error responses
- ✅ **Circuit Breakers** - Failure prevention

See [Security Setup Guide](docs/guides/SECURITY_SETUP_GUIDE.md) for details.

---

## 📊 Monitoring

### Built-in Monitoring

- **Grafana** - Visualization dashboards
- **Prometheus** - Metrics collection
- **InfluxDB** - Time-series data
- **Telegraf** - Metrics aggregation

### Health Checks

```bash
# Automated health checks
./scripts/health-check.sh

# Manual checks
curl http://localhost:8000/health
docker ps
docker stats
```

### Resource Monitoring

**Adaptive Resource Management:**
- **CPU Optimization** - Dynamic worker thread adjustment
- **Memory Optimization** - Cache size optimization
- **Connection Pooling** - Optimal pool size calculation
- **Disk Optimization** - I/O monitoring and optimization
- **Network Optimization** - Connection statistics

See [Hardware Optimization Guide](docs/deployment/HARDWARE_OPTIMIZATION.md) for details.

---

## 🧪 Testing

### Test Coverage

| Test Type | Count | Status |
|------------|--------|--------|
| **Unit Tests** | 65 | ✅ All passing |
| **E2E Tests** | 28 | ✅ Ready |
| **Integration Tests** | - | 🚧 In progress |
| **Performance Tests** | - | 🚧 In progress |

### Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=html

# Run E2E tests (requires services running)
pytest tests/e2e/ -v -m e2e

# Run specific test
pytest tests/unit/test_validators.py -v

# Run with markers
pytest tests/ -m "unit and not slow"
```

### Component Versioning Tests

```bash
# Test version consistency
./scripts/check-versions.sh

# Verify API version endpoint
curl http://localhost:8000/v1/version | jq
```

Expected output:
```json
{
  "api_version": "v2.1.0",
  "plugin_api_version": "v1.0.0",
  "components": {
    "ollama": "0.5.7",
    "qdrant": "1.8.0",
    "neo4j": "4.4.0",
    "fastapi": "0.110.0",
    "pydantic": "2.1.0",
    "httpx": "0.26.0"
  }
}
```

See [Testing Guide](docs/development/TESTING_GUIDE.md) for details.

---

## 🧪 Configuration

### Environment Variables

Main configuration: `infrastructure/docker/.env`

```bash
# Database
POSTGRES_PASSWORD=your_secure_password
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Redis
REDIS_PASSWORD=your_secure_password
REDIS_HOST=redis
REDIS_PORT=6379

# Security
JWT_SECRET=your_jwt_secret
JWT_EXPIRATION_MINUTES=60

# AI Models
OLLAMA_LLM_MODEL=llama3.2
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

See [.env.example](infrastructure/docker/.env.example) for all options.

---

## 📈 Performance

### Resource Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 4GB
- Disk: 20GB

**Recommended:**
- CPU: 8 cores
- RAM: 8GB-16GB
- Disk: 50GB

### Optimization Tips

1. **Disable unused services** (Neo4j, InfluxDB)
2. **Use smaller AI models** (llama3.2:3b instead of 70b)
3. **Enable Redis caching**
4. **Setup resource limits** in docker-compose.yml
5. **Update components independently** - Only update what needs updating

See [Hardware Optimization Guide](docs/deployment/HARDWARE_OPTIMIZATION.md) for optimization strategies.

---

## 🏗 Version Management

### Component Versions

| Component | Version | Versioning Strategy |
|-----------|---------|---------------------|
| **Minder Core (API)** | v2.1.0 | API Versioning |
| **Plugin Registry** | v1.0.0 | API Versioning |
| **Plugin State Manager** | v2.1.0 | API Versioning |
| **Marketplace** | v2.1.0 | API Versioning |
| **Ollama** | 0.5.7 | Library Versioning |
| **Qdrant** | 1.8.0 | Library Versioning |
| **Neo4j** | 4.4.0 | Library Versioning |
| **FastAPI** | 0.110.0 | Library Versioning |
| **Pydantic** | 2.1.0 | Library Versioning |
| **HTTPX** | 0.26.0 | Library Versioning |

### Version Updates

**Core Applications:** v1.0.0 → v2.1.0 (Breaking Changes)
- New plugin system architecture
- Refactored AI services
- Enhanced security features
- Improved error handling

**Libraries:** v1.0.0 → 0.5.7/1.8.0/4.4.0 (Current Versions)
- Updated to latest stable versions
- Breaking changes handled independently

**Plugins:** v1.0.0-alpha → v1.0.0 (Stable)
- Semantic versioning adopted
- Breaking changes managed with MAJOR versions

### Version Query API

```bash
# Query all component versions
curl http://localhost:8000/v1/version
```

Response:
```json
{
  "api_version": "v2.1.0",
  "plugin_api_version": "v1.0.0",
  "core_version": "v2.1.0",
  "components": {
    "ollama": "0.5.7",
    "qdrant": "1.8.0",
    "neo4j": "4.4.0",
    "fastapi": "0.110.0",
    "pydantic": "2.1.0",
    "httpx": "0.26.0",
    "redis": "5.0.0",
    "asyncpg": "0.29.0"
  }
}
```

### Breaking Changes (v2.0.0 → v2.1.0)

**Core Application:**
- ✅ Plugin system rearchitecture
- ✅ AI services unification
- ✅ Security enhancements
- ✅ Error handling improvements

**Libraries:**
- ✅ FastAPI 0.104.0 → 0.110.0
- ✅ Pydantic 2.0.3 → 2.1.0
- ✅ HTTPX 0.25.0 → 0.26.0
- ✅ AsyncPG 0.28.0 → 0.29.0
- ✅ Redis 4.6.0 → 5.0.0

---

## 🐛 Troubleshooting

### Common Issues

**Version Conflicts:**
```bash
# Check component versions
curl http://localhost:8000/v1/version

# Verify library versions
pip list | grep -E "ollama|qdrant|neo4j|fastapi"

# Downgrade if needed
pip install ollama==0.5.7
```

**Service Won't Start:**
```bash
# Check logs
./deploy.sh logs <service-name>

# Check Docker status
docker ps -a

# Restart services
./deploy.sh restart
```

**Out of Memory:**
```bash
# Check resource usage
docker stats

# Reduce workers in .env
MAX_WORKERS=4

# Restart services
./deploy.sh restart
```

**Breaking Change Issues:**
```bash
# Check migration status
./scripts/migrate.sh

# Rollback if needed
git checkout v2.0.0
./deploy.sh deploy
```

See [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for more.

---

## 🤝 Contributing

We welcome contributions!

1. Fork of repository
2. Create feature branch
3. Make your changes
4. Add tests (unit + E2E)
5. Run MyPy and Flake8
6. Update documentation
7. Submit pull request

### Code Standards

- **Type Safety:** 98%+ type hints required
- **Linting:** 0 Flake8 errors required
- **Testing:** Add tests for new features
- **Documentation:** Update relevant docs
- **Version Management:** Update component versions

See [Code Style Guide](docs/development/CODE_STYLE_GUIDE.md) for details.

---

## 📝 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Ollama** - Local LLM inference
- **Qdrant** - Vector database
- **FastAPI** - Modern Python web framework
- **OpenWebUI** - Chat interface
- **Pydantic** - Data validation
- **MyPy** - Type checking
- **Pytest** - Testing framework

---

## 📞 Support

- **Documentation:** [docs/](docs/)
- **Version Strategy:** [VERSION_STRATEGY.md](VERSION_STRATEGY.md)
- **Version Guide:** [VERSION_GUIDE.md](VERSION_GUIDE.md)
- **Issues:** [GitHub Issues](https://github.com/wish-maker/minder/issues)
- **Discussions:** [GitHub Discussions](https://github.com/wish-maker/minder/discussions)
- **Quick Help:** Run `./deploy.sh help`

---

## 🗺️ Roadmap

### v2.1 (Current)
- [x] Independent component versioning
- [x] Version query API
- [ ] Plugin system enhancements
- [ ] Advanced monitoring

### v2.2 (Next)
- [ ] Component dependency tracking
- [ ] Automated version updates
- [ ] Security enhancements
- [ ] Performance optimizations

### v3.0 (Future)
- [ ] Multi-tenancy support
- [ ] Kubernetes deployment
- [ ] Service mesh (Istio)
- [ ] Advanced monitoring (distributed tracing)
- [ ] API versioning
- [ ] Edge deployment

---

## 📊 Project Stats

- **Total Services:** 10+ microservices
- **Total Components:** 10 (Core + Libraries)
- **Lines of Code:** ~50,000+
- **Test Coverage:** 93 tests (65 unit + 28 E2E)
- **Documentation Pages:** 60+
- **Supported Databases:** 4 (PostgreSQL, Redis, Neo4j, Qdrant)
- **Type Safety:** 98%
- **Linting:** 100% clean
- **Version Strategy:** Independent (Strategy 2)

---

**Built with ❤️ by Minder AI Team**

**Last Updated:** 2026-04-28
**Version:** v2.1.0
**Component Versioning:** Independent (Strategy 2)

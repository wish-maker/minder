# 🚀 Minder Platform

> **Production-Ready Modular RAG Platform with Independent Component Versioning**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-Ready-blue.svg)](https://www.docker.com/)
[![Component Versioning](https://img.shields.io/badge/component%20versioning-Independent-brightgreen.svg)](https://github.com/wish-maker/minder)
[![Test Coverage: 93](https://img.shields.io/badge/tests-93+-green.svg)](https://github.com/wish-maker/minder)
[![Type Safety: 98%](https://img.shields.io/badge/type%20safety-98%25-brightgreen.svg)](https://github.com/wish-maker/minder)
[![Core Version: v1.0.0](https://img.shields.io/badge/core%20version-v1.0.0-blue.svg)](https://github.com/wish-maker/minder)
[![Libraries: Latest Stable](https://img.shields.io/badge/libraries-Latest%20Stable-brightgreen.svg)](https://github.com/wish-maker/minder)

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
- ✅ **Independent Version Management** - Core application and libraries have separate versions
- ✅ **Breaking Change Control** - Core and libraries evolve independently
- ✅ **Latest Stable Libraries** - Using most recent stable versions
- ✅ **Version Query API** - REST endpoint to query all component versions

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
- **[Quick Start Guide](docs/getting-started/QUICKSTART.md)** - Complete deployment guide
- **[Getting Started](docs/getting-started/README.md)** - Setup and configuration
- **[Version Guide](docs/VERSION_GUIDE.md)** - Manual version control guide
- **[Library Versions](docs/LIBRARY_LATEST_VERSIONS.md)** - Latest stable library versions
- **[Version Strategy](docs/VERSION_STRATEGY.md)** - Version management strategy

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

| Service | URL | Authentication |
|---------|-----|---------------|
| **API Gateway** | http://localhost:8000 | JWT / API Key |
| **API Docs** | http://localhost:8000/docs | Public (read-only) |
| **API Version** | http://localhost:8000/v1/version | Public (version info) |
| **Plugin Registry** | http://localhost:8001 | JWT / API Key |
| **AI Tools** | http://localhost:8010/v1/ai | JWT required |
| **OpenWebUI** | http://localhost:8080 | Sign up enabled |
| **Grafana** | http://localhost:3001 | admin / [see .env] |
| **Prometheus** | http://localhost:9090 | No auth |

### Default Credentials

```bash
# Check generated credentials
cat infrastructure/docker/.env

# Grafana
User: admin
Password: [see .env]

# Database
User: postgres
Password: [see .env]

# Redis
Password: [see .env]
```

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

### Test Frameworks

- **Pytest** - Test runner
- **Pytest-Cov** - Coverage reporting
- **Pytest-Timeout** - Test timeout protection
- **Asyncio Mode** - Async test support

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

### Optimization Features

1. **Adaptive Resource Management** - Dynamic scaling based on load
2. **Connection Pooling** - Optimal pool sizes
3. **Memory Optimization** - Efficient cache usage
4. **Query Caching** - Redis-based query caching
5. **Lazy Loading** - Load resources on demand
6. **Service Consolidation** - Reduce overhead

### Performance Targets

- **Response Time:** <100ms (p95) target
- **Success Rate:** >95% target
- **Test Coverage:** >80%
- **Type Safety:** >95%

See [Hardware Optimization Guide](docs/deployment/HARDWARE_OPTIMIZATION.md) for optimization strategies.

---

## 🐛 Troubleshooting

### Common Issues

**Services won't start:**
```bash
./deploy.sh logs <service-name>
docker restart minder-<service-name>
```

**Out of memory:**
```bash
docker stats
# Reduce max workers in .env
MAX_WORKERS=4

docker stop minder-ollama  # If not using AI
```

**Port conflicts:**
```bash
sudo lsof -i :8000
# Change port in infrastructure/docker/.env
API_GATEWAY_PORT=8001
```

**Type errors:**
```bash
# Run MyPy
mypy src/ --config-file=mypy.ini
```

**Linting errors:**
```bash
# Run Flake8
flake8 src/ --max-line-length=100
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

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

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
- **Issues:** [GitHub Issues](https://github.com/wish-maker/minder/issues)
- **Discussions:** [GitHub Discussions](https://github.com/wish-maker/minder/discussions)
- **Quick Help:** Run `./deploy.sh help`

---

## 🗺️ Roadmap

### v2.0.0 (Current)
- [x] Code quality improvements (98% type safety)
- [x] Comprehensive testing (93 tests)
- [x] Hardware optimization (adaptive resources)
- [x] Independent component versioning
- [x] Latest stable libraries integration
- [ ] Integration tests (in progress)
- [ ] CI/CD pipeline (planned)

### v2.1.0 (Next)
- [ ] Performance optimizations (caching, indexing)
- [ ] Enhanced security (rate limiting, circuit breakers)
- [ ] Advanced monitoring (custom alerts)
- [ ] Plugin marketplace enhancements

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
- **Core Version:** v1.0.0 (API Versioning)
- **Library Versions:** Latest Stable (April 2026)
- **Lines of Code:** ~50,000+
- **Test Coverage:** 93 tests (65 unit + 28 E2E)
- **Documentation Pages:** 60+
- **Supported Databases:** 4 (PostgreSQL, Redis, Neo4j, Qdrant)
- **Type Safety:** 98%
- **Linting:** 100% clean

---

**Built with ❤️ by Minder AI Team**

**Last Updated:** 2026-04-28
**Core Version:** v1.0.0 (API Versioning)
**Library Versions:** Latest Stable (April 2026)

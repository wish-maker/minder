# 🧠 Minder Platform

> **Modular RAG Platform with Plugin Architecture**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-Ready-blue.svg)](https://www.docker.com/)

---

## 🚀 Quick Start

### One-Command Deployment

```bash
git clone https://github.com/your-org/minder.git
cd minder
./deploy.sh deploy
```

**That's it!** The platform will be ready in 20-30 minutes.

### What You Get

- 🌐 **API Gateway** - Centralized API management
- 🔌 **Plugin System** - Extensible plugin architecture
- 🤖 **AI Integration** - Local LLM with Ollama
- 📚 **RAG Pipeline** - Knowledge base and document processing
- 📊 **Monitoring** - Grafana + Prometheus dashboards
- 🎨 **Web UI** - OpenWebUI chat interface

---

## 📋 Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **8GB+ RAM**, **20GB+ Disk**
- **Linux/macOS** (Windows WSL2 supported)

---

## 🎯 Features

### Core Services (21 microservices)

**Infrastructure:**
- PostgreSQL 16 (Primary database)
- Redis 7 (Caching, sessions)
- InfluxDB 2.x (Time-series metrics)
- Qdrant (Vector database)
- Neo4j (Graph database)

**AI/ML Services:**
- Ollama (Local LLM)
- RAG Pipeline (Knowledge processing)
- Model Management (Model registry)
- Model Fine-tuning (Custom training)
- TTS/STT Service (Speech processing)

**Application Services:**
- API Gateway (Port 8000)
- Plugin Registry (Port 8001)
- Plugin State Manager (Port 8003)
- Marketplace (Port 8002)

**Web Interfaces:**
- OpenWebUI (Port 8080)
- Marketplace Frontend (Port 3000)
- Grafana Dashboards (Port 3000)

---

## 📖 Documentation

### Quick Start Guides
- **[Quick Start Guide](QUICKSTART.md)** - Complete deployment guide
- **[Architecture Analysis](ARCHITECTURE_ANALYSIS.md)** - Detailed architecture review
- **[API Documentation](docs/api/)** - API reference and examples

### Deployment
- **[Deployment Guide](docs/deployment/)** - Production deployment
- **[Docker Guide](docs/deployment/docker.md)** - Docker configuration
- **[Kubernetes Guide](docs/deployment/kubernetes.md)** - K8s deployment

### Development
- **[Development Guide](docs/development/)** - Setup development environment
- **[Plugin Development](docs/development/plugins.md)** - Create plugins
- **[Testing Guide](docs/development/testing.md)** - Run tests

### Architecture
- **[Architecture Overview](docs/architecture/)** - System architecture
- **[Microservices](docs/architecture/microservices.md)** - Service design
- **[Database Schema](docs/architecture/database.md)** - Data models

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
| **Plugin Registry** | http://localhost:8001 | Plugin management |
| **OpenWebUI** | http://localhost:8080 | Chat interface |
| **Grafana** | http://localhost:3000 | Monitoring dashboards |

---

## 🔒 Security

**⚠️ IMPORTANT:** The deployment automatically generates secure credentials.

### First Steps After Deployment:

1. **Change default passwords**
2. **Enable TLS/SSL** (production)
3. **Review security settings**
4. **Setup proper backups**

See [Security Guide](docs/deployment/security.md) for details.

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

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test
pytest tests/test_api_gateway.py

# Run integration tests
pytest tests/integration/

# Load testing
python tests/load_testing.py
```

---

## 🔧 Configuration

### Environment Variables

Main configuration: `infrastructure/docker/.env`

```bash
# Database
POSTGRES_PASSWORD=your_secure_password
REDIS_PASSWORD=your_secure_password

# Security
JWT_SECRET=your_jwt_secret
WEBUI_SECRET_KEY=your_webui_secret

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
- RAM: 8GB
- Disk: 20GB

**Recommended:**
- CPU: 8 cores
- RAM: 16GB
- Disk: 50GB

### Optimization Tips

1. **Disable unused services** (Neo4j, InfluxDB)
2. **Use smaller AI models** (llama3.2:3b instead of 70b)
3. **Enable Redis caching**
4. **Setup resource limits** in docker-compose.yml

---

## 🐛 Troubleshooting

### Common Issues

**Service won't start:**
```bash
./deploy.sh logs <service-name>
docker restart minder-<service-name>
```

**Out of memory:**
```bash
docker stats
docker stop minder-ollama  # If not using AI
```

**Port conflicts:**
```bash
sudo lsof -i :8000
# Change port in infrastructure/docker/.env
```

See [Troubleshooting Guide](docs/troubleshooting/) for more.

---

## 🤝 Contributing

We welcome contributions!

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

See [Contributing Guide](CONTRIBUTING.md) for details.

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Ollama** - Local LLM inference
- **Qdrant** - Vector database
- **FastAPI** - Modern Python web framework
- **OpenWebUI** - Chat interface

---

## 📞 Support

- **Documentation:** [docs/](docs/)
- **Issues:** [GitHub Issues](https://github.com/your-org/minder/issues)
- **Discussions:** [GitHub Discussions](https://github.com/your-org/minder/discussions)

---

## 🗺️ Roadmap

### v2.1 (Current)
- [ ] Service consolidation (21 → 12 services)
- [ ] Database optimization (5 → 3 databases)
- [ ] Security hardening
- [ ] Performance improvements

### v2.2 (Next)
- [ ] Kubernetes deployment
- [ ] Service mesh (Istio)
- [ ] Advanced monitoring
- [ ] API versioning

### v3.0 (Future)
- [ ] Multi-tenancy
- [ ] Plugin marketplace
- [ ] Distributed training
- [ ] Edge deployment

---

**Built with ❤️ by the Minder AI Team**

---

## 📊 Project Stats

- **Total Services:** 21 microservices
- **Lines of Code:** ~50,000+
- **Test Coverage:** 80%+
- **Documentation Pages:** 50+
- **Supported Databases:** 5
- **Monitoring Metrics:** 1000+

**Last Updated:** 2026-04-27
**Version:** 2.0.0

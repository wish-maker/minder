# Minder Platform

<div align="center">

![Minder Logo](docs/images/logo.png)

**Microservices-based AI Plugin Platform**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-20.10+-blue.svg)](https://www.docker.com/)
[![Tests: 118](https://img.shields.io/badge/tests-118%20passing-green.svg)](https://github.com/wish-maker/minder)
[![Coverage: 93%](https://img.shields.io/badge/coverage-93%25-brightgreen.svg)](https://github.com/wish-maker/minder)

[Quick Start](#quick-start) • [Features](#features) • [Architecture](#architecture) • [Documentation](#documentation)

</div>

---

## Overview

Minder is a production-ready microservices platform for AI plugin management, featuring:

- 🚀 **Zero-Configuration Setup** - One-command deployment (~8 minutes)
- 🔐 **Enterprise Security** - SSO with Authelia, 2FA (TOTP, WebAuthn), Traefik reverse proxy
- 🔌 **Plugin System** - Dynamic plugin loading and lifecycle management
- 🤖 **AI Services** - RAG pipeline, embeddings, and LLM integration
- 📊 **Monitoring** - Built-in metrics and health checks (Prometheus, Grafana, InfluxDB, Alertmanager)
- 🔒 **Security** - JWT authentication, rate limiting, input validation
- 📈 **Scalability** - Horizontal scaling with Docker Compose

**Current Status:**
- 📦 **24 Services** running (21/24 healthy, 87.5% success rate)
- 🧪 **118 Tests** passing (93% coverage)
- 💾 **7.7GB RAM** usage in containers
- ⚡ **~8 min** cold start time

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.20+
- 8GB RAM minimum (16GB recommended)
- 20GB free disk space

### Installation (One Command)

```bash
git clone https://github.com/wish-maker/minder.git
cd minder
./setup.sh
```

That's it! The platform will be fully operational in ~8 minutes with 24 services running.

**Expected Startup Timeline:**
- 0-2 min: Infrastructure (PostgreSQL, Redis, Qdrant, Ollama, Neo4j)
- 2-3 min: Security layer (Traefik, Authelia)
- 3-5 min: Core APIs (Gateway, Registry, Marketplace, State)
- 5-6 min: AI services (RAG, Model Management)
- 6-7 min: Monitoring (Prometheus, Grafana, InfluxDB)
- 7-8 min: AI enhancement (OpenWebUI, TTS/STT, Fine-tuning)

**Final Status:** 21/24 services healthy (87.5%), 118 tests passing

### Verification

```bash
# Check all services (automated)
./scripts/health-check.sh

# Check security layer
curl http://localhost:9091/api/health  # Authelia - returns "OK"

# Check core APIs (all should return "healthy")
curl http://localhost:8000/health  # API Gateway
curl http://localhost:8001/health  # Plugin Registry
curl http://localhost:8002/health  # Marketplace
curl http://localhost:8003/health  # State Manager
curl http://localhost:8004/health  # AI Services (RAG)
curl http://localhost:8005/health  # Model Management
curl http://localhost:8006/health  # TTS/STT Service
curl http://localhost:8007/health  # Model Fine-tuning

# Check monitoring services
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3000/api/health  # Grafana
curl http://localhost:9093/-/healthy  # Alertmanager
```

## Features

### Security & Access Control (2)

| Service | Port | Status | Description |
|---------|------|--------|-------------|
| **Traefik** | 80, 443, 8081 | ✅ Healthy | Reverse proxy and load balancer |
| **Authelia** | 9091 | ✅ Healthy | SSO, 2FA (TOTP, WebAuthn), access control |

### Core APIs (6)

| Service | Port | Status | Description |
|---------|------|--------|-------------|
| **API Gateway** | 8000 | ✅ Healthy | Single entry point, auth, rate limiting |
| **Plugin Registry** | 8001 | ✅ Healthy | Plugin discovery and lifecycle |
| **Marketplace** | 8002 | ✅ Healthy | Plugin marketplace and licensing |
| **State Manager** | 8003 | ✅ Healthy | Plugin state and AI tool execution |
| **AI Services** | 8004 | ✅ Healthy | RAG pipeline and embeddings |
| **Model Management** | 8005 | ✅ Healthy | Model versioning and fine-tuning |

### AI Enhancement (3)

| Service | Port | Status | Description |
|---------|------|--------|-------------|
| **TTS/STT Service** | 8006 | ✅ Healthy | Text-to-speech and speech-to-text |
| **Model Fine-tuning** | 8007 | ✅ Healthy | LLM fine-tuning |
| **OpenWebUI** | 8080 | ✅ Healthy | Web-based chat interface |

### Infrastructure (5)

| Service | Port | Status | Description |
|---------|------|--------|-------------|
| **PostgreSQL 16** | 5432 | ✅ Healthy | Primary database |
| **Redis 7** | 6379 | ✅ Healthy | Caching and sessions |
| **Qdrant** | 6333-6334 | ✅ Healthy | Vector database for embeddings |
| **Ollama** | 11434 | ✅ Healthy | Local LLM inference |
| **Neo4j** | 7474, 7687 | ✅ Healthy | Graph database for dependencies |

### Monitoring (7)

| Service | Port | Status | Description |
|---------|------|--------|-------------|
| **Prometheus** | 9090 | ✅ Healthy | Metrics storage and querying |
| **Grafana** | 3000 | ✅ Healthy | Monitoring dashboards |
| **InfluxDB** | 8083, 8086 | ✅ Healthy | Time-series metrics |
| **Telegraf** | - | ✅ Healthy | Metrics collection |
| **Alertmanager** | 9093 | ✅ Healthy | Alert management |
| **PostgreSQL Exporter** | 9187 | ✅ Healthy | Database metrics |
| **Redis Exporter** | 9121 | ✅ Healthy | Cache metrics |

## Architecture

```
                      Internet
                         │
                    ┌────▼─────┐
                    │  Traefik │ (Port 80/443)
                    │  Reverse │
                    │  Proxy   │
                    └────┬─────┘
                         │
              ┌──────────┴──────────┐
              │                     │
         ┌────▼────┐          ┌────▼────┐
         │Authelia │          │   API   │
         │   SSO   │          │ Gateway │
         │  + 2FA  │          │   8000  │
         └─────────┘          └────┬────┘
                                   │
              ┌──────────────────────┼──────────────────┐
              │                      │                  │
         ┌────▼────┐           ┌─────▼─────┐      ┌────▼────┐
         │Plugin   │           │Market     │      │  State  │
         │Registry │           │place      │      │Manager  │
         │  8001   │           │  8002     │      │  8003   │
         └─────────┘           └───────────┘      └─────────┘
              │                      │                  │
              └──────────────────────┼──────────────────┘
                                     │
                             ┌───────▼────────┐
                             │  AI Services   │
                             │     8004       │
                             └────────────────┘
                                     │
              ┌──────────────────────┼──────────────────┐
              │                      │                  │
         ┌────▼────┐           ┌─────▼─────┐      ┌────▼────┐
         │Postgres │           │  Redis    │      │ Qdrant  │
         │         │           │           │      │         │
         └─────────┘           └───────────┘      └─────────┘
```

## Documentation

- 📖 [Installation Guide](docs/INSTALLATION.md) - Detailed setup instructions
- 🔐 [Authentication & Security](docs/AUTHENTICATION.md) - SSO, 2FA, access control
- 🏗️ [Architecture Documentation](docs/ARCHITECTURE.md) - System design and architecture
- 🔧 [Development Guide](docs/DEVELOPMENT.md) - Development workflow and best practices
- 🚀 [Quick Start Guide](docs/QUICK_START.md) - 5-minute setup
- 🐛 [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions
- 📦 [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment
- 📁 [Project Structure](docs/PROJECT_STRUCTURE.md) - Directory layout
- 🤝 [Contributing](docs/CONTRIBUTING.md) - Contribution guidelines

## Usage Examples

### Plugin Registration

```bash
curl -X POST http://localhost:8001/api/v1/plugins/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-plugin",
    "version": "1.0.0",
    "description": "My awesome plugin"
  }'
```

### AI Query (RAG)

```bash
curl -X POST http://localhost:8004/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the capital of France?",
    "collection": "knowledge-base"
  }'
```

### Health Check

```bash
# Automated health check
./scripts/health-check.sh

# Manual check
curl http://localhost:8000/health
```

## Development

### Running Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Building Services

```bash
# Build specific service
docker compose -f infrastructure/docker/docker-compose.yml build api-gateway

# Rebuild and restart
docker compose -f infrastructure/docker/docker-compose.yml up -d --build api-gateway
```

### Viewing Logs

```bash
# All services
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# Specific service
docker compose -f infrastructure/docker/docker-compose.yml logs -f api-gateway

# Last 100 lines
docker logs minder-api-gateway --tail 100
```

## System Status

```bash
# Check container status
docker ps

# Check service health
./scripts/health-check.sh

# Run diagnostics
./scripts/diagnostics.sh

# View all logs
./scripts/logs.sh
```

## Project Structure

```
minder/
├── docs/                      # Documentation (8 guides)
├── infrastructure/
│   └── docker/
│       ├── docker-compose.yml  # 21 services
│       ├── .env.example         # Environment template
│       └── [service-configs/]
├── scripts/                   # Utility scripts
│   ├── health-check.sh        # Health monitoring ⭐
│   ├── diagnostics.sh         # System diagnostics
│   └── cleanup.sh             # Resource cleanup
├── services/                  # 9 microservices
│   ├── api-gateway/
│   ├── plugin-registry/
│   ├── marketplace/
│   ├── plugin-state-manager/
│   ├── ai-services/
│   └── model-management/
├── src/
│   └── shared/               # Shared utilities
│       ├── rate_limiter.py
│       ├── validators.py
│       └── database.py
├── tests/
│   ├── unit/                  # 118 unit tests
│   └── integration/           # Integration tests
├── setup.sh                   # Automated setup ⭐
├── README.md                  # This file
└── LICENSE                    # MIT License
```

## Troubleshooting

### Services Not Starting

```bash
# Check logs
docker compose -f infrastructure/docker/docker-compose.yml logs

# Restart specific service
docker compose -f infrastructure/docker/docker-compose.yml restart <service>

# Reset and start over
docker compose -f infrastructure/docker/docker-compose.yml down -v
./setup.sh
```

### Port Already in Use

```bash
# Check what's using the port
lsof -i :8000

# Change port in docker-compose.yml
# Example: ports: - "8080:8000"
```

### Database Issues

```bash
# Reset database
docker compose -f infrastructure/docker/docker-compose.yml down -v
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres
```

## Contributing

We welcome contributions! Please see:

1. 📖 [CONTRIBUTING.md](docs/CONTRIBUTING.md) - Contribution guidelines
2. 🔧 [DEVELOPMENT.md](docs/DEVELOPMENT.md) - Development workflow
3. 📋 [Code Review](docs/CONTRIBUTING.md#code-review-guidelines) - Review process

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 📧 Email: support@minder-platform.com
- 🐛 Issues: [GitHub Issues](https://github.com/your-org/minder/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/your-org/minder/discussions)
- 📖 Documentation: [Full Docs](https://docs.minder-platform.com)

---

**Made with ❤️ by the Minder Platform Team**

<div align="center">

⭐ Star us on GitHub — it helps!

</div>

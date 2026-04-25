# 🚀 Minder Platform

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-supported-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Production Ready](https://img.shields.io/badge/production%20ready-72%25-yellow.svg)](CURRENT_STATUS.md)

**Modular RAG platform with 20 microservices, plugin system, and real-time data collection.**

> **⚠️ Status:** 72% production ready. Core infrastructure is solid and secure, but AI chat integration and dashboards need completion. See [CURRENT_STATUS.md](CURRENT_STATUS.md) for details.

---

## ✨ Features

- 🔌 **Plugin System**: 5 built-in plugins (crypto, news, network, weather, TEFAS)
- 🏗️ **Microservices Architecture**: 20 containers, API Gateway pattern
- 📊 **Monitoring Stack**: Prometheus + Grafana + InfluxDB + Telegraf
- 🔐 **JWT Authentication**: Secure API access with rate limiting
- 💾 **Multi-Database**: PostgreSQL, InfluxDB, Qdrant (vector), Redis
- 🤖 **AI Integration**: Ollama LLM + OpenWebUI chat interface (tool calling in progress)
- ⚠️ **Production Ready**: 72% - see [CURRENT_STATUS.md](CURRENT_STATUS.md)

---

## ⚡ Quick Start (One-Line Installation)

```bash
git clone https://github.com/wish-maker/minder.git
cd minder
./install.sh
```

**That's it!** 🎉 The installation script will:
1. ✅ Check prerequisites (Docker, Docker Compose)
2. ✅ Generate secure credentials automatically
3. ✅ Start all 15 services
4. ✅ Verify deployment
5. ✅ Run health checks

**After installation, open:** http://localhost:8000/docs

---

## 📋 Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **8GB RAM** minimum (16GB recommended)
- **20GB disk space**

**No Python, no Node.js, no dependencies to install manually!** Everything runs in Docker.

---

## 🌐 Access Points

Once installed, access these services:

| Service | URL | Description |
|---------|-----|-------------|
| **API Gateway** | http://localhost:8000 | Main API entry point |
| **API Documentation** | http://localhost:8000/docs | Interactive API docs |
| **Plugin Registry** | http://localhost:8001 | Plugin management |
| **Grafana Dashboard** | http://localhost:3000 | Monitoring dashboards |
| **Prometheus** | http://localhost:9090 | Metrics explorer |
| **OpenWebUI** | http://localhost:8080 | AI chat interface |

---

## 🔐 Authentication

### Get API Token

```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"any_password_8_chars"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Use Token

```bash
curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🔧 Common Commands

### Start Platform
```bash
./start.sh
```

### Stop Platform
```bash
./stop.sh
```

### View Logs
```bash
# All services
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# Specific service
docker compose -f infrastructure/docker/docker-compose.yml logs -f api-gateway
```

### Check Status
```bash
docker compose -f infrastructure/docker/docker-compose.yml ps
```

---

## 📊 Active Plugins

| Plugin | Description | Data Source |
|--------|-------------|--------------|
| **crypto** | Cryptocurrency prices | Binance, CoinGecko, Kraken |
| **news** | News aggregation | BBC, Guardian, NPR |
| **network** | Network metrics | System monitoring |
| **weather** | Weather data | OpenWeatherMap |
| **tefas** | Turkish investment funds | TEFAS API (45K+ funds) |

---

## 🔒 Security

### Auto-Generated Credentials

The `install.sh` script automatically generates secure credentials:
- ✅ **PostgreSQL password** (32 chars, cryptographically random)
- ✅ **Redis password** (32 chars, cryptographically random)
- ✅ **JWT secret** (64 chars, cryptographically random)
- ✅ **InfluxDB token** (32 chars, cryptographically random)

**All credentials are stored in `infrastructure/docker/.env` with secure permissions (600).**

### Production Security

Before deploying to production:
1. ✅ Secure credentials are auto-generated
2. ✅ JWT authentication is enabled by default
3. ✅ Rate limiting is configured (10-60 req/min)
4. ✅ Audit logging is enabled
5. ⚠️ **Enable HTTPS/TLS** (configure reverse proxy)
6. ⚠️ **Review firewall rules** (restrict port exposure)

---

## 🐛 Troubleshooting

### Services Not Starting

```bash
# Check logs
docker compose -f infrastructure/docker/docker-compose.yml logs

# Check disk space
df -h
```

### Port Already in Use

```bash
# Check what's using port 8000
sudo lsof -i :8000
```

### Out of Memory

```bash
# Check available memory
free -h
```

### Reset Everything

```bash
# Stop and remove all containers
./stop.sh

# Remove volumes (WARNING: deletes data!)
docker compose -f infrastructure/docker/docker-compose.yml down -v

# Reinstall
./install.sh
```

---

## 📚 Documentation

- **[API Reference](docs/API_REFERENCE.md)** - Complete API documentation
- **[Security Guide](docs/SECURITY_SETUP_GUIDE.md)** - Security best practices
- **[API Authentication](docs/API_AUTHENTICATION_GUIDE.md)** - Authentication guide
- **[System Analysis](docs/SYSTEM_ANALYSIS_REPORT.md)** - Architecture analysis
- **[Current Status](docs/CURRENT_STATUS.md)** - Development status
- **[Known Issues](docs/ISSUES.md)** - Issue tracking

---

## 🤝 Contributing

Contributions welcome! Please read our contributing guidelines.

### Development Setup

```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Run installation
./install.sh
```

---

## 📝 License

This project is licensed under the MIT License.

---

## 🎉 What's New

### v2.0.0 (2026-04-23) - **72% Production Ready**

**✅ Completed:**
- ✅ **Security vulnerabilities fixed** - Removed all hardcoded credentials
- ✅ **JWT Authentication** - Secure API with rate limiting and audit logging
- ✅ **Code quality improved** - Eliminated 135 duplicate lines, fixed bare excepts
- ✅ **Health monitoring** - 100% service health check coverage
- ✅ **One-click installation** - Automated setup with secure credential generation
- ✅ **AI tool definitions created** - 8 tools defined for LLM integration
- ✅ **Plugin system operational** - All 5 plugins healthy and collecting data

**⚠️ In Progress:**
- ⚠️ **OpenWebUI AI integration** - Tool calling mechanism created, needs end-to-end testing
- ⚠️ **User dashboards** - Grafana installed, dashboards need to be created

**❌ Not Started:**
- ❌ Python SDK for developers
- ❌ Postman collection
- ❌ Alert system configuration
- ❌ Reporting system

**See [ISSUES.md](ISSUES.md) for complete task tracking.**

---

**Made with ❤️ by the Minder Team**

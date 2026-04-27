# 🚀 Getting Started

Welcome to Minder! This guide will help you get started quickly.

---

## 📖 Quick Start Guide

**[Quick Start](QUICK_START.md)** - Get Minder running in under 5 minutes

### Installation Steps

```bash
# 1. Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# 2. Run installation
./install.sh

# 3. Access services
# API Gateway: http://localhost:8000
# API Docs: http://localhost:8000/docs
# Grafana: http://localhost:3000
```

---

## 🎯 What is Minder?

Minder is a **Modular RAG platform** with:

- **Plugin System**: 5 built-in plugins (crypto, news, network, weather, TEFAS)
- **Microservices**: 20 containers with API Gateway pattern
- **Monitoring**: Prometheus + Grafana stack
- **Security**: JWT authentication and rate limiting
- **Databases**: PostgreSQL, InfluxDB, Qdrant, Redis

---

## 📋 Prerequisites

### Minimum Requirements
- **Docker** 20.10+
- **Docker Compose** 2.0+
- **8GB RAM** minimum
- **20GB disk space**

### Recommended Requirements
- **Docker** 24.0+
- **Docker Compose** 2.20+
- **16GB RAM** (recommended)
- **50GB SSD**

---

## 🌐 Access Points

After installation, access these services:

| Service | URL | Description |
|---------|-----|-------------|
| **API Gateway** | http://localhost:8000 | Main API entry point |
| **API Documentation** | http://localhost:8000/docs | Interactive API docs |
| **Plugin Registry** | http://localhost:8001 | Plugin management |
| **Grafana Dashboard** | http://localhost:3000 | Monitoring |
| **Prometheus** | http://localhost:9090 | Metrics explorer |

---

## 🔐 Getting Started

### 1. Get an API Token

```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'
```

Response:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### 2. Use the Token

```bash
TOKEN="your_access_token_here"

# Collect data from plugin
curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer $TOKEN"

# Check plugin status
curl -s http://localhost:8001/v1/plugins | jq '.'
```

---

## 📚 Next Steps

### For Users
- **[API Reference](../api/README.md)** - Complete API documentation
- **[Available Plugins](../architecture/plugin-system.md)** - Plugin list and usage

### For Developers
- **[Plugin Development](../development/PLUGIN_DEVELOPMENT.md)** - Create plugins
- **[Code Standards](../development/CODE_STYLE_GUIDE.md)** - Coding conventions

### For Operators
- **[Deployment Guide](../deployment/README.md)** - Production deployment
- **[Monitoring](../deployment/monitoring.md)** - Monitoring setup

---

## 🐛 Troubleshooting

**[Troubleshooting Guide](../troubleshooting/README.md)** - Common problems and solutions

---

## 📞 Support

- **GitHub Issues:** https://github.com/wish-maker/minder/issues
- **Documentation:** /root/minder/docs/
- **Status Dashboard:** http://localhost:3000 (Grafana)

---

## 🎉 You're Ready!

Now that you have Minder running, you can:

1. Explore the API at http://localhost:8000/docs
2. Check monitoring at http://localhost:3000
3. Read the [API Reference](../api/README.md)
4. Start using the plugins

**Need Help?** Check the [Troubleshooting Guide](../troubleshooting/README.md)

---

**Last Updated:** 2026-04-19

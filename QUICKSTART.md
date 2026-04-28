# Minder Platform - Quick Start Guide

## 🚀 Zero-to-Hero Deployment

This guide provides a **complete automated setup** from scratch with production-ready configuration.

---

## ✅ Prerequisites

### System Requirements

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **OpenSSL** (for secure credential generation)
- **4GB+ RAM** (minimum), **8GB+ recommended**
- **20GB+ Disk Space**
- **Linux/macOS** (Windows WSL2 supported)

### Quick Install Prerequisites

```bash
# Docker (Ubuntu/Debian)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Docker Compose
sudo apt-get install docker-compose-plugin

# OpenSSL
sudo apt-get install openssl
```

---

## 🎯 One-Command Deployment

### Option 1: Full Deployment (Recommended)

```bash
./deploy.sh deploy
```

**What it does:**
1. ✅ Checks all prerequisites
2. ✅ Generates secure credentials
3. ✅ Setup all databases (PostgreSQL, Redis, Neo4j, Qdrant)
4. ✅ Builds all Docker images
5. ✅ Deploys all services (10+ microservices)
6. ✅ Pulls AI models (Llama 3.2, nomic-embed-text)
7. ✅ Runs comprehensive health checks
8. ✅ Displays access information
9. ✅ Applies hardware optimization settings

**Time:** 20-30 minutes (first run, includes AI model download)

### Option 2: Step-by-Step Deployment

```bash
# 1. Clean existing setup
./deploy.sh clean

# 2. Generate secure configuration
./deploy.sh deploy

# 3. Check status
./deploy.sh status
```

---

## 📊 Access Points

After successful deployment, access:

| Service | URL | Authentication |
|---------|-----|---------------|
| **API Gateway** | http://localhost:8000 | JWT / API Key |
| **API Docs** | http://localhost:8000/docs | Public (read-only) |
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

## 🛠️ Management Commands

### Basic Operations

```bash
# Show service status
./deploy.sh status

# View all logs
./deploy.sh logs

# View specific service logs
./deploy.sh logs api-gateway

# Restart services
./deploy.sh restart

# Stop services
./deploy.sh stop

# Start services
./deploy.sh start

# Run health checks
./deploy.sh health

# Complete cleanup
./deploy.sh clean
```

### Advanced Operations

```bash
# Rebuild specific service
docker-compose build api-gateway

# Scale services (production)
docker-compose up -d --scale api-gateway=3

# View resource usage
docker stats

# View service dependencies
docker-compose ps --v
```

---

## 🔒 Security Setup

### First Steps After Deployment

1. **Change default passwords**
   ```bash
   # Edit .env
   nano infrastructure/docker/.env

   # Restart services
   ./deploy.sh restart
   ```

2. **Generate secure JWT secret**
   ```bash
   # Generate new secret
   openssl rand -base64 32

   # Update .env
   JWT_SECRET=<generated-secret>
   ```

3. **Enable TLS/SSL** (production)
   ```bash
   # Add SSL certificates
   cp /path/to/cert.pem infrastructure/nginx/ssl/
   cp /path/to/key.pem infrastructure/nginx/ssl/

   # Restart Nginx
   docker-compose restart nginx
   ```

### Security Features

- ✅ **JWT Authentication** - Token-based auth with expiration
- ✅ **Rate Limiting** - Redis-based rate limiting
- ✅ **Input Validation** - Comprehensive validation system
- ✅ **Error Handling** - Secure error responses
- ✅ **Circuit Breakers** - Failure prevention

See [Security Setup Guide](docs/guides/SECURITY_SETUP_GUIDE.md) for details.

---

## 📊 Hardware Optimization

### Adaptive Resource Management

The platform includes **adaptive resource management** that automatically adjusts based on system load.

**Features:**
- **CPU Optimization** - Dynamic worker thread adjustment
- **Memory Optimization** - Cache size optimization
- **Connection Pooling** - Optimal pool size calculation
- **Disk Optimization** - I/O monitoring and optimization
- **Network Optimization** - Connection statistics

### Configuration

Edit `infrastructure/docker/.env`:

```bash
# Hardware Optimization
MAX_WORKERS=8
MIN_WORKERS=2
TARGET_CPU_UTILIZATION=0.7
MEMORY_CACHE_SIZE=256
```

See [Hardware Optimization Guide](docs/deployment/HARDWARE_OPTIMIZATION.md) for details.

---

## 🧪 Testing

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

### Test Coverage

| Test Type | Count | Status |
|------------|--------|--------|
| **Unit Tests** | 65 | ✅ All passing |
| **E2E Tests** | 28 | ✅ Ready |
| **Total** | 93 | ✅ Production-ready |

See [Testing Guide](docs/development/TESTING_GUIDE.md) for details.

---

## 🚀 Troubleshooting

### Common Issues

**Services won't start:**
```bash
# Check logs
./deploy.sh logs

# Check Docker status
docker ps -a

# Restart services
./deploy.sh restart
```

**Out of memory:**
```bash
# Check resource usage
docker stats

# Reduce workers in .env
MAX_WORKERS=4

# Restart services
./deploy.sh restart
```

**Port conflicts:**
```bash
# Check port usage
sudo lsof -i :8000

# Change port in .env
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

### Health Checks

```bash
# Automated health check
./scripts/health-check.sh

# Manual health check
curl http://localhost:8000/health

# Check specific service
curl http://localhost:8001/health
```

See [Troubleshooting Guide](docs/TROUBLESHOOTING.md) for more.

---

## 📈 Performance Tips

### Resource Optimization

1. **Adjust worker count** based on CPU cores
2. **Enable Redis caching** for database queries
3. **Use connection pooling** for external services
4. **Monitor resource usage** with Grafana
5. **Scale horizontally** for production

### Performance Targets

- **Response Time:** <100ms (p95)
- **Success Rate:** >95%
- **Test Coverage:** >80%
- **Type Safety:** >95%

See [Hardware Optimization Guide](docs/deployment/HARDWARE_OPTIMIZATION.md) for optimization strategies.

---

## 📝 Next Steps

After successful deployment:

1. **Verify all services are running**
   ```bash
   ./deploy.sh status
   ```

2. **Test API endpoints**
   ```bash
   curl http://localhost:8000/health
   curl http://localhost:8000/docs
   ```

3. **Access OpenWebUI**
   ```
   Navigate to http://localhost:8080
   Create account or login
   ```

4. **Test AI integration**
   ```bash
   # Test AI tools endpoint
   curl -X POST http://localhost:8010/v1/ai/chat \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "Hello!"}]}'
   ```

5. **Monitor with Grafana**
   ```
   Navigate to http://localhost:3001
   View dashboards
   ```

---

## 📚 Additional Resources

### Documentation

- **[Full Documentation](docs/)** - Complete documentation index
- **[API Reference](docs/api/)** - API documentation
- **[Architecture](docs/architecture/)** - System architecture
- **[Deployment](docs/deployment/)** - Deployment guides
- **[Development](docs/development/)** - Development setup
- **[Guides](docs/guides/)** - Configuration guides
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Troubleshooting guide

### External Resources

- **Docker Documentation:** https://docs.docker.com/
- **Docker Compose:** https://docs.docker.com/compose/
- **Ollama:** https://ollama.ai/
- **FastAPI:** https://fastapi.tiangolo.com/
- **Grafana:** https://grafana.com/

---

## 🆘 Support

- **Documentation:** [docs/](docs/)
- **Issues:** [GitHub Issues](https://github.com/wish-maker/minder/issues)
- **Discussions:** [GitHub Discussions](https://github.com/wish-maker/minder/discussions)
- **Quick Help:** Run `./deploy.sh help`

---

**Built with ❤️ by Minder AI Team**

**Last Updated:** 2026-04-28
**Version:** 2.1.0

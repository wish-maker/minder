# Minder Platform - Quick Start Guide

## 🚀 Zero-to-Hero Deployment

This guide provides a **complete automated setup** from scratch.

---

## ✅ Prerequisites

- **Docker** 20.10+
- **Docker Compose** 2.0+
- **OpenSSL** (for secure credential generation)
- **8GB+ RAM**, **20GB+ Disk Space**
- **Linux/macOS** (Windows WSL2 supported)

### Quick Install Prerequisites

```bash
# Docker
curl -fsSL https://get.docker.com | sh

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
3. ✅ Setup all databases
4. ✅ Builds all Docker images
5. ✅ Deploys all services (21 services)
6. ✅ Pulls AI models (Llama 3.2, embeddings)
7. ✅ Runs comprehensive health checks
8. ✅ Displays access information

**Time:** 20-30 minutes (first run, includes AI model download)

### Option 2: Step-by-Step Deployment

```bash
# 1. Clean existing setup
./deploy.sh clean

# 2. Generate secure configuration
./deploy.sh deploy
```

---

## 📊 Access Points

After successful deployment, access:

| Service | URL | Credentials |
|---------|-----|-------------|
| **API Gateway** | http://localhost:8000 | See .env |
| **API Docs** | http://localhost:8000/docs | See .env |
| **Plugin Registry** | http://localhost:8001 | See .env |
| **OpenWebUI** | http://localhost:8080 | Sign up enabled |
| **Grafana** | http://localhost:3000 | admin / [see .env] |
| **Prometheus** | http://localhost:9090 | No auth |

---

## 🛠️ Management Commands

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

# Run health checks
./deploy.sh health

# Complete cleanup
./deploy.sh clean
```

---

## 🔒 Security First

**⚠️ CRITICAL:** The deployment automatically generates secure credentials and stores them in `infrastructure/docker/.env`.

### Immediate Actions After Deployment:

1. **Change Default Credentials:**
   ```bash
   # View generated credentials
   cat infrastructure/docker/.env

   # Change Grafana password
   docker exec minder-grafana grafana-cli admin reset-admin-password <new-password>
   ```

2. **Secure .env File:**
   ```bash
   # Ensure restrictive permissions
   chmod 600 infrastructure/docker/.env

   # Never commit to git!
   echo "infrastructure/docker/.env" >> .gitignore
   ```

3. **Enable TLS/SSL** (Production):
   - Use reverse proxy (nginx/traefik)
   - Enable HTTPS
   - Configure proper certificates

---

## 📈 Health Monitoring

### Automated Health Checks

```bash
# Run comprehensive health checks
./scripts/health-check.sh
```

**Output:**
- Infrastructure services status
- AI services status
- Core services status
- Web interfaces status
- Overall health score

### Manual Health Checks

```bash
# Check specific service
curl http://localhost:8000/health

# Check Docker containers
docker ps

# Check resource usage
docker stats

# View service logs
docker logs -f minder-api-gateway
```

---

## 🐛 Troubleshooting

### Service Won't Start

```bash
# Check logs
./deploy.sh logs <service-name>

# Restart service
docker restart minder-<service-name>

# Rebuild service
cd infrastructure/docker
docker compose up -d --build <service-name>
```

### Out of Memory

```bash
# Check resource usage
docker stats

# Stop memory-heavy services
docker stop minder-ollama  # If not using AI features
```

### Port Conflicts

```bash
# Check what's using the port
sudo lsof -i :8000

# Change port in .env
vim infrastructure/docker/.env
```

### Database Connection Issues

```bash
# Check PostgreSQL
docker exec -it minder-postgres psql -U minder -d minder

# Check Redis
docker exec -it minder-redis redis-cli -a <password> ping

# Restart database
docker restart minder-postgres
```

---

## 🔄 Updating

### Update Code

```bash
# Pull latest changes
git pull origin main

# Rebuild services
./deploy.sh deploy
```

### Update AI Models

```bash
# Pull new models
docker exec -it minder-ollama ollama pull <model-name>

# List available models
docker exec -it minder-ollama ollama list
```

---

## 🗑️ Complete Removal

```bash
# Stop and remove all containers, volumes, and images
./deploy.sh clean

# Manual cleanup
docker system prune -a --volumes
```

---

## 📚 Next Steps

1. **Explore API Documentation:** http://localhost:8000/docs
2. **Try OpenWebUI:** http://localhost:8080
3. **Check Grafana Dashboards:** http://localhost:3000
4. **Read Architecture Analysis:** [ARCHITECTURE_ANALYSIS.md](./ARCHITECTURE_ANALYSIS.md)
5. **Explore Plugins:** http://localhost:8001/docs

---

## 🆘 Getting Help

- **Documentation:** `docs/`
- **Troubleshooting:** `docs/troubleshooting/`
- **Architecture:** `docs/architecture/`
- **GitHub Issues:** [Create issue](https://github.com/your-repo/issues)

---

## ⚡ Quick Reference

```bash
# Full deployment
./deploy.sh deploy

# Service status
./deploy.sh status

# Health check
./deploy.sh health

# View logs
./deploy.sh logs

# Stop services
./deploy.sh stop

# Clean everything
./deploy.sh clean
```

---

**Deployment Time:** 20-30 minutes (first run)
**Maintenance Time:** <5 minutes (updates)
**Skill Level:** Beginner-friendly

**🎉 Congratulations! Your Minder Platform is now running!**

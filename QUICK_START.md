# 🚀 Minder Platform - Quick Start Guide

**Get Minder Platform running in 5 minutes!**

---

## Step 1: Install Prerequisites

Minder requires only **Docker** and **Docker Compose**.

### Ubuntu/Debian
```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Log out and back in for group changes to take effect
```

### macOS
```bash
# Download and install Docker Desktop
# https://www.docker.com/products/docker-desktop
```

### Verify Installation
```bash
docker --version
docker compose version
```

---

## Step 2: Clone Repository

```bash
git clone https://github.com/your-org/minder.git
cd minder
```

---

## Step 3: Run Installation Script

```bash
./install.sh
```

**This script will:**
1. ✅ Check Docker and Docker Compose are installed
2. ✅ Generate secure credentials automatically
3. ✅ Start all 15 services
4. ✅ Wait for services to be healthy
5. ✅ Verify deployment
6. ✅ Run health checks

**Installation takes 3-5 minutes on first run** (downloading Docker images).

---

## Step 4: Access Minder Platform

Once installation completes, open your browser:

### 🌐 API Documentation (Start Here)
**URL:** http://localhost:8000/docs

This interactive documentation lets you:
- Explore all API endpoints
- Test API calls directly
- View request/response formats

### 🔌 Plugin Registry
**URL:** http://localhost:8001/docs

Manage plugins, trigger data collection, view health status.

### 📊 Grafana Dashboards
**URL:** http://localhost:3000
**Default credentials:** `admin` / `admin`

Monitor system metrics, plugin performance, and data collection.

---

## Step 5: Get API Token

### Option 1: Using the Web Interface

1. Open http://localhost:8000/docs
2. Navigate to `/v1/auth/login`
3. Click "Try it out"
4. Enter:
   - Username: `admin`
   - Password: `any_password_8_chars`
5. Copy the `access_token` from response

### Option 2: Using Command Line

```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"mypassword123"}'
```

Copy the `access_token` from the response.

---

## Step 6: Test API

### List All Plugins

```bash
curl http://localhost:8000/v1/plugins
```

### Trigger Data Collection

```bash
curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

### Check Plugin Health

```bash
curl http://localhost:8000/v1/plugins/crypto/health \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

---

## 🔧 Quick Commands

### Start Platform
```bash
./start.sh
```

### Stop Platform
```bash
./stop.sh
```

### View All Logs
```bash
docker compose -f infrastructure/docker/docker-compose.yml logs -f
```

### Check Service Status
```bash
docker compose -f infrastructure/docker/docker-compose.yml ps
```

### Restart Specific Service
```bash
docker compose -f infrastructure/docker/docker-compose.yml restart api-gateway
```

---

## 📊 What's Running?

After installation, you'll have **20 containers** running:

### Infrastructure (4 containers)
- **PostgreSQL** - Primary database
- **Redis** - Cache and message broker
- **Qdrant** - Vector database for RAG
- **Ollama** - Local LLM inference

### Core Services (3 containers)
- **API Gateway** (port 8000) - Main API entry point
- **Plugin Registry** (port 8001) - Plugin management
- **Model Management** (port 8005) - AI model registry

### Plugins (5 containers)
- **Crypto Plugin** - Cryptocurrency data
- **News Plugin** - News aggregation
- **Network Plugin** - Network metrics
- **Weather Plugin** - Weather data
- **TEFAS Plugin** - Turkish investment funds

### Monitoring (4 containers)
- **Prometheus** (port 9090) - Metrics collection
- **Grafana** (port 3000) - Dashboards
- **Telegraf** - Metrics agent
- **PostgreSQL Exporter** - DB metrics
- **Redis Exporter** - Cache metrics

### Additional Services (4 containers)
- **RAG Pipeline** - Document processing
- **InfluxDB** - Time-series data
- **OpenWebUI** (port 8080) - AI chat interface
- **Model Fine-tuning** - AI model training

---

## ⚙️ Configuration

All configuration is in `infrastructure/docker/.env` (auto-generated).

### View Current Configuration
```bash
cat infrastructure/docker/.env
```

### Regenerate Credentials
```bash
cd infrastructure/docker
./setup-security.sh
```

### Change Settings

Edit `infrastructure/docker/.env`:
```bash
nano infrastructure/docker/.env
```

Then restart services:
```bash
./stop.sh
./start.sh
```

---

## 🐛 Common Issues

### Port Already in Use

**Error:** `Bind for 0.0.0.0:8000 failed: port is already allocated`

**Solution:** Check what's using the port:
```bash
sudo lsof -i :8000
```

Stop the conflicting service or change the port in `docker-compose.yml`.

### Out of Memory

**Error:** Services keep restarting

**Solution:** Check available memory:
```bash
free -h
```

Reduce service limits in `docker-compose.yml` or close other applications.

### Services Not Healthy

**Error:** Some services showing "unhealthy"

**Solution:** This is normal during first startup. Wait 2-3 minutes for initialization:
```bash
docker compose -f infrastructure/docker/docker-compose.yml ps
```

If still unhealthy after 5 minutes, check logs:
```bash
docker compose -f infrastructure/docker/docker-compose.yml logs [service-name]
```

---

## 📚 Next Steps

1. **Explore the API** - http://localhost:8000/docs
2. **View Grafana Dashboards** - http://localhost:3000
3. **Read the Documentation** - Check `docs/` folder
4. **Configure Plugins** - Use Plugin Registry API
5. **Set Up Monitoring** - Configure alerts in Grafana

---

## 🆘 Need Help?

- **Documentation:** See `docs/` folder
- **Issues:** Check `docs/ISSUES.md`
- **API Reference:** See `docs/API_REFERENCE.md`
- **Security Guide:** See `docs/SECURITY_SETUP_GUIDE.md`

---

## 🎉 You're Ready!

**Minder Platform is now running!**

Start exploring: http://localhost:8000/docs

**Happy coding! 🚀**

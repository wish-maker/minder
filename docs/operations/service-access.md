# 🔑 Service Access Guide - Minder Platform

**Last Updated:** 2026-05-10
**Platform Version:** 1.0.0
**Access Method:** Zero-Trust Authentication

---

## 📋 Overview

All services in the Minder platform are protected by **Authelia authentication** (zero-trust architecture). This guide explains how to access services correctly.

**Key Points:**
- ❌ Direct port access (8000-8007) is **blocked by design** (security feature)
- ✅ All services must be accessed through **Traefik reverse proxy** (ports 80/443)
- ✅ **Authentication is required** for all web services
- ✅ HTTP redirects to HTTPS automatically

---

## 🚀 Quick Access Methods

### Method 1: Web Browser (Production)

**Step 1: Access Authelia**
```
URL: https://auth.minder.local
```

**Step 2: Login**
- Username: See `infrastructure/docker/authelia/users_database.yml`
- Password: See `infrastructure/docker/authelia/users_database.yml`
- 2FA: If enabled, enter TOTP code

**Step 3: Access Services**
```
API Gateway:     https://api.minder.local
Plugin Registry: https://plugins.minder.local
Marketplace:     https://marketplace.minder.local
Grafana:         https://grafana.minder.local
Prometheus:      https://prometheus.minder.local
OpenWebUI:       https://openwebui.minder.local
```

### Method 2: Command Line with Authentication

**Step 1: Get Authelia Session Cookie**
```bash
# Login via browser, then copy session cookie
# Or use CLI (advanced - requires manual session handling)
```

**Step 2: Use Cookie in Requests**
```bash
# Access API with session cookie
curl -sk https://api.minder.local/api/health \
  -b "authelia_session=YOUR_SESSION_COOKIE"

# Access with full headers
curl -sk https://api.minder.local/api/health \
  -b "authelia_session=YOUR_SESSION_COOKIE" \
  -H "Content-Type: application/json"
```

### Method 3: Development/Debugging Access

**Option A: Shell Access**
```bash
# Interactive shell to any service
./setup.sh shell api-gateway
./setup.sh shell plugin-registry
./setup.sh shell rag-pipeline

# Inside container, access localhost
curl http://localhost:8000/health
```

**Option B: Docker Exec**
```bash
# Execute command in container
docker exec minder-api-gateway curl http://localhost:8000/health

# Interactive shell
docker exec -it minder-api-gateway /bin/bash
```

**Option C: Internal Network**
```bash
# Access via container IP (from host)
curl http://172.19.0.14:8000/health  # API Gateway
curl http://172.19.0.15:8002/health  # Plugin Registry
curl http://172.19.0.16:8003/health  # RAG Pipeline
```

---

## 🌐 Service URLs

### Web Services (HTTPS)

| Service | URL | Authentication | Purpose |
|---------|-----|----------------|---------|
| **Authelia** | https://auth.minder.local | Required | SSO Login |
| **API Gateway** | https://api.minder.local | Required | Main API |
| **Plugin Registry** | https://plugins.minder.local | Required | Plugin management |
| **Marketplace** | https://marketplace.minder.local | Required | Plugin marketplace |
| **Grafana** | https://grafana.minder.local | Required | Monitoring dashboards |
| **Prometheus** | https://prometheus.minder.local | Required | Metrics |
| **OpenWebUI** | https://openwebui.minder.local | Required | LLM Chat UI |
| **Jaeger** | https://jaeger.minder.local | Required | Distributed tracing |

### Internal Services (Docker Network)

| Service | Internal URL | Container IP | Purpose |
|---------|-------------|--------------|---------|
| **API Gateway** | http://minder-api-gateway:8000 | 172.19.0.14 | Main API |
| **Plugin Registry** | http://minder-plugin-registry:8002 | 172.19.0.15 | Plugin management |
| **RAG Pipeline** | http://minder-rag-pipeline:8003 | 172.19.0.16 | RAG processing |
| **Model Management** | http://minder-model-management:8004 | 172.19.0.17 | Model management |
| **Marketplace** | http://minder-marketplace:8005 | 172.19.0.18 | Plugin marketplace |
| **PostgreSQL** | postgres://minder-postgres:5432 | 172.19.0.4 | Primary database |
| **Redis** | redis://minder-redis:6379 | 172.19.0.5 | Cache |
| **Neo4j** | http://minder-neo4j:7474 | 172.19.0.7 | Graph database |
| **Qdrant** | http://minder-qdrant:6333 | 172.19.0.6 | Vector database |
| **RabbitMQ** | http://minder-rabbitmq:15672 | 172.19.0.8 | Message broker |

---

## 🔐 Authentication Flow

### Web Browser Flow

```
1. User navigates to https://api.minder.local
                   ↓
2. Traefik receives request
                   ↓
3. Authelia middleware checks for session cookie
                   ↓
4a. Cookie exists and valid → Access granted
4b. No cookie or invalid → 302 Redirect to Authelia
                   ↓
5. User logs in at https://auth.minder.local
                   ↓
6. Authelia issues session cookie
                   ↓
7. User redirected back to original service
                   ↓
8. Access granted with valid session
```

### API Client Flow

**Step 1: Initial Request (No Auth)**
```bash
curl -skI https://api.minder.local/api/health
```

**Response:**
```http
HTTP/2 302
Location: https://auth.minder.local/?rd=https%3A%2F%2Fapi.minder.local%2Fapi%2Fhealth
```

**Step 2: Authenticate**
```bash
# Open browser to https://auth.minder.local
# Login with credentials
# Get session cookie from browser dev tools
```

**Step 3: Access with Session**
```bash
curl -sk https://api.minder.local/api/health \
  -b "authelia_session=YOUR_SESSION_COOKIE"
```

**Response:**
```json
{
  "service": "api-gateway",
  "status": "healthy",
  "timestamp": "2026-05-10T18:56:30.975704"
}
```

---

## 🛠️ Development Access Methods

### Method 1: setup.sh Shell

**Interactive Shell:**
```bash
# API Gateway
./setup.sh shell api-gateway

# Plugin Registry
./setup.sh shell plugin-registry

# Any service
./setup.sh shell SERVICE_NAME
```

**Inside Container:**
```bash
# Test health endpoint
curl http://localhost:8000/health

# View logs
tail -f /var/log/service.log

# Run diagnostics
python -m pytest
```

### Method 2: Docker Exec

**Single Command:**
```bash
# API Gateway health
docker exec minder-api-gateway curl http://localhost:8000/health

# PostgreSQL connection
docker exec minder-postgres psql -U minder -c "SELECT version();"

# Redis ping
docker exec minder-redis redis-cli -a PASSWORD ping
```

**Interactive Shell:**
```bash
# Bash shell
docker exec -it minder-api-gateway /bin/bash

# Python shell
docker exec -it minder-api-gateway python

# Database shell
docker exec -it minder-postgres psql -U minder
```

### Method 3: Internal Network Access

**From Host Machine:**
```bash
# Get container IP
docker inspect minder-api-gateway | grep IPAddress

# Access via container IP
curl http://172.19.0.14:8000/health
curl http://172.19.0.15:8002/health
curl http://172.19.0.16:8003/health
```

**From Another Container:**
```bash
# Execute from API Gateway container
docker exec minder-api-gateway curl http://minder-postgres:5432
docker exec minder-api-gateway curl http://minder-redis:6379
docker exec minder-api-gateway curl http://minder-qdrant:6333
```

---

## 🧪 Testing Access

### Test 1: Verify HTTPS Redirect

```bash
curl -I http://api.minder.local/api/health
```

**Expected:** `HTTP/1.1 308 Permanent Redirect`

### Test 2: Verify Authentication Required

```bash
curl -skI https://api.minder.local/api/health
```

**Expected:** `HTTP/2 302` with redirect to Authelia

### Test 3: Verify Internal Access

```bash
docker exec minder-api-gateway curl http://localhost:8000/health
```

**Expected:** `HTTP/1.1 200` with JSON response

### Test 4: Verify Service Communication

```bash
docker exec minder-plugin-registry curl http://minder-api-gateway:8000/health
```

**Expected:** `HTTP/1.1 200` with JSON response

---

## ⚠️ Common Mistakes

### Mistake 1: Direct Port Access

**❌ WRONG:**
```bash
curl http://localhost:8000/health
```

**Why it fails:** Ports 8000-8007 are not exposed on host (security design)

**✅ CORRECT:**
```bash
# Through Traefik (requires auth)
curl -sk https://api.minder.local/api/health

# Or internal network (no auth required)
docker exec minder-api-gateway curl http://localhost:8000/health
```

### Mistake 2: HTTP Instead of HTTPS

**❌ WRONG:**
```bash
curl http://api.minder.local/api/health
```

**What happens:** Redirected to HTTPS, then to Authelia

**✅ CORRECT:**
```bash
curl -sk https://api.minder.local/api/health
```

### Mistake 3: Missing Authentication

**❌ WRONG:**
```bash
curl https://api.minder.local/api/health
```

**What happens:** 302 redirect to Authelia

**✅ CORRECT:**
```bash
# With authentication cookie
curl -sk https://api.minder.local/api/health \
  -b "authelia_session=YOUR_SESSION_COOKIE"

# Or use development access
docker exec minder-api-gateway curl http://localhost:8000/health
```

---

## 🔍 Troubleshooting

### Issue 1: "302 Found" Responses

**Cause:** This is **correct behavior** - authentication is working

**Solution:** Authenticate first via browser, then use session cookie

### Issue 2: "Connection Refused" on Port 8000

**Cause:** Port not exposed on host (security design)

**Solution:** Use HTTPS URL through Traefik or internal network access

### Issue 3: "404 Page Not Found"

**Cause:** Traefik routing issue or incorrect URL

**Solution:**
```bash
# Check Traefik logs
docker logs minder-traefik --tail 50

# Verify URL format
curl -skI https://api.minder.local/api/health

# Check service is running
docker ps | grep api-gateway
```

### Issue 4: Authentication Loop

**Cause:** Invalid session cookie or Authelia misconfiguration

**Solution:**
```bash
# Clear browser cookies
# Or get new session cookie

# Check Authelia logs
docker logs minder-authelia --tail 50

# Restart Authelia
docker compose restart authelia
```

---

## 📚 Additional Resources

- [Security Architecture](./security-architecture.md) - Zero-trust design details
- [Troubleshooting Guide](../troubleshooting/TROUBLESHOOTING.md) - Common issues
- [Authelia Documentation](https://www.authelia.com/docs/) - SSO configuration
- [Traefik Documentation](https://doc.traefik.io/traefik/) - Reverse proxy setup

---

## 🎯 Quick Reference

**Web Access:**
1. Go to https://auth.minder.local
2. Login with credentials
3. Access other services with active session

**CLI Access (Development):**
```bash
./setup.sh shell SERVICE_NAME
```

**CLI Access (Production):**
```bash
curl -sk https://api.minder.local/api/health \
  -b "authelia_session=YOUR_SESSION_COOKIE"
```

**Internal Network:**
```bash
docker exec minder-api-gateway curl http://localhost:8000/health
curl http://172.19.0.14:8000/health
```

---

*Last Updated: 2026-05-10*
*Platform Version: 1.0.0*
*Access Method: Zero-Trust Authentication*
*Status: Production Ready*

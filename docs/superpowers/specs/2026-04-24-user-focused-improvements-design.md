# Minder Platform - User-Focused Improvements Design

**Date:** 2026-04-24
**Status:** Approved
**Timeline:** 5 days
**Goal:** Fix AI integration, add dashboards, improve testing, prepare for production

---

## Executive Summary

This design addresses critical gaps in Minder Platform's user experience and production readiness. The current system has solid infrastructure but lacks working AI integration, user-friendly dashboards, adequate testing, and consistent documentation.

**Current State:**
- ✅ 5 plugins working (crypto, news, network, weather, tefas)
- ✅ API Gateway with JWT authentication
- ✅ Monitoring stack installed (Prometheus, Grafana)
- ❌ OpenWebUI integration broken
- ❌ AI tool calling not working
- ❌ 7% test coverage
- ❌ No user-facing dashboards
- ❌ Inconsistent documentation

**Target State:**
- ✅ AI chat interface working with tool calling
- ✅ 3+ user-facing Grafana dashboards
- ✅ 40%+ test coverage
- ✅ Comprehensive, consistent documentation
- ✅ Production-ready deployment

---

## Architecture Overview

### Current Issues

**1. AI Integration Broken**
- OpenWebUI container not running
- API Gateway missing `/v1/ai/` endpoints
- Ollama model not downloaded
- Tool calling mechanism not implemented

**2. User Experience Gaps**
- No visual dashboards for monitoring
- API-only interface (no GUI)
- Limited documentation for end users
- No real-time system visibility

**3. Testing & Quality**
- 7% test coverage (insufficient for production)
- No integration tests for AI features
- No end-to-end testing
- Manual testing only

**4. Documentation Issues**
- README claims 72% production ready
- CURRENT_STATUS claims 100% production ready
- Inconsistent information across docs
- Missing OpenWebUI usage guide

---

## Solution Design

### Phase 1: AI Integration (Days 1-2)

#### 1.1 OpenWebUI Container Setup

**Problem:** OpenWebUI container not in docker-compose.yml

**Solution:**
```yaml
# infrastructure/docker/docker-compose.yml

openwebui:
  image: ghcr.io/open-webui/open-webui:main
  container_name: minder-openwebui
  restart: unless-stopped
  environment:
    - OLLAMA_BASE_URL=http://minder-ollama:11434
    - OPENAI_API_KEY=sk-minder-dummy-key
    - OPENAI_BASE_URL=http://minder-api-gateway:8000/v1/ai
    - ENABLE_FUNCTIONS=true
    - FUNCTIONS_FILE=/app/config/functions.json
  volumes:
    - ./openwebui/functions.json:/app/config/functions.json:ro
  ports:
    - "8080:8080"
  depends_on:
    - ollama
    - api-gateway
  networks:
    - minder-network
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
    interval: 30s
    timeout: 10s
    retries: 3
```

**Files to Modify:**
- `infrastructure/docker/docker-compose.yml`

---

#### 1.2 Ollama Model Download

**Problem:** Ollama container unhealthy (no model)

**Solution:**
```bash
# Download llama3.2 model
docker exec minder-ollama ollama pull llama3.2

# Verify model is available
docker exec minder-ollama ollama list | grep llama3.2
```

**Automation:** Add to startup script

---

#### 1.3 API Gateway AI Endpoints

**Problem:** No `/v1/ai/` endpoints in API Gateway

**Solution:** Create `services/api-gateway/routes/ai.py`

```python
"""
AI Gateway endpoints for OpenWebUI integration
Provides OpenAI-compatible API for tool calling
"""

from fastapi import APIRouter, HTTPException, Request
import httpx
import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/ai", tags=["ai"])

# Tool definitions (from functions.json)
TOOLS_DEFINITIONS = {
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_crypto_price",
                "description": "Get current cryptocurrency price",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "enum": ["BTC", "ETH", "SOL", "ADA", "DOT"]}
                    },
                    "required": ["symbol"]
                }
            }
        },
        # ... (7 more tools)
    ]
}

@router.get("/functions/definitions")
async def get_function_definitions():
    """Return available tool definitions for LLM"""
    return TOOLS_DEFINITIONS

@router.post("/functions/{function_name}")
async def execute_function(function_name: str, params: Dict[str, Any]):
    """Execute a Minder platform function"""
    
    # Map function names to API calls
    function_mappings = {
        "get_crypto_price": {
            "url": "http://minder-plugin-registry:8001/v1/plugins/crypto/analysis",
            "method": "GET"
        },
        "collect_crypto_data": {
            "url": "http://minder-plugin-registry:8001/v1/plugins/crypto/collect",
            "method": "POST"
        },
        # ... (6 more mappings)
    }
    
    if function_name not in function_mappings:
        raise HTTPException(status_code=404, detail=f"Unknown function: {function_name}")
    
    mapping = function_mappings[function_name]
    
    # Call Minder API
    async with httpx.AsyncClient() as client:
        if mapping["method"] == "POST":
            response = await client.post(
                mapping["url"],
                json=params,
                timeout=30.0
            )
        else:
            # Add query parameters for GET requests
            url = mapping["url"]
            if params:
                url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
            response = await client.get(url, timeout=30.0)
        
        return {
            "result": response.json(),
            "status": "success",
            "timestamp": datetime.utcnow().isoformat()
        }

@router.post("/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint"""
    body = await request.json()
    
    # Extract messages and function calls
    messages = body.get("messages", [])
    functions = body.get("functions", [])
    
    # For now, route to Ollama
    # TODO: Implement proper function calling flow
    ollama_url = "http://minder-ollama:11434/api/chat"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            ollama_url,
            json=body,
            timeout=120.0
        )
        return response.json()
```

**Files to Create:**
- `services/api-gateway/routes/ai.py`

**Files to Modify:**
- `services/api-gateway/main.py` - Import and mount AI router

---

#### 1.4 Tool Calling Verification

**Test Plan:**
```bash
# Test 1: Get tool definitions
curl http://localhost:8000/v1/ai/functions/definitions

# Test 2: Execute tool directly
curl -X POST http://localhost:8000/v1/ai/functions/get_crypto_price \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC"}'

# Test 3: OpenWebUI chat
# Open browser to http://localhost:8080
# Send message: "What's the price of Bitcoin?"
# Verify LLM calls get_crypto_price tool
```

**Success Criteria:**
- ✅ All 8 tools accessible via API
- ✅ Tools execute successfully
- ✅ OpenWebUI can call tools
- ✅ LLM formats responses correctly

---

### Phase 2: Grafana Dashboards (Day 3)

#### 2.1 Dashboard 1: Plugin Health Monitoring

**Purpose:** Real-time visibility into plugin status

**Panels:**
1. Plugin Status Table (5 rows)
   - Name, Status, Health, Last Collection
   - Color-coded (green=healthy, red=unhealthy)

2. Data Collection Rate (Time Series)
   - Records collected per hour (per plugin)
   - Group by plugin name

3. Error Rate (Gauge)
   - Errors per minute
   - Alert if > 5 errors/min

4. Collection Latency (Heatmap)
   - Time to complete collection
   - Y-axis: Plugin, X-axis: Time

**Queries:**
```promql
# Plugin status from Prometheus
up{job=~"minder-plugin-.*"}

# Collection rate
rate(minder_data_collection_total[5m])

# Error rate
rate(minder_collection_errors_total[5m])
```

---

#### 2.2 Dashboard 2: System Performance

**Purpose:** Monitor API Gateway and infrastructure

**Panels:**
1. API Gateway Request Rate (Time Series)
   - Requests per second
   - Group by endpoint

2. Response Time Percentiles (Time Series)
   - p50, p95, p99 latency
   - Alert if p95 > 1s

3. Database Pool Usage (Gauge)
   - Active connections
   - Max connections: 100

4. Redis Cache Hit Rate (Single Stat)
   - Hit rate percentage
   - Goal: > 80%

5. Memory Usage (Time Series)
   - Per container memory
   - Alert if > 80%

**Queries:**
```promql
# Request rate
rate(http_requests_total{job="minder-api-gateway"}[5m])

# Response time
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Database pool
pg_stat_activity_count{datname="minder"}

# Redis hit rate
rate(redis_keyspace_hits[5m]) / (rate(redis_keyspace_hits[5m]) + rate(redis_keyspace_misses[5m]))
```

---

#### 2.3 Dashboard 3: Data Quality Metrics

**Purpose:** Ensure data collection is working properly

**Panels:**
1. Records per Plugin (Stat)
   - Total count in PostgreSQL
   - Compare to expected ranges

2. Data Freshness (Table)
   - Last successful collection time
   - Age since last collection
   - Alert if > 2 hours stale

3. Duplicate Key Errors (Time Series)
   - Errors per day
   - Should be zero (UPSERT working)

4. Storage Usage (Gauge)
   - Database size per plugin
   - Trend over time

**Queries:**
```promql
# Records collected
minder_plugin_records_total{plugin=~"crypto|news|network|weather|tefas"}

# Data freshness
time() - minder_last_collection_timestamp{plugin=~"crypto|news"}

# Storage usage
pg_database_size_bytes{datname=~"minder_.*"}
```

---

### Phase 3: Testing & Documentation (Day 4)

#### 3.1 Integration Test Suite

**File:** `tests/integration/test_ai_integration.py`

```python
"""
Integration tests for AI tool calling
"""

import pytest
import requests
import json

BASE_URL = "http://localhost:8000"

def test_ai_tool_definitions():
    """Test that tool definitions are accessible"""
    response = requests.get(f"{BASE_URL}/v1/ai/functions/definitions")
    assert response.status_code == 200
    
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) == 8  # 8 tools defined
    
    tool_names = [t["function"]["name"] for t in data["tools"]]
    expected_tools = [
        "get_crypto_price",
        "collect_crypto_data",
        "get_latest_news",
        "collect_news",
        "get_plugin_status",
        "get_network_metrics",
        "get_weather_data",
        "get_tefas_funds"
    ]
    assert set(tool_names) == set(expected_tools)

def test_get_crypto_price_tool():
    """Test get_crypto_price tool execution"""
    response = requests.post(
        f"{BASE_URL}/v1/ai/functions/get_crypto_price",
        json={"symbol": "BTC"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert "result" in data
    assert data["status"] == "success"
    
    # Verify price data structure
    result = data["result"]
    assert "symbol" in result
    assert result["symbol"] == "BTC"

def test_collect_crypto_data_tool():
    """Test collect_crypto_data tool execution"""
    response = requests.post(
        f"{BASE_URL}/v1/ai/functions/collect_crypto_data",
        json={}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert "result" in data
    assert data["status"] == "success"

def test_get_plugin_status_tool():
    """Test get_plugin_status tool execution"""
    response = requests.post(
        f"{BASE_URL}/v1/ai/functions/get_plugin_status",
        json={}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert "result" in data
    assert "plugins" in data["result"]
    assert len(data["result"]["plugins"]) == 5

@pytest.mark.skipif(
    os.environ.get("OPENWEBUI_URL") is None,
    reason="OpenWebUI not available"
)
def test_openwebui_chat_integration():
    """Test OpenWebUI chat with tool calling"""
    # This test requires OpenWebUI to be running
    openwebui_url = os.environ.get("OPENWEBUI_URL", "http://localhost:8080")
    
    # Send chat message
    response = requests.post(
        f"{openwebui_url}/api/chat",
        json={
            "message": "What's the price of Bitcoin?",
            "model": "llama3.2"
        }
    )
    
    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    
    # TODO: Verify tool was called (need to check OpenWebUI logs)
```

**File:** `tests/integration/test_plugin_management.py`

```python
"""
Integration tests for plugin management
"""

def test_enable_disable_plugin():
    """Test plugin enable/disable functionality"""
    # Requires JWT token
    token = get_test_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Disable plugin
    response = requests.post(
        f"{BASE_URL}/v1/plugins/crypto/disable",
        headers=headers
    )
    assert response.status_code == 200
    
    # Verify plugin is disabled
    response = requests.get(f"{BASE_URL}/v1/plugins/crypto")
    assert response.json()["enabled"] == False
    
    # Enable plugin
    response = requests.post(
        f"{BASE_URL}/v1/plugins/crypto/enable",
        headers=headers
    )
    assert response.status_code == 200
    
    # Verify plugin is enabled
    response = requests.get(f"{BASE_URL}/v1/plugins/crypto")
    assert response.json()["enabled"] == True

def test_plugin_data_collection():
    """Test triggering data collection"""
    token = get_test_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    # Trigger collection
    response = requests.post(
        f"{BASE_URL}/v1/plugins/crypto/collect",
        headers=headers
    )
    assert response.status_code == 200
    
    # Wait for collection to complete
    time.sleep(5)
    
    # Verify data was collected
    response = requests.get(
        f"{BASE_URL}/v1/plugins/crypto/analysis?symbol=BTC"
    )
    assert response.status_code == 200
    assert len(response.json()["data"]) > 0
```

---

#### 3.2 Unit Test Enhancements

**Coverage Targets:**
- Core modules: 80%+
- Plugins: 60%+
- API Gateway: 70%+

**New Tests:**

**File:** `tests/unit/test_ai_gateway.py`

```python
"""
Unit tests for AI Gateway endpoints
"""

from fastapi.testclient import TestClient
from services.api_gateway.main import app

client = TestClient(app)

def test_get_function_definitions():
    """Test tool definitions endpoint"""
    response = client.get("/v1/ai/functions/definitions")
    assert response.status_code == 200
    
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) == 8

def test_execute_get_crypto_price():
    """Test get_crypto_price execution"""
    response = client.post(
        "/v1/ai/functions/get_crypto_price",
        json={"symbol": "BTC"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert "result" in data
    assert data["status"] == "success"

def test_execute_unknown_function():
    """Test error handling for unknown function"""
    response = client.post(
        "/v1/ai/functions/unknown_function",
        json={}
    )
    assert response.status_code == 404
```

---

#### 3.3 Documentation Improvements

**File:** `README.md`

**Changes:**
```markdown
# Minder Platform

[![Production Ready](https://img.shields.io/badge/production%20ready-60%25-yellow.svg)](docs/CURRENT_STATUS.md)

> **⚠️ Status:** 60% production ready. Core infrastructure is solid, but AI integration and user dashboards need completion.

## ✨ Features

- 🔌 **Plugin System**: 5 built-in plugins (crypto, news, network, weather, TEFAS)
- 🏗️ **Microservices Architecture**: 20 containers, API Gateway pattern
- 📊 **Monitoring Stack**: Prometheus + Grafana dashboards
- 🔐 **JWT Authentication**: Secure API access with rate limiting
- 💾 **Multi-Database**: PostgreSQL, InfluxDB, Qdrant (vector), Redis
- 🤖 **AI Integration**: Ollama LLM + OpenWebUI chat interface (beta)
- ⚠️ **Production Ready**: 60% - see [CURRENT_STATUS.md](docs/CURRENT_STATUS.md) for details

## 🌐 Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **API Gateway** | http://localhost:8000 | Main API entry point |
| **OpenWebUI Chat** | http://localhost:8080 | AI chat interface (beta) |
| **Grafana Dashboards** | http://localhost:3000 | Monitoring dashboards |
| **Plugin Registry** | http://localhost:8001 | Plugin management |

## 🤖 AI Chat Interface (BETA)

OpenWebUI provides a natural language interface to Minder Platform:

**Start using:**
1. Open http://localhost:8080
2. Sign up/login
3. Try these queries:
   - "What's the price of Bitcoin?"
   - "Collect the latest crypto data"
   - "What are the latest news headlines?"
   - "Check the status of all plugins"

**See:** [OpenWebUI Integration Guide](docs/OPENWEBUI_INTEGRATION_GUIDE.md)
```

**File:** `docs/CURRENT_STATUS.md`

**Changes:**
```markdown
# Minder Platform - Current Status Snapshot

> **Generated:** 2026-04-24
> **Production Readiness:** 60% (up from 72%)
> **Phase:** Phase 1 Complete ✅ | Phase 2 Complete ✅ | Phase 3 Complete ✅ | AI Integration In Progress ⚠️

## Executive Summary

**Current State:**
- ✅ Core infrastructure solid (API Gateway, Plugin Registry, 5 plugins)
- ✅ JWT authentication and security implemented
- ✅ Monitoring stack installed (Prometheus, Grafana)
- ⚠️ AI integration in progress (OpenWebUI not deployed)
- ❌ User dashboards not created
- ❌ Test coverage at 7% (target: 40%)

**What's Working:**
1. ✅ 5 plugins collecting data (crypto, news, network, weather, tefas)
2. ✅ API Gateway with JWT auth and rate limiting
3. ✅ Plugin Registry with health monitoring
4. ✅ Databases (PostgreSQL, Redis, InfluxDB, Qdrant)
5. ✅ Monitoring (Prometheus, Grafana installed)

**What's Not Working:**
1. ❌ OpenWebUI container not deployed
2. ❌ AI tool calling not implemented
3. ❌ User-facing Grafana dashboards missing
4. ❌ Test coverage insufficient (7%)
5. ❌ Documentation inconsistencies

**Current Work:**
- Implementing AI integration (OpenWebUI + tool calling)
- Creating Grafana dashboards for end users
- Improving test coverage to 40%
- Fixing documentation inconsistencies
```

**New File:** `docs/USER_GUIDE.md`

```markdown
# Minder Platform - User Guide

## Getting Started

### 1. Check System Status

Open Grafana: http://localhost:3000
- Login: admin/admin
- View "Plugin Health" dashboard

### 2. Use AI Chat Interface

Open: http://localhost:8080
- Sign up for account
- Ask questions in natural language:
  - "What's the price of Bitcoin?"
  - "Collect the latest news"
  - "How are the plugins doing?"

### 3. Access API Directly

See: [API Reference](docs/API_REFERENCE.md)

## Common Tasks

### Collect Cryptocurrency Data

**Via AI Chat:**
```
"Collect the latest crypto data for me"
```

**Via API:**
```bash
TOKEN=$(curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}' | jq -r '.access_token')

curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer $TOKEN"
```

### Check Plugin Status

**Via AI Chat:**
```
"Check the status of all plugins"
```

**Via API:**
```bash
curl http://localhost:8000/v1/plugins | jq '.plugins[] | {name, status, health}'
```

## Troubleshooting

### AI Chat Not Working

1. Check OpenWebUI is running:
```bash
docker ps | grep openwebui
```

2. Check Ollama has model:
```bash
docker exec minder-ollama ollama list
```

3. See: [OpenWebUI Integration Guide](docs/OPENWEBUI_INTEGRATION_GUIDE.md)

### Plugins Not Collecting Data

1. Check plugin status:
```bash
curl http://localhost:8001/v1/plugins
```

2. Check plugin logs:
```bash
docker logs minder-plugin-registry --tail 50
```

3. Trigger manual collection:
```bash
curl -X POST http://localhost:8000/v1/plugins/{name}/collect \
  -H "Authorization: Bearer $TOKEN"
```
```

---

### Phase 4: Production Readiness (Day 5)

#### 4.1 Security Hardening

**Environment Variable Validation:**

**File:** `infrastructure/docker/setup-security.sh`

```bash
#!/bin/bash
# Enhanced security setup script

set -e

echo "🔒 Minder Platform Security Setup"

# Generate secure credentials
generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
}

generate_jwt_secret() {
    openssl rand -base64 64 | tr -d "=+/" | cut -c1-64
}

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file with secure credentials..."
    
    cat > .env <<EOF
# Database Credentials
POSTGRES_PASSWORD=$(generate_password)
REDIS_PASSWORD=$(generate_password)

# JWT Secret
JWT_SECRET=$(generate_jwt_secret)
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# InfluxDB Token
INFLUXDB_TOKEN=$(generate_password)

# Application Settings
LOG_LEVEL=INFO
ENVIRONMENT=production
RATE_LIMIT_PER_MINUTE=60

# Admin Users
ADMIN_USERS=admin,operator
EOF

    chmod 600 .env
    echo "✅ .env file created with secure credentials"
else
    echo "✅ .env file already exists"
fi

# Validate .env
echo "🔍 Validating environment variables..."

source .env

# Check required variables
required_vars=(
    "POSTGRES_PASSWORD"
    "REDIS_PASSWORD"
    "JWT_SECRET"
    "INFLUXDB_TOKEN"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var is not set"
        exit 1
    fi
done

echo "✅ All required environment variables are set"

# Check password strength
if [ ${#POSTGRES_PASSWORD} -lt 20 ]; then
    echo "⚠️  Warning: POSTGRES_PASSWORD should be at least 20 characters"
fi

if [ ${#JWT_SECRET} -lt 40 ]; then
    echo "⚠️  Warning: JWT_SECRET should be at least 40 characters"
fi

echo "🎉 Security setup complete!"
```

**Rate Limiting Fix:**

**File:** `services/api-gateway/main.py`

```python
# Add Prometheus endpoint to rate limiting exceptions
RATE_LIMIT_EXEMPT_ENDPOINTS = [
    r"/metrics",
    r"/health",
    r"/v1/ai/functions/definitions"
]

@app.middleware("http")
async def add_rate_limit_exempt(request: Request, call_next):
    # Check if endpoint should be exempt from rate limiting
    for pattern in RATE_LIMIT_EXEMPT_ENDPOINTS:
        if re.match(pattern, request.url.path):
            # Mark request as exempt
            request.state.rate_limit_exempt = True
            break
    
    return await call_next(request)
```

---

#### 4.2 Production Deployment Documentation

**New File:** `docs/PRODUCTION_DEPLOYMENT.md`

```markdown
# Minder Platform - Production Deployment Guide

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 16GB RAM minimum
- 50GB disk space
- Domain name (for HTTPS)

## Pre-Deployment Checklist

### 1. Security Setup

```bash
cd infrastructure/docker
./setup-security.sh
```

Verify:
- [ ] .env file created
- [ ] All credentials secure (20+ chars)
- [ ] File permissions set to 600

### 2. DNS Configuration

```bash
# Configure A records
api.yourdomain.com → YOUR_SERVER_IP
grafana.yourdomain.com → YOUR_SERVER_IP
```

### 3. SSL/TLS Certificates

**Option A: Let's Encrypt (Recommended)**
```bash
# Install certbot
sudo apt install certbot

# Generate certificates
sudo certbot certonly --standalone -d api.yourdomain.com
```

**Option B: Custom Certificates**
```bash
# Place certificates in infrastructure/docker/ssl/
# cert.pem and key.pem
```

### 4. Configure Reverse Proxy

**File:** `infrastructure/docker/nginx/nginx.conf`

```nginx
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        proxy_pass http://minder-api-gateway:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Deployment Steps

### Step 1: Start Services

```bash
cd infrastructure/docker
docker compose up -d
```

### Step 2: Verify Health

```bash
# Check all containers
docker compose ps

# Check API Gateway
curl https://api.yourdomain.com/health

# Check plugins
curl https://api.yourdomain.com/v1/plugins
```

### Step 3: Configure Monitoring

1. Access Grafana: http://grafana.yourdomain.com
2. Login with admin/admin
3. Change admin password
4. Configure alert notifications
5. Import dashboards

### Step 4: Test AI Integration

1. Access OpenWebUI: http://yourdomain.com:8080
2. Sign up for account
3. Test: "What's the price of Bitcoin?"
4. Verify tool calling works

## Post-Deployment

### Backup Setup

```bash
# Database backup
docker exec minder-postgres pg_dump -U minder minder > backup.sql

# Volume backup
docker run --rm -v minder_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup.tar.gz /data
```

### Monitoring Setup

1. Configure Prometheus targets
2. Set up Grafana alerts:
   - API Gateway down
   - Plugin collection failed
   - Database connection pool exhausted
   - Disk space > 80%

### Log Aggregation

```bash
# View logs
docker compose logs -f

# Export logs
docker compose logs > logs.txt
```

## Troubleshooting

### Issue: Services Not Starting

```bash
# Check logs
docker compose logs

# Check disk space
df -h

# Check memory
free -h
```

### Issue: High Memory Usage

```bash
# Check container memory
docker stats

# Restart memory-intensive services
docker compose restart ollama
```

### Issue: Database Connection Errors

```bash
# Check PostgreSQL
docker exec minder-postgres pg_isready -U minder

# Check connections
docker exec minder-postgres psql -U minder -c "SELECT count(*) FROM pg_stat_activity;"
```

## Maintenance

### Update Services

```bash
# Pull latest images
docker compose pull

# Restart with new images
docker compose up -d
```

### Backup Strategy

- Daily automated backups
- Weekly full backup verification
- Monthly restore testing

### Scaling

**Horizontal Scaling:**
```bash
# Scale API Gateway
docker compose up -d --scale api-gateway=3
```

**Vertical Scaling:**
```yaml
# In docker-compose.yml
services:
  postgres:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
```

---

#### 4.3 Health Check Verification

**File:** `tests/integration/test_production_readiness.py`

```python
"""
Production readiness verification tests
"""

import pytest
import requests
import time

def test_all_services_healthy():
    """Verify all critical services are healthy"""
    services = {
        "API Gateway": "http://localhost:8000/health",
        "Plugin Registry": "http://localhost:8001/health",
        "Grafana": "http://localhost:3000/api/health",
    }
    
    for service, url in services.items():
        response = requests.get(url, timeout=5)
        assert response.status_code == 200, f"{service} not healthy"
        
        data = response.json()
        if "status" in data:
            assert data["status"] == "healthy", f"{service} status: {data['status']}"

def test_plugins_loaded():
    """Verify all plugins are loaded and healthy"""
    response = requests.get("http://localhost:8001/v1/plugins")
    assert response.status_code == 200
    
    data = response.json()
    assert data["count"] == 5
    
    for plugin in data["plugins"]:
        assert plugin["enabled"] == True, f"{plugin['name']} not enabled"
        assert plugin["health_status"] == "healthy", f"{plugin['name']} unhealthy"

def test_ai_integration():
    """Verify AI tool calling is working"""
    # Test tool definitions
    response = requests.get("http://localhost:8000/v1/ai/functions/definitions")
    assert response.status_code == 200
    assert len(response.json()["tools"]) == 8
    
    # Test tool execution
    response = requests.post(
        "http://localhost:8000/v1/ai/functions/get_crypto_price",
        json={"symbol": "BTC"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_dashboards_accessible():
    """Verify Grafana dashboards exist and are accessible"""
    # Requires Grafana API key or session
    grafana_url = "http://localhost:3000"
    
    # List dashboards
    response = requests.get(
        f"{grafana_url}/api/search",
        headers={"Authorization": "Bearer YWRtaW46YWRtaW4="}  # base64 admin:admin
    )
    assert response.status_code == 200
    
    dashboards = response.json()
    dashboard_titles = [db["title"] for db in dashboards]
    
    required_dashboards = [
        "Plugin Health Monitoring",
        "System Performance",
        "Data Quality Metrics"
    ]
    
    for title in required_dashboards:
        assert title in dashboard_titles, f"Dashboard '{title}' not found"

def test_documentation_consistency():
    """Verify documentation is consistent"""
    import re
    
    # Check README and CURRENT_STATUS agree on production readiness
    with open("README.md") as f:
        readme = f.read()
    
    with open("docs/CURRENT_STATUS.md") as f:
        status = f.read()
    
    # Extract production ready percentages
    readme_match = re.search(r'production%20ready-(\d+)%', readme)
    status_match = re.search(r'Production Readiness.*?(\d+)%', status)
    
    if readme_match and status_match:
        readme_pct = int(readme_match.group(1))
        status_pct = int(status_match.group(1))
        
        # Should be within 5% of each other
        assert abs(readme_pct - status_pct) <= 5, \
            f"README says {readme_pct}%, STATUS says {status_pct}%"

def test_rate_limiting():
    """Verify rate limiting is working"""
    # Make many requests
    responses = []
    for _ in range(70):  # Exceeds rate limit of 60
        response = requests.get("http://localhost:8000/health")
        responses.append(response.status_code)
    
    # Should have some 429 responses
    assert 429 in responses, "Rate limiting not working"
    
    # But /metrics should be exempt
    metrics_responses = []
    for _ in range(10):
        response = requests.get("http://localhost:8000/metrics")
        metrics_responses.append(response.status_code)
    
    assert all(code == 200 for code in metrics_responses), \
        "Rate limiting blocking /metrics endpoint"

def test_security_headers():
    """Verify security headers are present"""
    response = requests.get("http://localhost:8000/health")
    
    headers = response.headers
    
    # Check for security headers
    assert "X-Content-Type-Options" in headers
    assert "X-Frame-Options" in headers
    assert "X-XSS-Protection" in headers
```

---

## Implementation Plan

### Day 1-2: AI Integration

**Tasks:**
1. Add OpenWebUI to docker-compose.yml (1 hour)
2. Download Ollama llama3.2 model (30 min)
3. Create API Gateway AI endpoints (3 hours)
4. Test tool calling (1 hour)
5. Update documentation (1 hour)

**Success Criteria:**
- ✅ OpenWebUI accessible at http://localhost:8080
- ✅ All 8 tools accessible via API
- ✅ Tool calling works end-to-end
- ✅ LLM can call tools via chat

---

### Day 3: Grafana Dashboards

**Tasks:**
1. Create Plugin Health dashboard (2 hours)
2. Create System Performance dashboard (2 hours)
3. Create Data Quality dashboard (2 hours)
4. Test dashboards (1 hour)
5. Create dashboard documentation (1 hour)

**Success Criteria:**
- ✅ 3 dashboards created and accessible
- ✅ Dashboards show real data
- ✅ Dashboards update in real-time
- ✅ User can monitor system health

---

### Day 4: Testing & Documentation

**Tasks:**
1. Write integration tests (3 hours)
2. Write unit tests (2 hours)
3. Achieve 40% coverage (1 hour)
4. Update README and CURRENT_STATUS (1 hour)
5. Create USER_GUIDE.md (1 hour)

**Success Criteria:**
- ✅ 15+ new tests passing
- ✅ 40%+ test coverage
- ✅ Documentation consistent
- ✅ User guide complete

---

### Day 5: Production Readiness

**Tasks:**
1. Enhance security setup (2 hours)
2. Fix rate limiting issues (1 hour)
3. Create PRODUCTION_DEPLOYMENT.md (2 hours)
4. Write production readiness tests (1 hour)
5. Final verification (1 hour)

**Success Criteria:**
- ✅ Security credentials validated
- ✅ Rate limiting working correctly
- ✅ Production documentation complete
- ✅ All tests passing
- ✅ System production ready

---

## Risk Mitigation

### Risk 1: AI Integration Complexity

**Risk:** Tool calling may not work as expected with Ollama

**Mitigation:**
- Start with direct API testing before OpenWebUI
- Have fallback to manual tool calling
- Document known limitations

### Risk 2: Time Constraints

**Risk:** 5 days may not be sufficient

**Mitigation:**
- Prioritize critical path (AI + dashboards)
- Defer nice-to-have features
- Focus on MVP completion

### Risk 3: Breaking Changes

**Risk:** Changes may break existing functionality

**Mitigation:**
- Test after each change
- Use feature flags if needed
- Keep backups of working state

---

## Success Metrics

**Quantitative:**
- AI tool calling: 0 → 8 tools working
- Test coverage: 7% → 40%
- Dashboards: 0 → 3 dashboards
- Documentation consistency: 70% → 100%

**Qualitative:**
- User can interact with system via AI chat
- User can monitor system via dashboards
- Documentation is clear and consistent
- System is production-ready

---

## Next Steps

After completion:
1. Deploy to staging environment
2. Conduct user acceptance testing
3. Gather feedback and iterate
4. Plan Phase 5 enhancements

---

**This design balances quick wins with long-term quality, focusing on the most critical user-facing improvements while maintaining production readiness.**

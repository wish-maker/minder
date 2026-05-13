# Network Access & Architecture Fixes - Design Document

**Date:** 2026-05-13
**Author:** Claude Code (Superpowers Brainstorming)
**Status:** Approved
**Target:** Minder Platform - Open Source Production Ready

---

## Executive Summary

Minder platformunda kritik network erişim sorunları tespit edildi ve düzeltme planı hazırlandı. Ana sorun: API servisleri host'a map edilmemiş, sadece Traefik routing üzerinden erişilebilir olacak şekilde tasarlanmış. Bu, local network/VPN erişimini engelliyor.

**Server IP:** 192.168.68.14
**Goal:** Hybrid access pattern - Direct ports + Traefik routing
**Impact:** All 32 services accessible via local network/VPN

---

## Problem Analysis

### Critical Issues Found

1. **Port Mapping Missing (CRITICAL)**
   - API services (api-gateway:8000, plugin-registry:8001, etc.) have NO host port bindings
   - Only accessible via Traefik reverse proxy
   - Blocks local network/VPN access

2. **Health Check Gaps**
   - `minder-redis-exporter`: NO healthcheck defined
   - `minder-otel-collector`: NO healthcheck defined
   - Status unknown despite showing "Up"

3. **Foreign Container**
   - `clever_chandrasekhar` container (not part of Minder project)
   - Should be removed for cleanliness

4. **Network Security**
   - Traefik IP whitelist too restrictive (127.0.0.1/32 only)
   - Blocks local network access to dashboard

### Root Cause

Docker Compose designed as "production-first" with Traefik-only access, but this breaks:
- Local development workflows
- VPN remote access
- LAN-based monitoring
- Open source usage patterns

---

## Solution Design

### Architecture Pattern: Hybrid Dual Access

```
┌─────────────────────────────────────────────────────────────┐
│                     ACCESS PATTERNS                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  PATTERN 1: Direct Port Access (Dev/LAN/VPN)                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ http://192.168.68.14:8000 → API Gateway            │    │
│  │ http://192.168.68.14:8001 → Plugin Registry        │    │
│  │ http://192.168.68.14:8002 → Marketplace            │    │
│  │ http://192.168.68.14:8003 → State Manager          │    │
│  │ http://192.168.68.14:8004 → RAG Pipeline           │    │
│  │ http://192.168.68.14:8005 → Model Management       │    │
│  │ http://192.168.68.14:8006 → TTS/STT Service        │    │
│  │ http://192.168.68.14:8007 → Model Fine-tuning      │    │
│  │ http://192.168.68.14:8080 → OpenWebUI              │    │
│  │ http://192.168.68.14:3000 → Grafana                │    │
│  │ http://192.168.68.14:9090 → Prometheus             │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
│  PATTERN 2: Traefik Routing (Production/SSL)                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ https://api.minder.local → API Gateway (SSL)        │    │
│  │ https://auth.minder.local → Authelia (SSO)          │    │
│  │ https://grafana.minder.local → Grafana (SSL)        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Benefits

✅ **Flexibility**: Works in dev, LAN, VPN, and production
✅ **Security**: Traefik SSL termination + Authelia SSO
✅ **Simplicity**: No /etc/hosts editing needed for basic access
✅ **Open Source Friendly**: Works out of the box for contributors

---

## Implementation Plan

### Phase 1: Critical Fixes (IMMEDIATE - Do First)

#### 1.1 Add Port Mappings to API Services

**File:** `infrastructure/docker/docker-compose.yml`

**Changes:**
```yaml
api-gateway:
  ports:
    - "8000:8000"  # ADD THIS
  # ... rest of config

plugin-registry:
  ports:
    - "8001:8001"  # ADD THIS

marketplace:
  ports:
    - "8002:8002"  # ADD THIS

plugin-state-manager:
  ports:
    - "8003:8003"  # ADD THIS

rag-pipeline:
  ports:
    - "8004:8004"  # ADD THIS

model-management:
  ports:
    - "8005:8005"  # ADD THIS

tts-stt-service:
  ports:
    - "8006:8006"  # ADD THIS

model-fine-tuning:
  ports:
    - "8007:8007"  # ADD THIS

openwebui:
  ports:
    - "8080:8080"  # Already exists, verify
```

**Impact:** API services accessible via `http://192.168.68.14:8000-8007`

---

#### 1.2 Add Missing Health Checks

**File:** `infrastructure/docker/docker-compose.yml`

**redis-exporter health check:**
```yaml
redis-exporter:
  # ... existing config
  healthcheck:
    test: ["CMD", "wget", "--spider", "-q", "http://localhost:9121/metrics"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```

**otel-collector health check:**
```yaml
otel-collector:
  # ... existing config
  healthcheck:
    test: ["CMD", "wget", "--spider", "-q", "http://localhost:18888/metrics"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```

---

#### 1.3 Remove Foreign Container

**Command:**
```bash
docker rm -f clever_chandrasekhar
```

---

#### 1.4 Update Traefik IP Whitelist

**File:** `infrastructure/docker/docker-compose.yml`

**Change:**
```yaml
traefik:
  labels:
    # OLD: 127.0.0.1/32 only
    # NEW: Local network subnets
    - traefik.http.middlewares.ipwhitelist.ipwhitelist.trustedIPs=192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,127.0.0.1/32
```

**Subnets explained:**
- `192.168.0.0/16`: Home/office LAN (common)
- `10.0.0.0/8`: Corporate networks
- `172.16.0.0/12`: Private networks
- `127.0.0.1/32`: Localhost

---

### Phase 2: Apply Changes

**Commands:**
```bash
# 1. Stop all services
cd ~/minder
./setup.sh stop

# 2. Remove foreign container
docker rm -f clever_chandrasekhar

# 3. Apply docker-compose changes (manual edit or sed)

# 4. Start services
./setup.sh start

# 5. Verify access
curl http://192.168.68.14:8000/health
curl http://192.168.68.14:8001/health
curl http://192.168.68.14:3000
```

---

### Phase 3: Validation & Testing

**Test Matrix:**

| Service | Direct Access | Traefik Access | Health Check |
|---------|--------------|----------------|--------------|
| API Gateway | `:8000` | `api.minder.local` | ✅ |
| Plugin Registry | `:8001` | N/A | ✅ |
| Marketplace | `:8002` | N/A | ✅ |
| State Manager | `:8003` | N/A | ✅ |
| RAG Pipeline | `:8004` | N/A | ✅ |
| Model Management | `:8005` | N/A | ✅ |
| TTS/STT | `:8006` | N/A | ✅ |
| Model Fine-tuning | `:8007` | N/A | ✅ |
| OpenWebUI | `:8080` | N/A | ✅ |
| Grafana | `:3000` | `grafana.minder.local` | ✅ |
| Prometheus | `:9090` | N/A | ✅ |
| Redis Exporter | N/A | N/A | ✅ (NEW) |
| OTel Collector | N/A | N/A | ✅ (NEW) |

---

### Phase 4: Documentation Updates

**Files to update:**

1. **README.md**
   - Add "Local Network Access" section
   - Update quick start commands with `192.168.68.14` examples
   - Document both access patterns

2. **docs/deployment/production.md**
   - Document hybrid access pattern
   - Add security considerations

3. **CLAUDE.md**
   - Update service port mappings
   - Add network access patterns

---

## Security Considerations

### Risks Introduced

1. **Direct Port Exposure**
   - **Risk:** Services accessible on LAN without SSL/Auth
   - **Mitigation:** Firewall rules, VPN only, network segmentation
   - **Recommendation:** Use in trusted networks only

2. **IP Whitelist Expansion**
   - **Risk:** Broader access to Traefik dashboard
   - **Mitigation:** Authelia SSO still required
   - **Recommendation:** Monitor dashboard access logs

### Best Practices

✅ **Production Deployment:**
- Use Traefik SSL routing exclusively
- Disable direct port mappings via env var
- Configure firewall rules
- Enable VPN for remote access

✅ **Development/LAN:**
- Direct port access acceptable
- Keep Authelia enabled for sensitive services
- Monitor with Prometheus/Grafana

---

## Rollback Plan

If issues occur:

```bash
# Quick rollback - stop services
cd ~/minder
./setup.sh stop

# Revert docker-compose.yml changes
git checkout infrastructure/docker/docker-compose.yml

# Restart
./setup.sh start
```

**Data Loss Risk:** None (no volume changes)

---

## Success Criteria

After implementation, ALL of these must work:

```bash
# 1. Direct API access
curl http://192.168.68.14:8000/health
# Expected: {"service":"api-gateway","status":"healthy",...}

curl http://192.168.68.14:8001/health
# Expected: {"service":"plugin-registry","status":"healthy",...}

# 2. Monitoring access
curl http://192.168.68.14:3000
# Expected: Grafana UI HTML

curl http://192.168.68.14:9090
# Expected: Prometheus UI HTML

# 3. All services healthy
./setup.sh status
# Expected: 32/32 services healthy

# 4. No unhealthy containers
docker ps -a --filter health=unhealthy
# Expected: Empty output

# 5. Foreign container removed
docker ps -a | grep clever_chandrasekhar
# Expected: Empty output
```

---

## Future Enhancements

1. **Environment-based Port Mapping**
   - DEV: Direct ports enabled
   - PROD: Traefik only
   - Controlled via `ENVIRONMENT` env var

2. **setup.sh Enhancements**
   - `./setup.sh access-mode` - Toggle direct/Traefik/both
   - `./setup.sh network-test` - Test connectivity from all interfaces
   - `./setup.sh expose` - Add port mapping dynamically

3. **Firewall Integration**
   - UFW/iptables rules generator
   - Network segmentation guide

4. **VPN Documentation**
   - WireGuard setup guide
   - Tailscale integration

---

## References

- **Current State:** `/root/minder/infrastructure/docker/docker-compose.yml`
- **Setup Script:** `/root/minder/setup.sh`
- **Server IP:** `192.168.68.14`
- **Network Subnet:** `192.68.0.0/16` (likely)

---

## Approval

- [x] Design reviewed
- [x] Implementation risks assessed
- [x] Rollback plan defined
- [x] Success criteria established

**Next Step:** Invoke `superpowers:writing-plans` to create detailed implementation plan.

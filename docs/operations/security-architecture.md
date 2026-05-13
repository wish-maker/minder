# 🔐 Security Architecture - Zero-Trust Design

**Last Updated:** 2026-05-10
**Platform Version:** 1.0.0
**Security Model:** Zero-Trust Network Segmentation

---

## 📋 Overview

Minder platform implements a **zero-trust security architecture** where every service, user, and network flow must be authenticated and authorized. This is achieved through:

- **Network Segmentation**: No exposed host ports (except Traefik)
- **Authentication Required**: All services protected by Authelia SSO
- **HTTPS-Only**: TLS/SSL enforced on all connections
- **Service Discovery**: Internal-only Docker network communication

---

## 🏗️ Security Pillars

### Pillar 1: No Exposed Ports

**Design Principle:** All services run on internal Docker network only

**Implementation:**
```yaml
# docker-compose.yml - No "ports:" mapping for internal services
api-gateway:
  # ❌ NO: ports: ["8000:8000"]
  # ✅ YES: No port mapping = internal only
  networks:
    - docker_minder-network

# Only Traefik binds to host
traefik:
  ports:
    - "80:80"
    - "443:443"
```

**Benefits:**
- Direct external access impossible
- All traffic must go through reverse proxy
- Attack surface minimized

**Verification:**
```bash
# Check that only Traefik has host port bindings
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep -v "0.0.0.0"
# Should only see traefik with 0.0.0.0:80 and 0.0.0.0:443
```

---

### Pillar 2: Authentication Required

**Design Principle:** All web services require valid authentication

**Implementation:**
```yaml
# docker-compose.yml - All services have Authelia middleware
api-gateway:
  labels:
    - "traefik.http.routers.api-gateway.middlewares=authelia-forwardauth@file,strip-api-prefix"
```

**Authentication Flow:**
```
1. User Request → https://api.minder.local/api/health
                   ↓
2. Traefik → Authelia ForwardAuth Middleware
                   ↓
3. Authelia → Check session cookie
                   ↓
4a. Valid Cookie → Allow access to service
4b. No Cookie → 302 Redirect to Authelia login
                   ↓
5. User logs in → Session cookie issued
                   ↓
6. Retry request → Access granted
```

**Benefits:**
- Single sign-on (SSO) across all services
- Two-factor authentication (2FA) support
- Centralized user management
- Audit logging for all access

**Verification:**
```bash
# Test authentication redirect
curl -skI https://api.minder.local/api/health
# Should return: HTTP/2 302
# Location: https://auth.minder.local/?rd=...

# Test with valid session
curl -sk https://api.minder.local/api/health \
  -b "authelia_session=VALID_SESSION"
# Should return: HTTP/2 200 with response body
```

---

### Pillar 3: HTTPS-Only

**Design Principle:** All connections encrypted with TLS/SSL

**Implementation:**
```yaml
# traefik/dynamic/ssl-configuration.yml
tls:
  certificates:
    - certFile: /letsencrypt/local-host.crt
      keyFile: /letsencrypt/local-host.key
      stores:
        - default

# docker-compose.yml - Traefik labels
traefik:
  labels:
    - "traefik.http.routers.http-catchall.entrypoints=web"
    - "traefik.http.routers.http-catchall.middlewares=redirect-to-https"
```

**HTTP to HTTPS Redirect:**
```yaml
# Automatic redirect for all HTTP requests
redirect-to-https:
  scheme: https
  permanent: true
```

**Benefits:**
- Data encryption in transit
- Prevents man-in-the-middle attacks
- SSL/TLS certificate validation
- Secure credential transmission

**Verification:**
```bash
# Test HTTP redirect
curl -I http://api.minder.local/api/health
# Should return: HTTP/1.1 308 Permanent Redirect
# Location: https://api.minder.local/api/health

# Test HTTPS connection
curl -skI https://api.minder.local/api/health
# Should return: HTTP/2 302 (auth redirect) or 200 (with auth)
```

---

## 🔒 Network Architecture

### Docker Network Configuration

**Network Name:** `docker_minder-network`
**Network Type:** Bridge
**Subnet:** 172.19.0.0/16
**Gateway:** 172.19.0.1

**Service IP Assignment:**
```
Traefik:         172.19.0.2  (only service with host ports)
Authelia:        172.19.0.3  (authentication service)
PostgreSQL:      172.19.0.4  (primary database)
Redis:           172.19.0.5  (cache)
Qdrant:          172.19.0.6  (vector database)
Neo4j:           172.19.0.7  (graph database)
RabbitMQ:        172.19.0.8  (message broker)
InfluxDB:        172.19.0.9  (time-series DB)
MinIO:           172.19.0.10 (object storage)
API Gateway:     172.19.0.14 (main API)
Plugin Registry: 172.19.0.15 (plugin service)
Marketplace:     172.19.0.16 (plugin marketplace)
... and more
```

**Network Isolation:**
- All services communicate via internal DNS (service names)
- External access only through Traefik (80/443)
- No cross-container network access violations
- Service-to-service encryption possible

---

## 🛡️ Security Layers

### Layer 1: Network Security

**Features:**
- Internal-only Docker network
- No exposed host ports
- Service discovery via Docker DNS
- Network segmentation by service type

**Configuration:**
```yaml
# docker-compose.yml
networks:
  docker_minder-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.19.0.0/16
```

### Layer 2: Reverse Proxy Security

**Traefik Configuration:**
- SSL/TLS termination
- Request routing and filtering
- Rate limiting capabilities
- IP whitelist support

**Middleware Chain:**
```yaml
# Example: API Gateway security
1. SSL/TLS (enforced)
2. Authelia ForwardAuth (authentication)
3. Strip API Prefix (URL normalization)
4. Rate Limiting (optional)
5. IP Whitelist (admin services)
```

### Layer 3: Application Security

**Authelia Features:**
- User authentication (local, LDAP, OAuth)
- Two-factor authentication (TOTP, WebAuthn)
- Session management
- Access control rules

**Access Control Examples:**
```yaml
# authelia/configuration.yml
access_control:
  default_policy: deny

  rules:
    # Domain-based access
    - domain: "api.minder.local"
      policy: one_factor
      subject:
        - ["group:developers"]

    # Admin services - 2FA required
    - domain: "grafana.minder.local"
      policy: two_factor
      subject:
        - ["group:admins"]

    # Public services (none in this architecture)
    - domain: "public.minder.local"
      policy: bypass
```

### Layer 4: Service Security

**Internal Service Authentication:**
- Service-to-service communication via internal network
- API key authentication for sensitive operations
- Database credential management via secrets
- Environment variable isolation

---

## 🔑 Authentication Methods

### Method 1: Authelia SSO (Production)

**Flow:**
```
User → Traefik → Authelia ForwardAuth → Authelia Service
                                        ↓
                                  Check Session Cookie
                                        ↓
                                  Valid? → Allow
                                  Invalid? → Redirect to Login
```

**Configuration:**
```yaml
# traefik/dynamic/authelia-middleware.yml
http:
  middlewares:
    authelia-forwardauth:
      forwardAuth:
        address: "http://minder-authelia:9091/api/verify?rd=https://auth.minder.local/"
        trustForwardHeader: true
        authResponseHeaders:
          - "Remote-User"
          - "Remote-Groups"
```

### Method 2: Direct Container Access (Development)

**Purpose:** Debugging and development only

**Methods:**
```bash
# Shell access
./setup.sh shell api-gateway

# Docker exec
docker exec minder-api-gateway curl http://localhost:8000/health

# Via container IP (from host)
curl http://172.19.0.14:8000/health
```

**⚠️ Security Note:** These methods bypass authentication and should only be used for development/debugging.

---

## 🚨 Security Considerations

### Production Deployment

**Certificate Management:**
```bash
# Current: Self-signed certificates for .local domains
# Production: Use Let's Encrypt or corporate CA

# Update traefik/dynamic/ssl-configuration.yml
tls:
  certificates:
    - certFile: /letsencrypt/production.crt
      keyFile: /letsencrypt/production.key
```

**Password Security:**
```bash
# Generate strong passwords
./setup.sh doctor --check-passwords

# Update .env file
nano infrastructure/docker/.env

# Rotate passwords regularly
./setup.sh doctor --rotate-passwords
```

**Access Control:**
```bash
# Review Authelia users
cat infrastructure/docker/authelia/users_database.yml

# Review access rules
cat infrastructure/docker/authelia/configuration.yml | grep -A 20 "access_control"

# Audit logs
docker logs minder-authelia | grep -i "audit\|access\|denied"
```

### Security Best Practices

1. **Never expose internal services on host ports**
2. **Always use HTTPS in production**
3. **Enable 2FA for all admin accounts**
4. **Rotate credentials regularly**
5. **Monitor Authelia logs for suspicious activity**
6. **Keep Traefik and Authelia updated**
7. **Use strong passwords for all services**
8. **Limit access to Docker host**
9. **Enable firewall rules for host ports 80/443 only**
10. **Regular security audits**

---

## 🔍 Security Verification

### Test 1: Verify No Exposed Ports

```bash
# Should only see Traefik with 0.0.0.0:80 and 0.0.0.0:443
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep "0.0.0.0"
```

**Expected Output:**
```
NAMES           PORTS
minder-traefik  0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

### Test 2: Verify HTTPS Redirect

```bash
curl -I http://api.minder.local/api/health
```

**Expected Output:**
```
HTTP/1.1 308 Permanent Redirect
Location: https://api.minder.local/api/health
```

### Test 3: Verify Authentication Required

```bash
curl -skI https://api.minder.local/api/health
```

**Expected Output:**
```
HTTP/2 302
Location: https://auth.minder.local/?rd=https%3A%2F%2Fapi.minder.local%2Fapi%2Fhealth
```

### Test 4: Verify Internal Network Access

```bash
# From API Gateway container
docker exec minder-api-gateway curl http://minder-postgres:5432
```

**Expected:** Connection successful (internal communication works)

### Test 5: Verify SSL/TLS Certificate

```bash
curl -vk https://api.minder.local/api/health 2>&1 | grep -i "ssl\|tls\|certificate"
```

**Expected:** SSL/TLS connection established (certificate may be self-signed)

---

## 📚 Additional Resources

- [Troubleshooting Guide](../troubleshooting/TROUBLESHOOTING.md)
- [Service Access Guide](./service-access.md)
- [Authelia Documentation](https://www.authelia.com/docs/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)

---

*Last Updated: 2026-05-10*
*Platform Version: 1.0.0*
*Security Model: Zero-Trust Network Segmentation*
*Status: Production Ready*

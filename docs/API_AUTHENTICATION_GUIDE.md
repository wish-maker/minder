# Minder Platform - API Authentication Guide

**Last Updated:** 2026-04-23 18:50
**Status:** ✅ Implemented
**Priority:** P1 - Critical (Security)

---

## Overview

API Authentication has been successfully implemented using JWT (JSON Web Tokens). All sensitive endpoints now require authentication, protecting against unauthorized access and potential abuse.

---

## Authentication Architecture

### JWT-Based Authentication

```
┌─────────┐                  ┌──────────────┐                  ┌──────────┐
│ Client  │──Login Request──▶│ API Gateway  │──Verify Creds──▶│  Auth    │
│         │                  │              │                  │ Service  │
└─────────┘                  └──────────────┘                  └──────────┘
                                    │
                                    ▼
                            ┌──────────────┐
                            │  JWT Token   │
                            │  Generated   │
                            └──────────────┘
                                    │
                                    ▼
┌─────────┐                  ┌──────────────┐                  ┌──────────┐
│ Client  │──JWT Token─────▶│ API Gateway  │──Forward Token──▶│ Plugin   │
│         │  (Bearer)       │  (Validate)  │                  │ Registry │
└─────────┘                  └──────────────┘                  └──────────┘
```

### Components

1. **JWT Middleware** (`src/shared/auth/jwt_middleware.py`)
   - Token creation and validation
   - Rate limiting per user
   - Role-based access control

2. **API Gateway** (`services/api-gateway/main.py`)
   - Central authentication endpoint
   - Token validation for proxy requests
   - Protected write operations

3. **Plugin Registry** (`services/plugin-registry/main.py`)
   - Protected sensitive endpoints
   - Audit logging for operations

---

## Protected Endpoints

### Authentication Required (Write Operations)

| Endpoint | Method | Protection | Rate Limit |
|----------|--------|------------|------------|
| `/v1/plugins/{name}/collect` | POST | JWT Required | 10 req/min |
| `/v1/plugins/{name}/enable` | POST | JWT Required | 60 req/min |
| `/v1/plugins/{name}/disable` | POST | JWT Required | 60 req/min |
| `/v1/plugins/{name}` | DELETE | JWT Required | 20 req/min |
| `/v1/plugins/install` | POST | JWT Required | 5 req/min |

### Public Endpoints (Read-Only)

| Endpoint | Method | Protection |
|----------|--------|------------|
| `/v1/plugins` | GET | Public |
| `/v1/plugins/{name}` | GET | Public |
| `/v1/plugins/{name}/health` | GET | Public |
| `/health` | GET | Public |
| `/metrics` | GET | Public |

---

## Authentication Flow

### 1. Login (Get Token)

**Request:**
```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "secure_password_123"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "username": "admin",
    "role": "admin"
  }
}
```

### 2. Use Token (Protected Endpoint)

**Request:**
```bash
curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json"
```

**Response:**
```json
{
  "message": "Data collection triggered for crypto",
  "plugin": "crypto",
  "status": "collecting",
  "triggered_by": "admin",
  "timestamp": "2026-04-23T18:50:00Z"
}
```

### 3. Refresh Token

**Request:**
```bash
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## User Roles

### Role Hierarchy

```
admin ──────▶ Full access
  │
  ├──── Can enable/disable plugins
  ├──── Can uninstall plugins
  ├──── Can trigger collection
  └──── Can manage users

operator ───▶ Operational access
  │
  ├──── Can trigger collection
  ├──── Can view plugin status
  └──── Cannot modify plugins

user ───────▶ Limited access
  │
  ├──── Can view plugins
  ├──── Can view plugin health
  └──── Read-only access
```

### Configuring Admin Users

Set `ADMIN_USERS` environment variable:

```bash
# docker-compose.yml
environment:
  - ADMIN_USERS=admin,operator,superuser
```

Or in `.env`:
```bash
ADMIN_USERS=admin,operator,superuser
```

---

## Rate Limiting

### Default Limits

| Role | Requests | Time Window |
|------|----------|-------------|
| user | 60 | 1 minute |
| operator | 100 | 1 minute |
| admin | Unlimited | - |

### Per-Endpoint Limits

- **Data Collection:** 10 requests/minute
- **Plugin Management:** 20 requests/minute
- **General:** 60 requests/minute

### Rate Limit Response

When limit exceeded:
```json
{
  "detail": "Rate limit exceeded: 10 requests per 1 minute(s)"
}
```

HTTP Status: `429 Too Many Requests`

---

## Security Best Practices

### 1. Token Storage

**Client-Side:**
- Store tokens in memory (not localStorage)
- Use httpOnly cookies in web apps
- Implement token refresh mechanism

**Example:**
```javascript
// ✅ GOOD: Memory storage
let token = null;

function login(credentials) {
  token = await api.login(credentials);
}

// ❌ BAD: localStorage
localStorage.setItem('token', token); // Vulnerable to XSS
```

### 2. Token Expiration

**Configuration:**
```bash
# .env
JWT_EXPIRATION_MINUTES=60  # Token expires in 1 hour
```

**Refresh Strategy:**
- Refresh token 5 minutes before expiration
- Implement automatic refresh in client
- Handle token expiration gracefully

### 3. HTTPS/TLS

**Production:**
- Always use HTTPS in production
- Never transmit tokens over HTTP
- Configure TLS certificates properly

### 4. Password Requirements

**Current Implementation:**
- Minimum 8 characters
- Username: minimum 3 characters

**Production Enhancement:**
```python
# TODO: Integrate with proper user database
# - Password hashing (bcrypt/argon2)
# - Password complexity requirements
# - Account lockout after failed attempts
# - Multi-factor authentication (MFA)
```

---

## Audit Logging

All authenticated operations are logged:

```
INFO:minder.plugin-registry:Data collection triggered for plugin: crypto | User: admin (admin) | Timestamp: 2026-04-23T18:50:00Z
```

**Audit Trail Includes:**
- Username and role
- Operation performed
- Timestamp (UTC)
- Resource affected

---

## Testing Authentication

### 1. Test Login

```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secure123"}' \
  | jq -r '.access_token')

echo "Token: $TOKEN"
```

### 2. Test Protected Endpoint

```bash
# Without token (should fail)
curl -X POST http://localhost:8000/v1/plugins/crypto/collect
# Response: 401 Unauthorized

# With token (should succeed)
curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer $TOKEN"
# Response: 200 OK
```

### 3. Test Rate Limiting

```bash
# Send 11 requests (limit is 10)
for i in {1..11}; do
  curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
    -H "Authorization: Bearer $TOKEN"
  echo "Request $i"
done

# Request 11 should return 429 Too Many Requests
```

---

## Client Integration Examples

### Python

```python
import requests

class MinderClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.token = None

    def login(self, username, password):
        """Authenticate and get token"""
        response = requests.post(
            f"{self.base_url}/v1/auth/login",
            json={"username": username, "password": password}
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        return self.token

    def trigger_collection(self, plugin_name):
        """Trigger data collection (protected endpoint)"""
        if not self.token:
            raise Exception("Not authenticated")

        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(
            f"{self.base_url}/v1/plugins/{plugin_name}/collect",
            headers=headers
        )
        response.raise_for_status()
        return response.json()

# Usage
client = MinderClient()
client.login("admin", "secure123")
result = client.trigger_collection("crypto")
print(result)
```

### JavaScript/TypeScript

```typescript
class MinderClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string = "http://localhost:8000") {
    this.baseUrl = baseUrl;
  }

  async login(username: string, password: string): Promise<string> {
    const response = await fetch(`${this.baseUrl}/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
      throw new Error('Login failed');
    }

    const data = await response.json();
    this.token = data.access_token;
    return this.token;
  }

  async triggerCollection(pluginName: string): Promise<any> {
    if (!this.token) {
      throw new Error('Not authenticated');
    }

    const response = await fetch(
      `${this.baseUrl}/v1/plugins/${pluginName}/collect`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.token}`,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      throw new Error('Request failed');
    }

    return response.json();
  }
}

// Usage
const client = new MinderClient();
await client.login('admin', 'secure123');
const result = await client.triggerCollection('crypto');
console.log(result);
```

---

## Troubleshooting

### Common Errors

**1. 401 Unauthorized - Missing Token**

```json
{
  "detail": "Authentication required"
}
```

**Solution:** Include `Authorization: Bearer <token>` header

**2. 401 Unauthorized - Invalid Token**

```json
{
  "detail": "Invalid token"
}
```

**Solution:** Token expired or invalid. Login again to get new token.

**3. 401 Unauthorized - Token Expired**

```json
{
  "detail": "Token has expired"
}
```

**Solution:** Refresh token or login again.

**4. 429 Too Many Requests**

```json
{
  "detail": "Rate limit exceeded: 10 requests per 1 minute(s)"
}
```

**Solution:** Wait before making more requests.

---

## Migration Guide

### For Existing API Users

**Before (No Authentication):**
```bash
curl -X POST http://localhost:8000/v1/plugins/crypto/collect
```

**After (With Authentication):**
```bash
# 1. Login and get token
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secure123"}' \
  | jq -r '.access_token')

# 2. Use token in requests
curl -X POST http://localhost:8000/v1/plugins/crypto/collect \
  -H "Authorization: Bearer $TOKEN"
```

---

## Configuration Reference

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `JWT_SECRET` | Secret key for signing tokens | - | ✅ Yes |
| `JWT_ALGORITHM` | Token signing algorithm | HS256 | No |
| `JWT_EXPIRATION_MINUTES` | Token expiration time | 60 | No |
| `ADMIN_USERS` | Comma-separated admin usernames | admin | No |

### Docker Compose Configuration

```yaml
services:
  api-gateway:
    environment:
      - JWT_SECRET=${JWT_SECRET}
      - JWT_ALGORITHM=HS256
      - JWT_EXPIRATION_MINUTES=60
      - ADMIN_USERS=admin,operator

  plugin-registry:
    environment:
      - JWT_SECRET=${JWT_SECRET}
      - JWT_ALGORITHM=HS256
      - JWT_EXPIRATION_MINUTES=60
      - ADMIN_USERS=admin,operator
```

---

## Security Checklist

Before deploying to production:

- [ ] JWT_SECRET is set to strong, unique value (64+ characters)
- [ ] JWT_SECRET different per environment (dev/staging/prod)
- [ ] HTTPS/TLS enabled for all API endpoints
- [ ] Token expiration configured appropriately
- [ ] Rate limiting enabled and tested
- [ ] Audit logging enabled and monitored
- [ ] Admin users configured
- [ ] Password requirements enforced
- [ ] Token refresh mechanism implemented
- [ ] Failed authentication attempts monitored

---

## Future Enhancements

### Planned Improvements

1. **User Database Integration**
   - PostgreSQL-based user management
   - Password hashing with bcrypt/argon2
   - Account lockout after failed attempts

2. **Multi-Factor Authentication (MFA)**
   - TOTP (Time-based One-Time Password)
   - SMS verification
   - Email verification codes

3. **OAuth 2.0 / OpenID Connect**
   - Third-party identity providers (Google, GitHub)
   - SSO (Single Sign-On) support

4. **API Key Management**
   - API key generation and rotation
   - Scoped API keys (specific endpoints)
   - API key usage analytics

5. **Advanced Rate Limiting**
   - Redis-backed distributed rate limiting
   - Per-endpoint custom limits
   - Burst allowance

---

## Support

For questions or issues:
1. Check troubleshooting section above
2. Review API logs: `docker logs minder-api-gateway --tail 100`
3. Check plugin registry logs: `docker logs minder-plugin-registry --tail 100`
4. Open issue in project repository

---

**Remember:** API authentication is critical for production security. Always use HTTPS, protect your tokens, and monitor authentication logs for suspicious activity!

# Authentication and Security

## Overview

Authentication on the Minder platform is handled by the **API Gateway**
(`minder-api-gateway`, port 8000) using **JWT** tokens with **bcrypt** password
hashing. This is the mechanism that is actually in effect today.

A single sign-on / 2FA layer (Authelia) is defined in the stack but is
**currently disabled** — see [Authelia (deferred)](#authelia-deferred) below.
There is **no role-based access control (RBAC)** implemented; access is
gated by holding a valid JWT.

> This is a development environment on a Raspberry Pi 4. Production hardening
> (enforced SSO/2FA, RBAC, TLS everywhere) has not yet been applied.

## How authentication works

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTPS
┌──────▼──────────────────┐
│      Traefik (v3)       │  reverse proxy, TLS, routing
└──────┬──────────────────┘
       │
┌──────▼──────────────────┐
│     API Gateway         │  issues + validates JWT (bcrypt password hashing)
│  /v1/auth/register      │
│  /v1/auth/login         │
│  /v1/auth/refresh       │
└──────┬──────────────────┘
       │ proxies (with bearer token)
┌──────▼──────────────────┐
│   Backend services      │
│  registry / rag / models│
└─────────────────────────┘
```

### 1. Register / obtain a token

```http
POST /v1/auth/register
Content-Type: application/json

{ "username": "alice", "password": "your-password" }
```

```http
POST /v1/auth/login
Content-Type: application/json

{ "username": "alice", "password": "your-password" }
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

### 2. Use the token

```http
GET /v1/plugins
Authorization: Bearer <access_token>
```

### 3. Refresh

```http
POST /v1/auth/refresh
Content-Type: application/json

{ "refresh_token": "..." }
```

### JWT secret

Tokens are signed with `JWT_SECRET`, which lives in the root `./.env` file (see
the [security setup guide](./security-setup.md)). `setup.sh` auto-generates a
strong value if you leave the placeholder in place. The same secret must be
consistent across services that validate tokens.

---

## Traefik (reverse proxy)

**Purpose:** single entry point, TLS termination, request routing.

- Dashboard: `http://localhost:8081` (restricted by an IP-whitelist middleware)
- Routing is driven by Docker labels (`exposedByDefault: false`)
- Configuration: `docker/services/traefik/`

Traefik has an `authelia-forwardauth` middleware wired onto five routers
(minio, api-gateway, grafana, openwebui, jaeger). The other three routers
(traefik-dashboard, rabbitmq, neo4j) use an IP-whitelist middleware instead.
Because the Authelia container is disabled, that forward-auth check is **not
enforced** — those five routes are not currently protected by SSO.

---

## Authelia (deferred)

Authelia is intended to provide centralised SSO and 2FA in front of the stack,
but it is **commented out in the compose file and does not run**. The stated
reason in the compose file:

> "TEMPORARILY DISABLED: Crash loop due to missing database and NTP sync issues.
> Decision deferred."

Whether to keep or drop Authelia is an open decision. Until it is re-enabled and
proven working, treat everything below as **planned/optional**, not active:

- Single Sign-On across services
- Two-Factor Authentication (TOTP / WebAuthn)
- Brute-force protection and session regulation
- Access-control rules per domain

If/when Authelia is brought online, its configuration would live under
`docker/services/authelia/` and it would be enabled by uncommenting its service
block in `docker/compose/docker-compose.yml`. None of that is in effect today,
so this guide does not document its per-domain rules as if they were live.

---

## Troubleshooting

### API requests return 401

- Confirm you sent `Authorization: Bearer <token>` and the token has not expired.
- Confirm `JWT_SECRET` is set consistently (see [security-setup.md](./security-setup.md)).
- Check the gateway logs:
  ```bash
  docker logs minder-api-gateway --tail 100
  ```

### Rate limited (429)

The gateway applies Redis-backed rate limiting on a 60-second window (fail-open).
Confirm Redis is healthy:
```bash
docker exec -it minder-redis redis-cli -a "$REDIS_PASSWORD" ping
```

### Cannot reach a service through Traefik

```bash
docker logs minder-traefik --tail 100
```

---

## Additional Resources

- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [Authelia Documentation](https://www.authelia.com/) (for the deferred SSO layer)
- [JWT Best Practices (RFC 8725)](https://datatracker.ietf.org/doc/html/rfc8725)

---

**Last Updated:** 2026-07-10

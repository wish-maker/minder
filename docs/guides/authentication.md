# Authentication and Security

## Overview

Authentication on the Minder platform is handled by the **API Gateway**
(`minder-api-gateway`, port 8000) using **JWT** tokens with **bcrypt** password
hashing. This is the mechanism that is actually in effect today.

A single sign-on / 2FA layer (Authelia) is also **enabled** in front of five
Traefik routers — see [Authelia (SSO / 2FA)](#authelia-sso--2fa) below.
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

{ "username": "alice", "email": "alice@example.com", "password": "your-password" }
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
  "token_type": "bearer",
  "expires_in": 1800,
  "user": { "id": 1, "username": "alice", "email": "alice@example.com", "role": "user" }
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
Authorization: Bearer <access_token>
```

### Changing your account password

There is currently no account-level password-change/reset endpoint —
`src/services/api-gateway/routes/auth.py` only implements `register`/`login`/
`refresh`. (`./setup.sh sync-postgres-password` is an unrelated *operator*
command for rotating the infra-level Postgres credential in `.env`, not an
end-user account action.) This is a real gap, not an oversight to route
around — file an issue if you need it.

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
(minio, api-gateway, grafana, openwebui, jaeger, client). The other three routers
(traefik-dashboard, rabbitmq, neo4j) use an IP-whitelist middleware instead.
The Authelia container is **enabled and running**, so that forward-auth check
**is enforced** — an unauthenticated request to those five routes gets a 302
redirect to the Authelia portal.

---

## Authelia (SSO / 2FA)

Authelia provides centralised SSO and 2FA in front of the stack and is
**enabled and running** (`docker/docker-compose.yml`, service `authelia`).
Its configuration lives under `docker/services/authelia/`
(`configuration.yml`, `users_database.yml`).

The Traefik `authelia-forwardauth` middleware enforces it on five routers
(minio, api-gateway, grafana, openwebui, jaeger, client): an unauthenticated request
is 302-redirected to the Authelia portal. Full browser SSO still needs real
DNS + TLS on the deploy.

- Single Sign-On across services — **active**
- Two-Factor Authentication (TOTP / WebAuthn) — available per Authelia's config
- Brute-force protection and session regulation — Authelia defaults
- Access-control rules per domain — see `configuration.yml`'s `access_control` section

### Rotating the admin password

`docker/services/authelia/users_database.yml` is a **tracked file** — every
clone of this repo ships the exact same `admin` account with the exact same
password hash. That password is not written down anywhere (the file only
holds a one-way argon2id hash), but it is still a single **shared secret
identical across every Minder install** until you change it — treat it the
same as any other default credential and rotate it before exposing this
instance to any network beyond your own machine:

```bash
docker exec minder-authelia authelia crypto hash generate argon2 \
  --memory 32768 --iterations 3 --parallelism 2 --password '<your new password>'
```

Paste the resulting `$argon2id$…` string over the `password:` value in
`users_database.yml`, then `docker compose restart authelia` (or
`bash setup.sh restart`) to apply it. There is currently no `setup.sh`
verb that automates this — it's a manual step you need to remember to do.

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
- [Authelia Documentation](https://www.authelia.com/) (the SSO/2FA layer in front of the stack)
- [JWT Best Practices (RFC 8725)](https://datatracker.ietf.org/doc/html/rfc8725)

---

**Last Updated:** 2026-07-10

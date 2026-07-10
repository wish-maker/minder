# Security Architecture

**Last Updated:** 2026-07-10
**Platform Version:** 1.0.0
**Environment:** Development (Raspberry Pi 4)

---

> **This describes the current, real security posture — plus the intended target where
> features are not yet enabled.** Development-environment caveats are called out inline.
> Production hardening has not yet been fully applied.

---

## Summary of the Current Posture

- **Reverse proxy:** Traefik v3.7.7 (TLS termination, routing via Docker labels,
  `exposedByDefault: false`). There is **no Nginx** in this stack.
- **Authentication:** The **API Gateway** implements real JWT (HS256) authentication with
  bcrypt-hashed credentials, plus Redis-backed rate limiting (60s window, fail-open).
- **SSO / Authelia:** **DISABLED.** The Authelia service is commented out in compose. Traefik
  has a `authelia-forwardauth` middleware referenced on a few routers, but because the
  container is down the middleware does **not** enforce anything. Keep-vs-drop is an open
  decision.
- **RBAC:** **Not implemented.** Only JWT authentication exists on the gateway; there is no
  role-based access control.
- **Network:** Services communicate over Docker networks by container name. Some application
  and observability services publish host ports directly (see
  [Service Access Guide](./service-access.md)); storage backends are internal-only.
- **Secrets:** Root `./.env` is the single source of truth (permissions `600`); setup.sh
  mirrors it to `docker/compose/.env`.

---

## Reverse Proxy (Traefik v3)

Traefik is the single ingress. It terminates TLS and routes by Docker labels. Only services
that carry Traefik router labels are exposed through it (`exposedByDefault: false`).

```yaml
# Only Traefik binds the public host ports
traefik:
  image: traefik:v3.7.7
  ports:
    - "80:80"
    - "443:443"
    - "8081:8081"   # dashboard, IP-whitelisted
```

Capabilities in use:
- TLS termination (self-signed certificates for `.local` domains in this environment).
- HTTP→HTTPS redirect for routed hosts.
- Router-level middleware, including IP whitelisting on admin routes (Traefik dashboard,
  RabbitMQ management, Neo4j browser).

> **Note:** Some services also publish their own host ports directly and are therefore
> reachable without going through Traefik. This is acceptable for a development environment
> but is not a locked-down production posture.

---

## Authentication

### API Gateway JWT (real, in use)

The API Gateway is the only service with application-level authentication:

- JWT bearer tokens (HS256), issued at `POST /auth/login`.
- Credentials stored as bcrypt hashes.
- Redis-backed rate limiting: 60-second window, **fail-open** (if Redis is unreachable,
  requests are allowed through).

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}'

curl -H "Authorization: Bearer <token>" http://localhost:8000/health
```

### Authelia SSO (disabled)

Authelia is **defined but disabled** (commented out in compose). It was intended to provide
SSO/2FA in front of web services via a Traefik `forwardAuth` middleware. Because the
container does not run, any router referencing that middleware currently passes traffic
through **without** authentication. Whether to keep and wire Authelia or drop it is an open
platform decision.

### RBAC (not implemented)

There is no role-based access control. Do not assume per-role or per-group authorization is
enforced — only the gateway's JWT check exists today.

---

## Network Model

- Services attach to the `minder-network` Docker network and resolve each other by container
  name via Docker DNS. A second `minder-monitoring` network is prepared/attachable.
- Storage backends (postgres, redis, qdrant, neo4j, minio, rabbitmq, schema-registry) and
  the metric exporters are **internal-only** — no host port.
- Application and observability services (API core 8000–8006/8008, Grafana, Prometheus,
  Alertmanager, InfluxDB, Jaeger, OTel Collector) and Traefik publish host ports.

See the [Service Access Guide](./service-access.md) for the authoritative port map.

---

## Secrets Management

- **Single source of truth:** root `./.env`. Edit this file only.
- setup.sh **mirrors** it to `docker/compose/.env` on start/restart. Do not edit the mirror.
- File permissions are kept at `600`.
- There is **no** file-secrets overlay and **no** multi-environment layering (removed);
  `.env` is the single mechanism.

```bash
# Edit the root env file
nano .env

# Changing an ALREADY-RUNNING stateful secret (e.g. POSTGRES_PASSWORD) does not rotate the
# live credential by itself — the database keeps the old one. After editing, run:
bash setup.sh sync-postgres-password
```

Never commit `.env` files containing real secrets.

---

## Security Considerations & Roadmap

This is a development deployment. Before treating it as production-ready:

1. Decide and (if kept) actually enable Authelia SSO so routed services are gated.
2. Lock down host-published ports; front everything through the proxy.
3. Replace self-signed `.local` certificates with a real CA / Let's Encrypt.
4. Implement authorization (RBAC) beyond the gateway's JWT check if multi-tenant/role
   separation is required.
5. Rotate credentials via `./.env` (and `sync-postgres-password` for stateful ones).
6. Keep Traefik and images updated.

---

## Additional Resources

- [Service Access Guide](./service-access.md)
- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [Authelia Documentation](https://www.authelia.com/docs/) (for the deferred SSO rollout)

---

*Last Updated: 2026-07-10 · Development environment · Reverse proxy: Traefik v3 · SSO: disabled · RBAC: not implemented*

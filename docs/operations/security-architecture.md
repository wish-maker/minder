# Security Architecture

**Last Updated:** 2026-08-11
**Platform Version:** 1.0.0
**Environment:** Development (Raspberry Pi 4)

---

> **This describes the current, real security posture — plus the intended target where
> features are not yet enabled.** Development-environment caveats are called out inline.
> Production hardening has not yet been fully applied.

---

## Summary of the Current Posture

- **Reverse proxy:** Traefik v3.7.10 (TLS termination, routing via Docker labels,
  `exposedByDefault: false`). There is **no Nginx** in this stack.
- **Authentication:** The **API Gateway** implements real JWT (HS256) authentication with
  bcrypt-hashed credentials, plus Redis-backed rate limiting (60s window, fail-open).
  Authelia is now a real **OIDC identity provider** for this JWT, not just a forward-auth
  gate — see below.
- **SSO / Authelia:** **ENABLED**, and now a genuine identity source, not only forward-auth.
  Traefik's `authelia-forwardauth` middleware is referenced on **six** routers (minio,
  api-gateway, grafana, openwebui, jaeger, client) and enforces SSO — unauthenticated
  requests get a 302 redirect to the Authelia portal. Separately, the client's single
  "Log in" button drives a real OIDC authorization-code flow (`/v1/auth/oidc/login` →
  Authelia → `/v1/auth/oidc/callback`), so a Minder JWT is now minted from a verified
  Authelia identity, not a locally-registered account, for anyone who logs in through the UI.
- **RBAC:** **Not enforced.** `role` is now populated from Authelia's `groups` claim
  (`admins` group → `admin` role) instead of only ever defaulting to `"user"`, but nothing
  in the codebase checks it before permitting an action — every write-protected endpoint
  still only checks "is there a valid JWT," not "does this JWT's role permit this." Tracked
  as [#474](https://github.com/wish-maker/minder/issues/474).
- **Network:** Services communicate over Docker networks by container name. Some application
  and observability services publish host ports directly (see
  [Service Access Guide](./service-access.md)); storage backends are internal-only.
- **Secrets:** Root `./.env` is the single source of truth (permissions `600`); setup.sh
  mirrors it to `docker/.env`.

---

## Reverse Proxy (Traefik v3)

Traefik is the single ingress. It terminates TLS and routes by Docker labels. Only services
that carry Traefik router labels are exposed through it (`exposedByDefault: false`).

```yaml
# Only Traefik binds the public host ports
traefik:
  image: traefik:v3.7.10
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

> **Note:** Some services also publish their own host ports directly, bound to
> `127.0.0.1` — reachable without going through Traefik (and therefore without Authelia's
> forward-auth gate) by anything with a shell on the host, or an SSH port-forward to it, but
> **not** from the wider network. This is acceptable for a development environment but is
> not a locked-down production posture. Tracked as
> [#472](https://github.com/wish-maker/minder/issues/472).

---

## Authentication

### API Gateway JWT (real, in use)

The API Gateway is the only service with application-level authentication:

- JWT bearer tokens (HS256), issued at `POST /v1/auth/login`.
- Credentials stored as bcrypt hashes.
- Redis-backed rate limiting: 60-second window, **fail-open** (if Redis is unreachable,
  requests are allowed through).

```bash
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}'

curl -H "Authorization: Bearer <token>" http://localhost:8000/health
```

### Authelia SSO (enabled — now a real identity provider)

Authelia is **enabled and running**, providing SSO/2FA in front of web services via a
Traefik `forwardAuth` middleware wired onto six routers (minio, api-gateway, grafana,
openwebui, jaeger, client). Requests to those routers are 302-redirected to the Authelia
portal when unauthenticated.

Separately from that gate, api-gateway is now a confidential OIDC client of Authelia's own
identity provider (`identity_providers.oidc` in `docker/services/authelia/configuration.yml`):

- `GET /v1/auth/oidc/login` redirects the browser to Authelia's authorization endpoint.
- `GET /v1/auth/oidc/callback` exchanges the returned code for a verified ID token, resolves
  it to a Minder user (creating or linking one on first login — see
  `core/auth.py`'s `get_or_create_oidc_user`), and mints the same JWT shape
  `/v1/auth/login` always has.

This is what the client's single "Log in" button in the topbar drives — end users
authenticate against Authelia directly and never see a Minder-specific login form. The
local `/v1/auth/register` + `/v1/auth/login` endpoints below still exist (useful for
scripting/dev), but are no longer the primary path a real user takes.

### RBAC (not enforced)

`role` is derived from Authelia's `groups` claim on every OIDC login (`admins` group →
`admin` role, else `"user"`) and stored on the user row / JWT, but **nothing checks it**
before permitting an action — do not assume per-role or per-group authorization is
enforced. Every write-protected endpoint still only checks "is there a valid JWT," not "does
this JWT's role permit this." Tracked as
[#474](https://github.com/wish-maker/minder/issues/474).

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
- setup.sh **mirrors** it to `docker/.env` on start/restart. Do not edit the mirror.
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

1. ~~Complete Authelia's rollout so browser SSO works end-to-end~~ — **done**: real OIDC
   SSO now mints Minder's own JWT from a verified Authelia identity (see above).
2. Lock down host-published ports; front everything through the proxy
   ([#472](https://github.com/wish-maker/minder/issues/472)).
3. Replace self-signed `.local` certificates with a real CA / Let's Encrypt.
4. Implement authorization (RBAC) beyond "is there a valid JWT" — `role` already exists and
   is populated from Authelia's groups, it just isn't checked anywhere yet
   ([#474](https://github.com/wish-maker/minder/issues/474)).
5. Rotate credentials via `./.env` (and `sync-postgres-password` for stateful ones). Also
   rotate Authelia's own admin credential, which currently ships identical across every
   clone of this repo ([#473](https://github.com/wish-maker/minder/issues/473)).
6. Keep Traefik and images updated.

---

## Additional Resources

- [Service Access Guide](./service-access.md)
- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [Authelia Documentation](https://www.authelia.com/docs/) (for the SSO rollout)

---

*Last Updated: 2026-08-11 · Development environment · Reverse proxy: Traefik v3 · SSO: enabled, real OIDC (Authelia) · RBAC: not enforced*

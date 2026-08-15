# Authentication and Security

## Overview

Minder has a **single login entry point**: the "Log in" button in the top-right of the
client UI. Clicking it takes you to Authelia's own login page (the platform's identity
provider), and coming back mints a Minder session automatically — there is no separate
Minder-specific username/password form to fill in, and no scattered per-page login boxes.

Under the hood: Authelia issues a verified identity via **OIDC**, the **API Gateway**
(`minder-api-gateway`, port 8000) exchanges that for its own **JWT**, and every other
service trusts that JWT. Authelia also still gates several other web UIs (Grafana,
OpenWebUI, MinIO, Jaeger) directly at the reverse-proxy layer, independent of Minder's own
login — see [Authelia](#authelia-sso--2fa--oidc-identity-provider) below.

Role checks (#474) cover a specific set of admin-only actions today (model pull/
delete/fine-tune, bundle enable/disable/reconcile, listing a plugin's
installations) — most other endpoints that require auth still only check
"is there a valid JWT," not the role it carries. See [Roles](#roles-partially-enforced)
below.

> This is a development environment on a Raspberry Pi 4 / self-hosted deployment.
> Production hardening (RBAC across the rest of the write surface, TLS everywhere)
> has not yet been fully applied.

## How authentication works (browser login)

```
┌─────────────┐   1. click "Log in"    ┌──────────────────────┐
│   Client    ├───────────────────────▶│  GET /v1/auth/oidc/  │
│  (browser)  │                        │  login (api-gateway) │
└──────▲──────┘                        └──────────┬───────────┘
       │                                           │ redirect
       │ 4. #token=<minder-jwt>                    ▼
       │                                ┌──────────────────────┐
       │                                │  Authelia login page │
       │                                │  (SSO session reused │
       │                                │  if you're already   │
       │                                │  logged in elsewhere)│
       │                                └──────────┬───────────┘
       │                                           │ authorization code
       │           3. verify + mint Minder JWT     ▼
       └────────────────────────────────GET /v1/auth/oidc/callback
                                        (api-gateway ↔ Authelia,
                                         server-to-server)
```

1. The client's "Log in" button links straight to `GET /v1/auth/oidc/login`.
2. That redirects your browser to Authelia. If you already have an Authelia session
   (e.g. you're logged into Grafana/OpenWebUI, or the client's own forward-auth gate
   already established one), this step can complete silently with no extra prompt.
3. Authelia redirects back with an authorization code. api-gateway exchanges it for a
   verified identity (`core/oidc.py`), then looks up or provisions a matching Minder user
   (`core/auth.py`'s `get_or_create_oidc_user` — first login creates the account, or links
   it to a pre-existing local account with the same username. Every login syncs
   username/email/role from Authelia's `groups` claim, including the very first one that
   links a pre-existing local account — a user promoted to Authelia's `admins` group gets
   `role: admin` starting with that first SSO login, not just from the second one onward).
4. api-gateway mints a normal Minder JWT and redirects your browser to
   `/auth/callback#token=...`. The client reads the token from the URL fragment (never sent
   to any server, so it never lands in an access log) and you're logged in.

From here, every API call the client makes carries that JWT the same way it always has:

```http
GET /v1/plugins
Authorization: Bearer <access_token>
```

### Your account

Click your username (top-right, once logged in) to open **Settings** — it shows your
username, email, and role as Minder sees them, and a "Log out" button. Because your real
account lives in Authelia, actual profile/password changes happen there, not in Minder;
Settings links straight to Authelia's own portal for that.

### Local register/login (still available, mainly for scripting/dev)

The original username/password endpoints still exist and mint the exact same JWT shape —
useful for scripts, CI, or local dev without going through a browser — but the UI no longer
exposes a form for them:

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

**Response (same shape from either login path):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": { "id": 1, "username": "alice", "email": "alice@example.com", "role": "user" }
}
```

```http
POST /v1/auth/refresh
Authorization: Bearer <access_token>
```

There is still no account-level password-change/reset endpoint for locally-registered
accounts — `src/services/api-gateway/routes/auth.py` only implements
`register`/`login`/`refresh`/`oidc/login`/`oidc/callback`. (`./setup.sh
sync-postgres-password` is an unrelated *operator* command for rotating the infra-level
Postgres credential in `.env`, not an end-user account action.) If you need this, log in via
Authelia instead — its own portal has real password management.

### Roles (partially enforced)

Logging in via Authelia sets your Minder `role` from Authelia's `groups` claim: membership
in the `admins` group becomes `role: admin`, everyone else gets `role: user`. You can see
your own role on the Settings page. `require_role()`/`require_role_or_service()` (#474)
check this role before permitting a specific set of admin-only actions: a model pull/
delete/fine-tune, a bundle enable/disable/reconcile, and listing who installed a
marketplace plugin. Everywhere else that requires auth still only checks "is there a
valid JWT," not "does this JWT's role allow it" — don't build workflows that assume
broader per-role restrictions are enforced than that.

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

Traefik has an `authelia-forwardauth` middleware wired onto six routers
(minio, api-gateway, grafana, openwebui, jaeger, client). The other three routers
(traefik-dashboard, rabbitmq, neo4j) use an IP-whitelist middleware instead.
The Authelia container is **enabled and running**, so that forward-auth check
**is enforced** — an unauthenticated request to those six routes gets a 302
redirect to the Authelia portal.

This forward-auth gate is separate from (and composes with) the OIDC login flow described
above: the client router being forward-auth-gated is *why* step 2 of that flow can complete
silently — visiting the client at all already required an Authelia session, so clicking
Minder's own "Log in" button rarely prompts again.

---

## Authelia (SSO / 2FA / OIDC identity provider)

Authelia is Minder's identity provider and is **enabled and running**
(`docker/docker-compose.yml`, service `authelia`). Its configuration lives under
`docker/services/authelia/` (`configuration.yml`, `users_database.yml`).

Two independent things both come from Authelia:

1. **Forward-auth gate** — the Traefik `authelia-forwardauth` middleware enforces a login
   on six routers (minio, api-gateway, grafana, openwebui, jaeger, client): an
   unauthenticated request is 302-redirected to the Authelia portal.
2. **OIDC identity provider** — api-gateway is a registered OIDC client
   (`identity_providers.oidc` in `configuration.yml`); this is what mints your actual Minder
   JWT when you click "Log in" (see the flow diagram above).

Full browser SSO still needs real DNS + TLS on the deploy.

- Single Sign-On across services — **active**
- OIDC-based Minder login (this doc's main flow) — **active**
- Two-Factor Authentication (TOTP / WebAuthn) — available per Authelia's config
- Brute-force protection and session regulation — Authelia defaults
- Access-control rules per domain — see `configuration.yml`'s `access_control` section

### The admin password

`docker/services/authelia/users_database.yml` is a **tracked template** —
it holds a placeholder, not a real hash. `setup.sh start`/`install` generates
a random `MINDER_AUTHELIA_ADMIN_PASSWORD` in `.env` on first run (same
self-healing SECRET_SPEC mechanism as every other secret — `JWT_SECRET`,
`POSTGRES_PASSWORD`, etc.), argon2id-hashes it via Authelia's own CLI, and
writes the real value into `users_database.rendered.yml` (gitignored, the
file `docker-compose.yml` actually mounts). Every deployment gets its own
password instead of the one hardcoded value every clone used to share (#473).

**The plaintext is printed to the terminal exactly once**, the moment it's
generated — record it then, since it is never shown again and is never
written to a log file:

```
┌──────────────────────────────────────────────────┐
│  🔑 Authelia Admin Password (generated)           │
└──────────────────────────────────────────────────┘
⚠ Record this now -- it will not be shown again.
  Username: admin
  Password: <random>
```

If you lose it, rotate: clear the `MINDER_AUTHELIA_ADMIN_PASSWORD` line in
`.env` and re-run `bash setup.sh start` (or set
`MINDER_ALLOW_SECRET_REGEN=1` first if the stack is already running — see
`docs/guides/security-setup.md`'s secret-rotation section) to generate and
print a new one.

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

**Last Updated:** 2026-08-11

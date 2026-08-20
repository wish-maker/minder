# api-gateway

The single front door to Minder's backend (`:8000`, FastAPI). Everything a
browser/client talks to goes through here: it authenticates (JWT + optional
Authelia OIDC/SSO), rate-limits, and reverse-proxies to the downstream services
over the internal `minder-network`. ~2k LOC. Interactive docs at `/docs`.

No downstream service is reachable from a browser directly (they're loopback +
internal-only, #190) — the gateway is the only public API surface.

## Run / check

```bash
bash setup.sh start api-gateway     # needs redis (rate limit) + the downstreams it proxies

curl http://localhost:8000/health           # gateway + a fan-out of downstream health
curl http://localhost:8000/v1/status         # every core service's /health over the internal network

python scripts/dev/dev.py mypy api-gateway
DB_PASSWORD=x JWT_SECRET=<32ch> REDIS_PASSWORD=x python -m pytest tests/unit/test_api_gateway_*.py tests/integration/test_api_gateway.py
```

## What it does

- **Auth** (`routes/auth.py`, `core/auth.py`, `core/oidc.py`): local
  username/password → JWT (`POST /v1/auth/login` + `/register`, bcrypt), and the
  Authelia OIDC/SSO flow (`/v1/auth/oidc/login` → callback → the SAME Minder JWT
  shape, so nothing downstream changes). A disabled account → 403.
- **Rate limiting** (`core/middleware.py`): Redis-backed fixed-window
  (`RATE_LIMIT_PER_MINUTE`, default 60), keyed by the **real client IP** (+ the
  JWT caller identity when present, #901), **fail-open** (Redis down → requests
  pass). Over the limit → **429** with the standard `{"detail": ...}` body + a
  `Retry-After` header (#541). The real client IP is recovered from
  `X-Forwarded-For` via a **trusted-proxy CIDR allowlist** (`TRUSTED_PROXY_CIDRS`,
  #749): XFF is honoured only when the connecting peer is inside a trusted CIDR,
  so a forged header on a direct connection can't spoof the key (`shared/net/
  trusted_proxy.py`). Behind Traefik the peer is always the proxy, so without
  this every caller collapsed into one shared bucket.
- **Proxy** (`routes/proxy.py`): httpx passthrough to the downstreams. Reads
  (GET) are open (Authelia's job at the edge, #15); **writes (POST/PUT/DELETE/
  PATCH) require a valid JWT** (`_require_jwt_for_writes`, #47). Path prefixes:
  `/v1/rag/*` → rag-pipeline, `/v1/plugins/*` → plugin-registry, `/v1/models/*` →
  model-management, `/v1/marketplace/*` → marketplace, `/v1/tools/*` +
  `/v1/licensing/*` → plugin-state-manager, `/v1/bundles/*` + `/v1/containers/*` →
  plugin-registry, `/v1/tts|stt` → tts-stt, `/v1/graph-rag/*` → graph-rag. A malformed downstream
  path 404s cleanly; an unreachable downstream → 503 (never a hang). Every
  proxied request body is capped at `MAX_PROXY_BODY_SIZE_MB` (default 150MB,
  **413** once exceeded) — a gateway-level ceiling above every real downstream
  limit (e.g. rag-pipeline's own 50MB upload cap), read via `request.stream()`
  so a large/malicious upload can't exhaust gateway memory before any
  downstream check is ever consulted.
- **AI / OpenWebUI bridge** (`routes/ai.py`): `POST /v1/ai/chat/completions`
  (Ollama chat; plugin function-calling is opt-in via `"minder_tools": true` —
  the gateway offers plugin tools, executes the model's `tool_calls` forwarding
  the caller's JWT, and feeds results back), plus `/v1/ai/functions/definitions`
  and `/v1/ai/functions/{name}`.
- **Ops** (`routes/health.py`): `/health`, `/v1/status` (fan-out, never 500s
  even if every downstream is down), `/v1/containers/{name}/logs` (JWT-gated,
  allowlisted, via the docker-socket-proxy), `/metrics`.

## Layout

```
api-gateway/
├── main.py               # thin app: middleware + include routers + global exception handler
├── routes/
│   ├── auth.py           # /v1/auth/* — local login/register + OIDC login/callback
│   ├── proxy.py          # /v1/{rag,plugins,models,marketplace,tools,bundles,...}/{path} passthrough
│   ├── ai.py             # /v1/ai/* — Ollama chat + plugin function-calling bridge
│   └── health.py         # /health, /v1/status, /v1/containers/{name}/logs, /metrics
├── core/
│   ├── auth.py           # JWT create/verify, bcrypt, user lookup (403 on disabled)
│   ├── middleware.py     # Redis rate-limit middleware (fail-open, Retry-After)
│   ├── oidc.py           # Authelia OIDC exchange → Minder JWT
│   └── clients.py        # httpx client + downstream URL map
└── config.py             # Settings (rate-limit, CORS, Authelia URLs, downstream URLs)
```

## Configuration (`config.py`, env-overridable)

- `RATE_LIMIT_ENABLED` (default true), `RATE_LIMIT_PER_MINUTE` (60), `RATE_LIMIT_BURST` (100).
- `TRUSTED_PROXY_CIDRS` (#749) — comma-separated CIDR allowlist of trusted reverse proxies; `X-Forwarded-For` is honoured only from a peer inside these ranges. Default trusts loopback + RFC1918 (Docker's dynamic bridge pool; `minder-network` has no pinned subnet). Tighten to Traefik's exact subnet in a fixed-network deployment.
- `CORS_ALLOWED_ORIGINS` (default `*` — the gateway is the public surface). Pairing a
  wildcard origin with `allow_credentials=True` is refused: the shared CORS helper
  (`shared/utils/cors.py`) forces `allow_credentials=False` whenever origins include `*`,
  so a cross-origin credentialed request (cookies attached/read back) is never possible
  even with this wildcard default. Auth here is Bearer-token in the `Authorization`
  header, not cookies, so this has no effect on normal client usage.
- `AUTHELIA_ISSUER_URL` / `AUTHELIA_INTERNAL_URL` (OIDC), `MINDER_CLIENT_BASE_URL` (post-login redirect target).
- Downstream URLs (`MODEL_MANAGEMENT_URL`, …) — the internal service hostnames.
- Secrets (`DB_PASSWORD` / `REDIS_PASSWORD` / `JWT_SECRET`) from `MinderBaseSettings`, required.

## Error conventions

Follows the platform-wide `{"detail": ...}` shape and the 4xx-for-bad-input /
sanitized-5xx rules — see **[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_api_gateway_*.py` (proxy headers, chat error handling) +
`tests/integration/test_api_gateway.py` (proxy routing, rate-limit blocking incl.
the 429 shape + Retry-After). The `RATE_LIMIT_ENABLED=false` default in
`tests/conftest.py` keeps the shared in-process gateway from tripping a real 429
across unrelated tests (#333); the rate-limit test uses a separate app with it on.

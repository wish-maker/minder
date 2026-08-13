# Minder Services

The nine services that make up the Minder platform — eight FastAPI microservices
plus the React management SPA. Each directory has its own README with endpoints,
config, layout, and tests; this page is the map.

## The services

| Service | Port | What it does |
|---------|------|--------------|
| [api-gateway](api-gateway/README.md) | `:8000` | The single public API surface — JWT/OIDC auth, Redis rate limiting, httpx proxy to the downstreams |
| [plugin-registry](plugin-registry/README.md) | `:8001` | Plugin lifecycle + actions, service discovery, the bundle capability control-plane |
| [marketplace](marketplace/README.md) | `:8002` | Plugin/tool catalog, license tiers, Neo4j dependency graph |
| [plugin-state-manager](plugin-state-manager/README.md) | `:8003` | Plugin enable/disable state + license-gated AI-tool execution |
| [rag-pipeline](rag-pipeline/README.md) | `:8004` | Chunk/embed/retrieve + generate — Minder's own RAG (standard/HyDE/Self-RAG/…) |
| [model-management](model-management/README.md) | `:8005` | Ollama model lifecycle (list/pull/delete/test) |
| [tts-stt](tts-stt/README.md) | `:8006` | Text-to-speech (Piper offline / gTTS fallback) + speech-to-text |
| [graph-rag](graph-rag/README.md) | `:8008` | spaCy NER → Neo4j knowledge-graph construction + retrieval |
| [client](client/README.md) | `:8009` | The management SPA (React 18 + Vite + Tailwind) — the ONE non-Python service |

> `:8007` is intentionally absent — `model-fine-tuning` was removed on purpose
> (do NOT re-add), along with `ai-service`.

Every non-Traefik host port binds to `127.0.0.1` (#190): reachable on the host for
ops/health, but external access is Traefik-only (Authelia-gated). See the root
`.claude/CLAUDE.md` for the full platform service map and
`docs/architecture/bundles.md` for the bundle model.

## Conventions shared across the eight Python services

- **Thin `main.py`** — app assembly only (lifespan + include routers). Logic lives
  in `routes/` (HTTP) + `core/`/`domain/`/`repositories/` (behaviour). All eight
  conform.
- **Versioned + legacy paths** — every route is served at both `/v1/...` and the
  unversioned path (an alias, not a redirect — a redirect would drop the body on
  non-GET clients, #147).
- **Error handling** — the platform-wide `{"detail": ...}` shape, 4xx for bad
  input, sanitized 5xx (never raw `str(exc)` outside dev), backend-down → 503. Full
  rules in [`docs/api/reference.md`](../../docs/api/reference.md).
- **Config** — most services take secrets from the shared `MinderBaseSettings`
  (`DB_PASSWORD`/`REDIS_PASSWORD`/`JWT_SECRET`, required — no weak defaults).
  Self-contained services (`model-management`, `graph-rag`, `tts-stt`) use a plain
  `BaseSettings` (Ollama / Neo4j+spaCy / voices only). `marketplace` deliberately
  diverges (own DB namespace + fully-qualified imports, #223) — don't standardize
  it away.
- **Shared code** — cross-cutting concerns (JWT, CORS, metrics, config, redis,
  DB-pool, errors, logging) live in [`../shared/`](../shared/), not copied per
  service (#49).

## Local checks (mirror CI)

```bash
python scripts/dev/dev.py mypy <service>      # per-service mypy (each svc its own import root)
python scripts/dev/dev.py lint <paths>        # black + isort + flake8
DB_PASSWORD=x JWT_SECRET=<32ch> REDIS_PASSWORD=x python -m pytest tests/unit/test_<service>_*.py
```

Unit tests load every service into ONE process (`tests/conftest.py`), so
hyphenated-service modules are loaded by-path — see the harness note at the top of
each service's test file. `src/plugins/` is out of CI lint/type scope by design.

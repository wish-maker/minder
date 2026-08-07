# Minder Shared Components

Reusable utilities, models, and configuration shared across Minder platform services.

## 📦 Overview

This package reduces duplication and enforces consistency across services:
- **Reduce code duplication** — share utilities instead of rewriting them per service
- **Ensure consistency** — one implementation for CORS, metrics, JWT, Redis, config
- **Improve maintainability** — update once, apply everywhere

## 🔌 Import path

Services copy `src/shared` into their image at `/app/src/shared` and put `/app/src`
on `sys.path`, so the import root is **`shared`** (NOT `services.shared`):

```python
from shared.config.base_settings import MinderBaseSettings
from shared.models import HealthCheckResponse, SuccessResponse, ErrorResponse, LicenseTier
from shared.utils.redis_client import create_redis_client_from_settings
from shared.utils.cors import add_cors_middleware
from shared.metrics import setup_metrics
from shared.auth.jwt_middleware import get_current_user, create_jwt_token
from shared.ai.tool_validator import validate_ai_tools
from shared.log import setup_logging
from shared.health import DependencyCheck, evaluate_dependencies
from shared.errors import backend_http_error
from shared.pagination import paginate
from shared.db.pool import create_pg_pool
from shared.db.schema import apply_schema
```

> Each module that imports `shared.*` guards the path first (main.py inserts it once;
> modules imported before that add an idempotent guard):
> ```python
> import sys
> if "/app/src" not in sys.path:
>     sys.path.insert(0, "/app/src")
> from shared.utils.redis_client import create_redis_client_from_settings  # noqa: E402
> ```

## 📁 Package structure

```
src/shared/
├── __init__.py
├── README.md
├── log.py                    # setup_logging(service_name): minder.<name> logger convention
├── health.py                 # DependencyCheck + evaluate_dependencies(): shared health-probe aggregation
├── errors.py                 # backend_http_error(exc, op): sanitized 503/500 from a caught exception
├── pagination.py              # paginate(items, limit, offset) -> (page, total)
├── metrics.py                # setup_metrics(app): request middleware + /metrics
├── bundle_graph.py           # pure bundle claim-graph brain shared by setup CLI + registry API (#65)
├── config/
│   ├── __init__.py           # exports MinderBaseSettings
│   └── base_settings.py      # base BaseSettings (required secrets, no weak defaults)
├── db/
│   ├── __init__.py
│   ├── pool.py                # create_pg_pool(...): asyncpg pool + optional CREATE DATABASE
│   └── schema.py               # apply_schema(pool, sql_path): run a service's schema.sql at startup
├── models/
│   ├── __init__.py           # exports the response models + license-tier vocabulary below
│   ├── responses.py          # standard Pydantic response envelopes
│   └── tiers.py               # LicenseTier / normalize_tier / tier_rank: canonical tier vocabulary (#142)
├── utils/
│   ├── __init__.py           # exports cors + redis_client helpers
│   ├── cors.py               # add_cors_middleware
│   └── redis_client.py       # create_redis_client, create_redis_client_from_settings
├── auth/
│   ├── __init__.py           # (empty — import from submodule)
│   └── jwt_middleware.py     # JWT create/verify + auth dependencies + rate limiting
└── ai/
    ├── __init__.py           # (empty — import from submodule)
    └── tool_validator.py     # validate_ai_tools(manifest)
```

> `auth/__init__.py` and `ai/__init__.py` are intentionally empty — import from the
> submodule directly (`from shared.auth.jwt_middleware import ...`).

## 🔧 Components

### Configuration — `config/base_settings.py`

`MinderBaseSettings` is a `pydantic-settings` base with the common DB/Redis/JWT/CORS
fields. **Secrets (`DB_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`) are REQUIRED** — no
defaults — and validated at load time, so a service can never boot with a placeholder
secret. Extend it with service-specific fields:

```python
from shared.config.base_settings import MinderBaseSettings

class Settings(MinderBaseSettings):
    SERVICE_PORT: int = 8002

settings = Settings()   # raises if DB_PASSWORD / REDIS_PASSWORD / JWT_SECRET are unset
```

### Models — `models/responses.py`

Standard response envelopes, all importable from `shared.models`:

`SuccessResponse`, `ErrorResponse`, `PaginatedResponse`, `HealthCheckResponse`,
`DetailedHealthCheck`, `CreateResponse`, `UpdateResponse`, `DeleteResponse`,
`BatchOperationResponse`, `ValidationErrorResponse`, `ConfigurationResponse`.

```python
from shared.models import HealthCheckResponse

@app.get("/health", response_model=HealthCheckResponse)
async def health():
    return HealthCheckResponse(service="marketplace", status="healthy", version="1.0.0")
```

### License tiers — `models/tiers.py`

`LicenseTier` is the canonical `{free, community, pro, enterprise}` vocabulary shared
between marketplace and plugin-state-manager (#142 — the two services previously used
different tier sets, so a marketplace-issued `"professional"` license either crashed or
silently fail-opened a paid tool to everyone in the state-manager's gate).
`normalize_tier`/`tier_rank` accept a raw string, a `LicenseTier`, or the deprecated
`"professional"` alias (→ `PRO`) and raise `ValueError` for anything else:

```python
from shared.models import LicenseTier, normalize_tier, tier_rank

user_tier = normalize_tier(license.tier)          # tolerates "professional" -> PRO
if tier_rank(user_tier) < tier_rank(LicenseTier.PRO):
    raise HTTPException(403, "requires a pro license")
```

### Logging — `log.py`

`setup_logging(service_name, level=None)` configures root logging once and returns the
service's `minder.<name>` logger — replaces the identical `logging.basicConfig(...)` +
`getLogger(...)` two-liner every service used to duplicate:

```python
from shared.log import setup_logging

logger = setup_logging("api-gateway", level=settings.LOG_LEVEL)
```

### Health — `health.py`

`evaluate_dependencies(checks)` runs a list of `DependencyCheck` probes (sync or async;
a probe signals unhealthy by raising or returning `False`) and derives an aggregate
`(status, http_code, checks_map)`. A `critical=True` dep down flips the service to
`("unhealthy", 503)`; a non-critical one only marks it `("degraded", 200)` so an
optional backend outage doesn't pull the service out of a load balancer. It
deliberately does **not** impose a response body model — each service keeps its own
`/health` body shape (rejected as a shared model in #49; every service's health body
carries genuinely different fields) and merges in `status`/`checks`:

```python
from shared.health import DependencyCheck, evaluate_dependencies

status, code, checks = await evaluate_dependencies([
    DependencyCheck("database", probe=db_ping, critical=True),
    DependencyCheck("redis", probe=redis_ping, critical=False),
])
return JSONResponse(status_code=code, content={"service": "marketplace", "status": status, "checks": checks})
```

### Errors — `errors.py`

`backend_http_error(exc, operation)` turns a caught exception into a sanitized
`HTTPException` — 503 "a required backend is unreachable, retry" for connectivity-shaped
failures (matched via substring markers, e.g. neo4j `ServiceUnavailable`, `httpx.ConnectError`,
`ConnectionRefusedError`, DNS/timeout errors), or a generic sanitized 500 otherwise.
**Never leaks `str(exc)` to the caller** — the raw exception belongs in the service's own
log line, not the HTTP response:

```python
from shared.errors import backend_http_error

except Exception as e:
    logger.error(f"Failed to construct graph for {doc_id}: {e}")
    raise backend_http_error(e, "Knowledge graph construction")
```

### Pagination — `pagination.py`

`paginate(items, limit, offset) -> (page, total)` slices an in-memory sequence and
reports the pre-slice total, so a list endpoint doesn't hand-roll `items[offset:offset+limit]`:

```python
from shared.pagination import paginate

page, total = paginate(all_plugins, limit=limit, offset=offset)
return {"items": page, "total": total, "limit": limit, "offset": offset}
```

### Database — `db/pool.py`, `db/schema.py`

`create_pg_pool(...)` builds an `asyncpg.Pool` from explicit connection params (no
env-var convention imposed — each service keeps its own settings source), with an
optional `auto_create=True` that creates the target database on first connect if it's
missing (`InvalidCatalogNameError` → connect to `postgres` → `CREATE DATABASE` → retry).
`apply_schema(pool, sql_path)` reads and executes a service's git-tracked `schema.sql`
at startup — idempotent (`CREATE TABLE IF NOT EXISTS`), safe to run every boot:

```python
from shared.db.pool import create_pg_pool
from shared.db.schema import apply_schema

pool = await create_pg_pool(host=settings.DB_HOST, port=settings.DB_PORT,
                             user=settings.DB_USER, password=settings.DB_PASSWORD,
                             database=settings.DB_NAME, auto_create=True)
await apply_schema(pool, pathlib.Path(__file__).parent / "schema.sql")
```

### Metrics — `metrics.py`

`setup_metrics(app)` installs an HTTP request-tracking middleware and mounts the
Prometheus `/metrics` endpoint. Called once at app construction:

```python
from shared.metrics import setup_metrics

app = FastAPI(title="My Service")
setup_metrics(app)
```

### Utilities — `utils/`

**Redis client** (`utils/redis_client.py`) — factories that build a configured
`redis.Redis`. By default they **ping on creation** (fail-fast if Redis is
unreachable); pass `ping=False` for module-level singletons created at import time,
where the client must stay lazy (connects on first command):

```python
from shared.utils.redis_client import create_redis_client_from_settings, create_redis_client

redis_client = create_redis_client_from_settings(settings)              # eager ping
redis_client = create_redis_client_from_settings(settings, ping=False)  # lazy (import-time singleton)
# or explicit:
redis_client = create_redis_client(host="redis", port=6379, password="secret")
```

**CORS** (`utils/cors.py`):

```python
from shared.utils.cors import add_cors_middleware

add_cors_middleware(app)                                  # uses built-in dev default origins
add_cors_middleware(app, allowed_origins=["http://localhost:3000"])
```

### Auth — `auth/jwt_middleware.py`

The single source of truth for JWT (issue #49 — no service forks its own JWT logic):

```python
from shared.auth.jwt_middleware import (
    create_jwt_token, verify_jwt_token,
    get_current_user, get_current_user_optional, get_current_user_or_service,
    enforce_rate_limit,
)
```

### AI — `ai/tool_validator.py`

```python
from shared.ai.tool_validator import validate_ai_tools

validate_ai_tools(manifest)   # validates a plugin's declared AI tools
```

## 📊 Current adoption

| Module | Used by |
|---|---|
| `log.setup_logging` | api-gateway, graph-rag, marketplace, model-management, plugin-registry, plugin-state-manager, rag-pipeline, tts-stt (8/8) |
| `health.evaluate_dependencies` | api-gateway, graph-rag, marketplace, model-management, plugin-registry, plugin-state-manager, rag-pipeline, tts-stt (8/8) |
| `errors.backend_http_error` | api-gateway, graph-rag, marketplace, model-management, plugin-registry, plugin-state-manager, rag-pipeline, tts-stt (8/8, #357/#358/#359/#360/#361) |
| `metrics.setup_metrics` | graph-rag, marketplace, model-management, plugin-registry, plugin-state-manager, rag-pipeline, tts-stt (7/8; api-gateway has its own) |
| `auth.jwt_middleware` | api-gateway, marketplace, plugin-registry (all services with an auth surface) |
| `pagination.paginate` | plugin-registry, plugin-state-manager, rag-pipeline (5 endpoints across 3 services, #357/#358) |
| `db.pool.create_pg_pool` | api-gateway, marketplace, plugin-registry, plugin-state-manager, rag-pipeline (5/5 services with their own Postgres pool) |
| `db.schema.apply_schema` | api-gateway, plugin-registry, plugin-state-manager, rag-pipeline (4/5; marketplace uses its own migration runner instead) |
| `utils.cors` | api-gateway, marketplace, plugin-state-manager |
| `utils.redis_client` | api-gateway, plugin-registry |
| `config.MinderBaseSettings` | plugin-state-manager (broader adoption evaluated and closed in #49 — see below) |
| `ai.tool_validator` | plugin-registry |
| `models.responses` | (envelopes available; a shared `HealthCheckResponse` body was deliberately rejected in #49 — see `health.py` above) |
| `models.tiers.LicenseTier` | marketplace, plugin-state-manager (the only 2 services with a license concept) |

> `config.MinderBaseSettings`/`models.responses` were evaluated for wider adoption in #49
> and intentionally left as-is: every service's `/health` body and settings carry
> genuinely different fields, so forcing the shared shapes would either drop
> service-specific data or need per-service subclasses — no clean win remained.

## 🤝 Contributing

When adding a shared component: place it in the right subpackage, export it from that
package's `__init__.py` (except `auth`/`ai`, imported from submodule), add a docstring
with an example, include type hints, and update this README's structure + adoption tables.

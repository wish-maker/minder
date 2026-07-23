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
from shared.models import HealthCheckResponse, SuccessResponse, ErrorResponse
from shared.utils.redis_client import create_redis_client_from_settings
from shared.utils.cors import add_cors_middleware, add_cors_from_string
from shared.metrics import setup_metrics
from shared.auth.jwt_middleware import get_current_user, create_jwt_token
from shared.ai.tool_validator import validate_ai_tools
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
├── metrics.py                # setup_metrics(app): request middleware + /metrics
├── config/
│   ├── __init__.py           # exports MinderBaseSettings
│   └── base_settings.py      # base BaseSettings (required secrets, no weak defaults)
├── models/
│   ├── __init__.py           # exports the response models below
│   └── responses.py          # standard Pydantic response envelopes
├── utils/
│   ├── __init__.py           # exports cors + redis_client helpers
│   ├── cors.py               # add_cors_middleware, add_cors_from_string
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
from shared.utils.cors import add_cors_middleware, add_cors_from_string

add_cors_middleware(app)                                  # uses built-in dev default origins
add_cors_from_string(app, "http://localhost:3000,http://localhost:8000")
```

### Auth — `auth/jwt_middleware.py`

The single source of truth for JWT (issue #49 — no service forks its own JWT logic):

```python
from shared.auth.jwt_middleware import (
    create_jwt_token, create_user_token, verify_jwt_token,
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
| `metrics.setup_metrics` | graph-rag, marketplace, model-management, plugin-registry, plugin-state-manager, rag-pipeline, tts-stt (7/8; api-gateway has its own) |
| `auth.jwt_middleware` | api-gateway, marketplace, plugin-registry (all services with an auth surface) |
| `utils.cors` | api-gateway, marketplace, plugin-state-manager |
| `utils.redis_client` | api-gateway, plugin-registry |
| `config.MinderBaseSettings` | plugin-state-manager (broader adoption tracked in #49) |
| `ai.tool_validator` | plugin-registry |
| `models.responses` | (envelopes available; broader adoption tracked in #49) |

## 🤝 Contributing

When adding a shared component: place it in the right subpackage, export it from that
package's `__init__.py` (except `auth`/`ai`, imported from submodule), add a docstring
with an example, include type hints, and update this README's structure + adoption tables.

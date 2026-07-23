"""Shared infrastructure clients and the downstream service registry.

Module-level singletons imported by the middleware, proxy routes, health check,
and main's lifespan (which closes them on shutdown).
"""

import sys

import httpx

from config import settings

# Shared Redis factory is the single source of truth for client construction
# (issue #49). api-gateway copies src/shared to /app/src/shared but does not put it
# on sys.path by default, so add it here (same guard as middleware.py / core.auth).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.utils.redis_client import create_redis_client_from_settings  # noqa: E402

# Redis client for rate limiting and caching. ping=False keeps the original lazy
# behaviour (this is a module-level singleton created at import, before Redis is
# guaranteed reachable) — redis.Redis connects on first command, unchanged from the
# previous hand-rolled client. Same host/port/password/db=0/decode_responses.
redis_client = create_redis_client_from_settings(settings, ping=False)

# HTTP client for proxying requests (with connection pooling)
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    timeout=httpx.Timeout(30.0, connect=10.0),
)

# Downstream service registry
SERVICE_REGISTRY = {
    "plugin_registry": settings.PLUGIN_REGISTRY_URL,
    "rag_pipeline": settings.RAG_PIPELINE_URL,
    "model_management": settings.MODEL_MANAGEMENT_URL,
}

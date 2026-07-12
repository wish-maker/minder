"""Shared infrastructure clients and the downstream service registry.

Module-level singletons imported by the middleware, proxy routes, health check,
and main's lifespan (which closes them on shutdown).
"""

import httpx
import redis

from config import settings

# Redis client for rate limiting and caching
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    db=0,
)

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

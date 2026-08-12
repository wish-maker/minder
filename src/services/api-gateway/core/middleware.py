"""HTTP middleware for the API Gateway: CORS, request-id/metrics, rate limiting.

All wiring is applied by register_middleware(app), called from main after the
FastAPI app is created.
"""

import logging
import sys
import time
import uuid

from core.clients import redis_client
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from config import settings

# Shared library on path (idempotent; also done in core/auth.py) so this module can
# use the shared CORS helper + the shared Prometheus collectors instead of
# re-defining them (they were byte-identical to shared.metrics) (#49/#223).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.metrics import (  # noqa: E402
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
    route_template,
)
from shared.utils.cors import add_cors_from_string  # noqa: E402

logger = logging.getLogger("minder.api-gateway")


def _client_ip(request: Request) -> str:
    """Client IP used as the rate-limit key.

    Replaces slowapi's get_remote_address (the only thing slowapi was used for — its
    Limiter was instantiated but never actually applied to any route). Returns the
    connecting peer's host; behind Traefik that is whatever ProxyHeaders resolves
    request.client to, unchanged from the previous behaviour.
    """
    client = request.client
    return client.host if client else "127.0.0.1"


def register_middleware(app: FastAPI) -> None:
    """Attach CORS, request-id/metrics, and (optional) rate-limit middleware."""

    # CORS — origins from env (comma-separated CORS_ALLOWED_ORIGINS), falling back
    # to "*" (unrestricted) when unset.
    add_cors_from_string(app, settings.CORS_ALLOWED_ORIGINS, default_origins=["*"])

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Add unique request ID to each request for distributed tracing"""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        request.state.start_time = time.time()

        # Update metrics. in_progress is method-only (bounded); the request's route
        # template isn't known until after routing (post call_next).
        method = request.method
        http_requests_in_progress.labels(method=method).inc()

        response = await call_next(request)

        # Calculate request duration
        duration = time.time() - request.state.start_time

        # Update metrics. Label total/duration with the matched route TEMPLATE
        # (e.g. /v1/rag/{path}) not the raw path — the gateway proxies every id
        # through path params, so raw-path labels are unbounded cardinality (#503).
        endpoint = route_template(request)
        http_requests_in_progress.labels(method=method).dec()
        http_requests_total.labels(
            method=method, endpoint=endpoint, status=response.status_code
        ).inc()
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
            duration
        )

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration*1000:.2f}ms"

        return response

    if settings.RATE_LIMIT_ENABLED:
        # Paths exempt from rate limiting: health/metrics (monitoring), API docs,
        # and static/frontend assets.
        exempt_prefixes = ("/static/", "/favicon")
        exempt_exact = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}

        @app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next):
            """Fixed-window per-IP rate limiting backed by Redis.

            The synchronous redis-py calls are offloaded via run_in_threadpool so they
            don't block the event loop on every request at the gateway (a thread pool
            hop, not an inline blocking call). An atomic INCR + first-hit EXPIRE
            replaces the old GET-then-INCR, which was a TOCTOU race: concurrent
            requests both read the pre-increment value and could each be admitted past
            the limit. (Threadpool-over-sync rather than redis.asyncio deliberately:
            an async client's connection pool binds to one event loop, which breaks
            under Starlette's TestClient — and buys nothing here since the work is a
            sub-millisecond Redis round-trip either way.)
            """
            path = request.url.path
            if path in exempt_exact or path.startswith(exempt_prefixes):
                return await call_next(request)

            # Atomic fixed-window counter: INCR returns the post-increment value, so
            # the window's first request sees 1 (and we stamp the 60s TTL then).
            # No read-modify-write, so no race. Fail open if Redis is unreachable.
            try:
                key = f"ratelimit:{_client_ip(request)}"
                count = await run_in_threadpool(redis_client.incr, key)
                if count == 1:
                    await run_in_threadpool(redis_client.expire, key, 60)
                if count > settings.RATE_LIMIT_PER_MINUTE:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "Rate limit exceeded",
                            "limit": settings.RATE_LIMIT_PER_MINUTE,
                            "window": "60 seconds",
                        },
                    )
            except Exception as e:
                # Redis unavailable, bypass rate limiting (fail open)
                logger.warning(f"Rate limiting unavailable: {e}")

            return await call_next(request)

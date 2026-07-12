"""HTTP middleware for the API Gateway: CORS, request-id/metrics, rate limiting.

All wiring is applied by register_middleware(app), called from main after the
FastAPI app is created.
"""

import logging
import time
import uuid

from clients import redis_client
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from metrics import (
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
)

from config import settings

logger = logging.getLogger("minder.api-gateway")


def register_middleware(app: FastAPI) -> None:
    """Attach CORS, request-id/metrics, and (optional) rate-limit middleware."""

    # CORS — parse CORS_ALLOWED_ORIGINS from environment (comma-separated)
    cors_origins = (
        settings.CORS_ALLOWED_ORIGINS.split(",")
        if settings.CORS_ALLOWED_ORIGINS
        else ["*"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Add unique request ID to each request for distributed tracing"""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        request.state.start_time = time.time()

        # Update metrics
        endpoint = request.url.path
        method = request.method
        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()

        response = await call_next(request)

        # Calculate request duration
        duration = time.time() - request.state.start_time

        # Update metrics
        http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()
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
        from slowapi import Limiter
        from slowapi.util import get_remote_address

        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter

        @app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next):
            """Apply rate limiting based on user IP or JWT token"""
            # Skip rate limiting for health checks and internal monitoring
            if request.url.path == "/health":
                return await call_next(request)

            # Skip rate limiting for metrics (monitoring)
            if request.url.path == "/metrics":
                return await call_next(request)

            # Skip rate limiting for API documentation
            if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
                return await call_next(request)

            # Skip rate limiting for static files and frontend assets
            if request.url.path.startswith("/static/") or request.url.path.startswith(
                "/favicon"
            ):
                return await call_next(request)

            # Get identifier (JWT token subject or IP address)
            identifier = get_remote_address(request)

            # Check rate limit in Redis (with error handling)
            try:
                key = f"ratelimit:{identifier}"
                current = redis_client.get(key)

                if current is None:
                    # First request in window
                    redis_client.setex(key, 60, 1)
                else:
                    count = int(current)
                    if count >= settings.RATE_LIMIT_PER_MINUTE:
                        return JSONResponse(
                            status_code=429,
                            content={
                                "error": "Rate limit exceeded",
                                "limit": settings.RATE_LIMIT_PER_MINUTE,
                                "window": "60 seconds",
                            },
                        )
                    redis_client.incr(key)
            except Exception as e:
                # Redis unavailable, bypass rate limiting (fail open)
                logger.warning(f"Rate limiting unavailable: {e}")

            return await call_next(request)

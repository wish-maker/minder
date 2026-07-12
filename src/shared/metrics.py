"""Shared Prometheus HTTP metrics for all Minder services.

One ``setup_metrics(app)`` call registers a request-tracking middleware and a
``/metrics`` endpoint, so every service exposes consistent request metrics
(total, latency, in-progress) without copy-pasting the middleware. Each service
runs in its own process, so the module-level collectors are per-service.

Usage (after `sys.path.insert(0, "/app/src")`):

    from shared.metrics import setup_metrics
    setup_metrics(app)
"""

import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently in progress",
    ["method", "endpoint"],
)


def setup_metrics(app: FastAPI) -> None:
    """Attach the request-tracking middleware and the /metrics endpoint to *app*."""

    @app.middleware("http")
    async def _track_requests(request: Request, call_next):
        method = request.method
        endpoint = request.url.path
        http_requests_in_progress.labels(method=method, endpoint=endpoint).inc()
        start = time.time()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.time() - start
            http_requests_in_progress.labels(method=method, endpoint=endpoint).dec()
            http_requests_total.labels(
                method=method, endpoint=endpoint, status=status
            ).inc()
            http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint"""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

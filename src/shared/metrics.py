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
    # Labelled by method ONLY: a request's matched route isn't known until AFTER
    # routing (post call_next), but an in-progress gauge must inc() before the
    # request runs. Method-only keeps it bounded; per-endpoint in-flight counts add
    # little and would need the raw path (unbounded) here.
    ["method"],
)


def route_template(request: Request) -> str:
    """Bounded ``endpoint`` label: the matched route TEMPLATE, not the raw path.

    ``request.url.path`` is the concrete URL (``/v1/models/llama3.2:latest``), so a
    Counter/Histogram labelled with it grows one time series per distinct id value —
    unbounded Prometheus cardinality. The matched route's ``path`` is the template
    (``/v1/models/{model_id}``), a small fixed set. Only populated AFTER routing, so
    call this from the post-``call_next`` path. Unmatched requests (404s, scanners
    hitting random URLs) collapse to a single ``__unmatched__`` bucket rather than
    spawning a series each."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if path else "__unmatched__"


def setup_metrics(app: FastAPI) -> None:
    """Attach the request-tracking middleware and the /metrics endpoint to *app*."""

    @app.middleware("http")
    async def _track_requests(request: Request, call_next):
        method = request.method
        http_requests_in_progress.labels(method=method).inc()
        start = time.time()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration = time.time() - start
            http_requests_in_progress.labels(method=method).dec()
            endpoint = route_template(request)
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

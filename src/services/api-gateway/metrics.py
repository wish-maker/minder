"""Prometheus metric definitions for the API Gateway.

Defined in one module so both the request-tracking middleware and the /metrics
endpoint share the same registered collectors (generate_latest reads the global
registry, so importing this module anywhere registers them).
"""

from prometheus_client import Counter, Gauge, Histogram

# HTTP request metrics
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

# Service health metrics
service_health_up = Gauge(
    "service_health_up", "Service health status (1=up, 0=down)", ["service"]
)

active_plugins_gauge = Gauge("active_plugins_total", "Number of active plugins")

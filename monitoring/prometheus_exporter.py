"""
Prometheus Metrics Exporter for Minder
Exposes metrics in Prometheus format for scraping
"""

import logging
import time

try:
    from prometheus_client import (  # noqa: F401
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        Info,
        Summary,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logging.warning("prometheus_client not installed. Install with: pip install prometheus_client")

logger = logging.getLogger(__name__)


class PrometheusMetricsExporter:
    """
    Prometheus metrics exporter for Minder

    Exports metrics in Prometheus format:
    - Counters: Request counts, errors
    - Gauges: System resources, active connections
    - Histograms: Request durations, query times
    - Summaries: Performance percentiles
    """

    def __init__(self):
        if not PROMETHEUS_AVAILABLE:
            raise ImportError("prometheus_client is not installed")

        # System metrics
        self.cpu_usage = Gauge("minder_cpu_usage_percent", "CPU usage percentage")
        self.memory_usage = Gauge("minder_memory_usage_percent", "Memory usage percentage")
        self.memory_available = Gauge("minder_memory_available_mb", "Available memory in MB")
        self.uptime = Gauge("minder_uptime_seconds", "Application uptime in seconds")

        # API metrics
        self.http_requests_total = Counter(
            "minder_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
        )
        self.http_request_duration_seconds = Histogram(
            "minder_http_request_duration_seconds",
            "HTTP request latency",
            ["method", "endpoint"],
        )

        # Database metrics
        self.db_queries_total = Counter(
            "minder_db_queries_total",
            "Total database queries",
            ["query_type", "status"],
        )
        self.db_query_duration_seconds = Histogram(
            "minder_db_query_duration_seconds",
            "Database query duration",
            ["query_type"],
        )
        self.db_connections = Gauge("minder_db_connections", "Active database connections", ["database"])

        # Plugin metrics
        self.plugin_operations_total = Counter(
            "minder_plugin_operations_total",
            "Total plugin operations",
            ["plugin_name", "operation", "status"],
        )
        self.plugin_operation_duration_seconds = Histogram(
            "minder_plugin_operation_duration_seconds",
            "Plugin operation duration",
            ["plugin_name", "operation"],
        )
        self.plugins_loaded = Gauge("minder_plugins_loaded", "Number of loaded plugins", ["status"])

        # Cache metrics
        self.cache_hits_total = Counter(
            "minder_cache_hits_total",
            "Total cache hits",
            ["cache_type"],
        )
        self.cache_misses_total = Counter(
            "minder_cache_misses_total",
            "Total cache misses",
            ["cache_type"],
        )

        # Background job metrics
        self.background_jobs_total = Counter(
            "minder_background_jobs_total",
            "Total background jobs executed",
            ["job_type", "status"],
        )
        self.background_job_duration_seconds = Histogram(
            "minder_background_job_duration_seconds",
            "Background job duration",
            ["job_type"],
        )

        # Application info
        self.app_info = Info(
            "minder_application",
            "Minder application information",
        )

        # Start time for uptime calculation
        self.start_time = time.time()

        logger.info("✅ Prometheus metrics exporter initialized")

    def record_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request"""
        status = "success" if status_code < 400 else "error"
        self.http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
        self.http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)

    def record_db_query(self, query_type: str, duration: float, success: bool):
        """Record database query"""
        status = "success" if success else "error"
        self.db_queries_total.labels(query_type=query_type, status=status).inc()
        self.db_query_duration_seconds.labels(query_type=query_type).observe(duration)

    def set_db_connections(self, database: str, count: int):
        """Set database connection count"""
        self.db_connections.labels(database=database).set(count)

    def record_plugin_operation(self, plugin_name: str, operation: str, duration: float, success: bool):
        """Record plugin operation"""
        status = "success" if success else "error"
        self.plugin_operations_total.labels(plugin_name=plugin_name, operation=operation, status=status).inc()
        self.plugin_operation_duration_seconds.labels(plugin_name=plugin_name, operation=operation).observe(duration)

    def set_plugins_loaded(self, active: int, inactive: int = 0):
        """Set number of loaded plugins"""
        self.plugins_loaded.labels(status="active").set(active)
        self.plugins_loaded.labels(status="inactive").set(inactive)

    def record_cache_hit(self, cache_type: str):
        """Record cache hit"""
        self.cache_hits_total.labels(cache_type=cache_type).inc()

    def record_cache_miss(self, cache_type: str):
        """Record cache miss"""
        self.cache_misses_total.labels(cache_type=cache_type).inc()

    def record_background_job(self, job_type: str, duration: float, success: bool):
        """Record background job execution"""
        status = "success" if success else "error"
        self.background_jobs_total.labels(job_type=job_type, status=status).inc()
        self.background_job_duration_seconds.labels(job_type=job_type).observe(duration)

    def update_system_metrics(self, cpu_percent: float, memory_percent: float, available_mb: float):
        """Update system resource metrics"""
        self.cpu_usage.set(cpu_percent)
        self.memory_usage.set(memory_percent)
        self.memory_available.set(available_mb)
        self.uptime.set(time.time() - self.start_time)

    def set_app_info(self, version: str, commit: str = None):
        """Set application information"""
        info = {"version": version}
        if commit:
            info["commit"] = commit
        self.app_info.info(info)

    def get_metrics(self) -> bytes:
        """Export metrics in Prometheus format"""
        return generate_latest(REGISTRY)

    def reset_metrics(self):
        """Reset all metrics (useful for testing)"""
        # Clear default registry
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            REGISTRY.unregister(collector)

        # Re-initialize metrics
        self.__init__()

        logger.info("✅ Prometheus metrics reset")

"""
Monitoring endpoints for Minder API
Provides metrics and health check endpoints
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Response

from monitoring.metrics_collector import MetricsCollector
from monitoring.performance_monitor import PerformanceMonitor
from monitoring.prometheus_exporter import PROMETHEUS_AVAILABLE, PrometheusMetricsExporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Global monitoring instances
metrics_collector: MetricsCollector = None
performance_monitor: PerformanceMonitor = None
prometheus_exporter: PrometheusMetricsExporter = None


def initialize_monitoring(config: Dict[str, Any]):
    """Initialize monitoring components"""
    global metrics_collector, performance_monitor, prometheus_exporter

    # Initialize metrics collector
    metrics_collector = MetricsCollector(config)

    # Initialize performance monitor
    performance_monitor = PerformanceMonitor(config)

    # Initialize Prometheus exporter if available
    if PROMETHEUS_AVAILABLE:
        try:
            prometheus_exporter = PrometheusMetricsExporter()
            prometheus_exporter.set_app_info(version="1.0.0")
        except Exception as e:
            logger.warning(f"Failed to initialize Prometheus exporter: {e}")


async def start_monitoring():
    """Start all monitoring components"""
    if metrics_collector:
        await metrics_collector.start()

    if performance_monitor:
        await performance_monitor.start()

    logger.info("✅ Monitoring started")


async def stop_monitoring():
    """Stop all monitoring components"""
    if metrics_collector:
        await metrics_collector.stop()

    if performance_monitor:
        await performance_monitor.stop()

    logger.info("✅ Monitoring stopped")


@router.get("/health")
async def health_check():
    """Comprehensive health check with metrics"""
    if not performance_monitor:
        return {"status": "monitoring_not_initialized"}

    system_metrics = performance_monitor.get_system_metrics()

    return {
        "status": "healthy" if system_metrics.get("cpu", {}).get("status") == "ok" else "degraded",
        "timestamp": datetime.now().isoformat(),
        "system": system_metrics,
        "monitoring": {
            "metrics_collector": ("running" if metrics_collector and metrics_collector.is_running else "stopped"),
            "performance_monitor": ("running" if performance_monitor and performance_monitor.is_running else "stopped"),
            "prometheus_exporter": "enabled" if prometheus_exporter else "disabled",
        },
    }


@router.get("/metrics")
async def get_metrics():
    """Get Prometheus metrics"""
    if not prometheus_exporter:
        return {"error": "Prometheus exporter not available"}

    metrics = prometheus_exporter.get_metrics()
    return Response(content=metrics, media_type="text/plain")


@router.get("/performance")
async def get_performance_metrics():
    """Get detailed performance metrics"""
    if not performance_monitor:
        return {"error": "Performance monitor not initialized"}

    return performance_monitor.get_all_metrics()


@router.get("/api")
async def get_api_metrics():
    """Get API performance metrics"""
    if not performance_monitor:
        return {"error": "Performance monitor not initialized"}

    return performance_monitor.get_api_metrics()


@router.get("/database")
async def get_database_metrics():
    """Get database query metrics"""
    if not performance_monitor:
        return {"error": "Performance monitor not initialized"}

    return performance_monitor.get_database_metrics()


@router.get("/plugins")
async def get_plugin_metrics(plugin_name: str = None):
    """Get plugin execution metrics"""
    if not performance_monitor:
        return {"error": "Performance monitor not initialized"}

    return performance_monitor.get_plugin_metrics(plugin_name)


@router.post("/record")
async def record_metric(metric: Dict[str, Any]):
    """Record a custom metric"""
    if not metrics_collector:
        return {"error": "Metrics collector not initialized"}

    await metrics_collector.collect_metric(metric)
    return {"status": "recorded"}


@router.get("/summary")
async def get_metrics_summary():
    """Get summary of collected metrics"""
    if not metrics_collector:
        return {"error": "Metrics collector not initialized"}

    return await metrics_collector.get_metrics_summary()


@router.post("/reset")
async def reset_metrics():
    """Reset all metrics (use with caution)"""
    if performance_monitor:
        performance_monitor.reset_metrics()

    if prometheus_exporter:
        prometheus_exporter.reset_metrics()

    return {"status": "metrics_reset"}

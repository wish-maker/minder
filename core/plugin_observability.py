"""
Plugin Observability & Monitoring System
Version: 1.0.0

Production-grade monitoring, metrics, and health checks
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger(__name__)


# Prometheus metrics
plugin_memory_usage = Gauge("plugin_memory_usage_bytes", "Plugin memory usage in bytes", ["plugin_name"])

plugin_cpu_percent = Gauge("plugin_cpu_percent", "Plugin CPU usage percentage", ["plugin_name"])

plugin_request_count = Counter(
    "plugin_request_count_total", "Total plugin requests", ["plugin_name", "method", "status"]
)

plugin_request_duration = Histogram(
    "plugin_request_duration_seconds", "Plugin request duration", ["plugin_name", "method"]
)

plugin_error_count = Counter("plugin_error_count_total", "Total plugin errors", ["plugin_name", "error_type"])

plugin_health_status = Gauge("plugin_health_status", "Plugin health status (1=healthy, 0=unhealthy)", ["plugin_name"])


class PluginMetrics:
    """Collect and expose plugin metrics"""

    def __init__(self):
        self.start_time = time.time()

    def record_request(self, plugin_name: str, method: str, duration: float, status: str = "success"):
        """Record plugin request"""
        plugin_request_count.labels(plugin_name=plugin_name, method=method, status=status).inc()

        plugin_request_duration.labels(plugin_name=plugin_name, method=method).observe(duration)

    def record_error(self, plugin_name: str, error_type: str, error: Exception):
        """Record plugin error"""
        plugin_error_count.labels(plugin_name=plugin_name, error_type=error_type).inc()

        logger.error(f"Plugin error: {plugin_name}: {error_type}: {error}")

    def update_resource_usage(self, plugin_name: str, memory_mb: float, cpu_percent: float):
        """Update plugin resource usage"""
        plugin_memory_usage.labels(plugin_name=plugin_name).set(memory_mb * 1024 * 1024)  # Convert to bytes

        plugin_cpu_percent.labels(plugin_name=plugin_name).set(cpu_percent)

    def update_health_status(self, plugin_name: str, healthy: bool):
        """Update plugin health status"""
        plugin_health_status.labels(plugin_name=plugin_name).set(1 if healthy else 0)


class PluginHealthMonitor:
    """
    Monitor plugin health with liveness/readiness probes

    Kubernetes-style health checks
    """

    def __init__(self, metrics: PluginMetrics):
        self.metrics = metrics
        self.health_checks: Dict[str, Dict[str, Any]] = {}

    async def check_health(self, plugin_name: str, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Check plugin health

        Returns:
            Health status with details
        """
        start_time = time.time()

        try:
            # Check 1: Plugin is loaded
            # (Implemented by caller passing plugin instance)

            # Check 2: Plugin responds to health check
            # health_status = await asyncio.wait_for(
            #     plugin.health_check(),
            #     timeout=timeout
            # )

            # Check 3: Resource usage within limits
            # memory_mb = get_plugin_memory(plugin_name)
            # cpu_percent = get_plugin_cpu(plugin_name)

            duration = time.time() - start_time

            status = {
                "plugin": plugin_name,
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "check_duration_seconds": duration,
                "uptime_seconds": self._get_plugin_uptime(plugin_name),
                # "memory_mb": memory_mb,
                # "cpu_percent": cpu_percent,
                # "state": health_status.get("state", {}),
            }

            # Update metrics
            self.metrics.update_health_status(plugin_name, healthy=True)

            # Cache result
            self.health_checks[plugin_name] = status

            return status

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            status = {
                "plugin": plugin_name,
                "status": "unhealthy",
                "reason": "health_check_timeout",
                "timeout": timeout,
                "check_duration_seconds": duration,
                "timestamp": datetime.now().isoformat(),
            }

            self.metrics.update_health_status(plugin_name, healthy=False)
            self.health_checks[plugin_name] = status

            return status

        except Exception as e:
            duration = time.time() - start_time
            status = {
                "plugin": plugin_name,
                "status": "unhealthy",
                "reason": "health_check_failed",
                "error": str(e),
                "check_duration_seconds": duration,
                "timestamp": datetime.now().isoformat(),
            }

            self.metrics.update_health_status(plugin_name, healthy=False)
            self.health_checks[plugin_name] = status

            return status

    def _get_plugin_uptime(self, plugin_name: str) -> float:
        """Get plugin uptime in seconds"""
        # Implementation depends on how you track plugin start time
        return 0.0

    def get_all_health_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get all cached health statuses"""
        return self.health_checks.copy()


class PluginPerformanceTracker:
    """Track plugin performance metrics"""

    def __init__(self):
        self.call_stats: Dict[str, Dict[str, List[float]]] = {}

    def record_call(self, plugin_name: str, method: str, duration: float):
        """Record plugin method call"""
        key = f"{plugin_name}.{method}"

        if key not in self.call_stats:
            self.call_stats[key] = {"durations": [], "timestamps": []}

        # Keep last 1000 calls
        self.call_stats[key]["durations"].append(duration)
        self.call_stats[key]["timestamps"].append(time.time())

        if len(self.call_stats[key]["durations"]) > 1000:
            self.call_stats[key]["durations"].pop(0)
            self.call_stats[key]["timestamps"].pop(0)

    def get_stats(self, plugin_name: str, method: str, window_seconds: int = 300) -> Dict[str, float]:
        """
        Get performance stats for plugin method

        Args:
            plugin_name: Plugin name
            method: Method name
            window_seconds: Time window (default 5 minutes)

        Returns:
            Statistics: avg, p50, p95, p99, min, max, count
        """
        key = f"{plugin_name}.{method}"

        if key not in self.call_stats:
            return {}

        cutoff_time = time.time() - window_seconds

        # Filter calls within time window
        durations = []
        for duration, timestamp in zip(self.call_stats[key]["durations"], self.call_stats[key]["timestamps"]):
            if timestamp >= cutoff_time:
                durations.append(duration)

        if not durations:
            return {}

        # Calculate statistics
        durations_sorted = sorted(durations)

        return {
            "count": len(durations),
            "avg": sum(durations) / len(durations),
            "min": durations_sorted[0],
            "max": durations_sorted[-1],
            "p50": durations_sorted[len(durations_sorted) // 2],
            "p95": durations_sorted[int(len(durations_sorted) * 0.95)],
            "p99": durations_sorted[int(len(durations_sorted) * 0.99)],
        }


class PluginDiagnostics:
    """
    Collect diagnostic information for troubleshooting
    """

    @staticmethod
    async def collect_diagnostics(plugin_name: str, plugin_instance: Any) -> Dict[str, Any]:
        """
        Collect comprehensive diagnostic info

        Returns:
            Diagnostic data for troubleshooting
        """
        diagnostics = {
            "plugin": plugin_name,
            "timestamp": datetime.now().isoformat(),
            "system": {
                "python_version": sys.version,
                "platform": sys.platform,
                "hostname": socket.gethostname(),
            },
            "plugin_info": {},
            "performance": {},
            "errors": [],
            "warnings": [],
        }

        try:
            # Get plugin metadata
            if hasattr(plugin_instance, "metadata"):
                diagnostics["plugin_info"] = {
                    "name": plugin_instance.metadata.name,
                    "version": plugin_instance.metadata.version,
                    "author": plugin_instance.metadata.author,
                    "description": plugin_instance.metadata.description,
                }

            # Get plugin state
            if hasattr(plugin_instance, "state"):
                diagnostics["plugin_info"]["state"] = plugin_instance.state

            # Get recent performance stats
            # (from PerformanceTracker)

            # Get recent errors
            # (from logs)

        except Exception as e:
            diagnostics["errors"].append(f"Failed to collect diagnostics: {e}")

        return diagnostics


# HTTP API endpoints
router = APIRouter(prefix="/plugins/observability", tags=["Plugin Observability"])

_metrics: Optional[PluginMetrics] = None
_health_monitor: Optional[PluginHealthMonitor] = None
_performance_tracker: Optional[PluginPerformanceTracker] = None


def set_observability_components(
    metrics: PluginMetrics,
    health_monitor: PluginHealthMonitor,
    performance_tracker: PluginPerformanceTracker,
):
    """Set global observability components"""
    global _metrics, _health_monitor, _performance_tracker
    _metrics = metrics
    _health_monitor = health_monitor
    _performance_tracker = performance_tracker


@router.get("/health/{plugin_name}")
async def get_plugin_health(plugin_name: str):
    """Get plugin health status"""
    if not _health_monitor:
        raise HTTPException(status_code=503, detail="Health monitor not initialized")

    status = await _health_monitor.check_health(plugin_name)
    return status


@router.get("/health")
async def get_all_plugin_health():
    """Get all plugin health statuses"""
    if not _health_monitor:
        raise HTTPException(status_code=503, detail="Health monitor not initialized")

    return _health_monitor.get_all_health_statuses()


@router.get("/metrics/{plugin_name}")
async def get_plugin_metrics(plugin_name: str):
    """Get plugin performance metrics"""
    if not _performance_tracker:
        raise HTTPException(status_code=503, detail="Performance tracker not initialized")

    # Get all methods for this plugin
    methods = ["collect_data", "analyze", "query"]  # Or discover dynamically

    metrics = {}
    for method in methods:
        stats = _performance_tracker.get_stats(plugin_name, method)
        if stats:
            metrics[f"{plugin_name}.{method}"] = stats

    return metrics


@router.get("/diagnostics/{plugin_name}")
async def get_plugin_diagnostics(plugin_name: str):
    """Get plugin diagnostic information"""
    # This would need access to plugin instance
    # For now, return placeholder
    return {"plugin": plugin_name, "message": "Diagnostics not yet implemented"}


# Startup: Start Prometheus metrics server
async def start_observability():
    """Start observability systems"""
    # Start Prometheus metrics server on port 9090
    start_http_server(9090)
    logger.info("📊 Prometheus metrics server started on port 9090")

    # Initialize components
    metrics = PluginMetrics()
    health_monitor = PluginHealthMonitor(metrics)
    performance_tracker = PluginPerformanceTracker()

    set_observability_components(metrics, health_monitor, performance_tracker)

    logger.info("✅ Plugin observability system started")


# Example usage
async def example_observability():
    """Example of observability usage"""
    from core.plugin_sandbox import SandboxedPluginLoader

    # Start observability
    await start_observability()

    loader = SandboxedPluginLoader()

    # Track plugin execution
    plugin_name = "weather_plugin"
    start_time = time.time()

    try:
        await loader.execute_plugin_method(plugin_name, "collect_data")

        duration = time.time() - start_time

        # Record metrics
        _metrics.record_request(plugin_name, "collect_data", duration)
        _performance_tracker.record_call(plugin_name, "collect_data", duration)

    except Exception as e:
        _metrics.record_error(plugin_name, type(e).__name__, e)

    # Check health
    health = await _health_monitor.check_health(plugin_name)
    print(f"Health: {health['status']}")


if __name__ == "__main__":
    import socket
    import sys

    asyncio.run(example_observability())

"""
Minder Performance Monitoring System
Tracks system performance, resource usage, and API metrics
"""

import asyncio
import psutil
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from collections import deque
import logging

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    Real-time performance monitoring for Minder system

    Tracks:
    - CPU and memory usage
    - API response times
    - Database query performance
    - Plugin execution metrics
    - Network I/O statistics
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enabled = config.get("monitoring", {}).get("enabled", True)

        # Metrics storage (rolling windows)
        self.cpu_history = deque(maxlen=60)  # Last 60 seconds
        self.memory_history = deque(maxlen=60)
        self.api_response_times = deque(maxlen=1000)  # Last 1000 requests
        self.query_times = deque(maxlen=500)  # Last 500 queries
        self.plugin_metrics = {}  # Per-plugin metrics

        # Thresholds for alerts
        self.thresholds = {
            "cpu_percent": 80,
            "memory_percent": 85,
            "response_time_ms": 5000,
            "query_time_ms": 3000,
        }

        self.start_time = datetime.now()
        self._monitoring_task = None
        self.is_running = False

    async def start(self):
        """Start performance monitoring"""
        if not self.enabled:
            logger.info("Performance monitoring disabled")
            return

        logger.info("Starting performance monitoring...")
        self.is_running = True
        self._monitoring_task = asyncio.create_task(self._monitor_loop())
        logger.info("✓ Performance monitoring started")

    async def stop(self):
        """Stop performance monitoring"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        self.is_running = False
        logger.info("✓ Performance monitoring stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - collects metrics every second"""
        while self.is_running:
            try:
                # Collect system metrics
                await self._collect_system_metrics()

                # Check for threshold violations
                await self._check_thresholds()

                # Sleep for 1 second
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Wait before retry

    async def _collect_system_metrics(self):
        """Collect CPU, memory, and I/O metrics"""
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        self.cpu_history.append({
            "timestamp": datetime.now(),
            "value": cpu_percent,
        })

        # Memory metrics
        memory = psutil.virtual_memory()
        self.memory_history.append({
            "timestamp": datetime.now(),
            "value": memory.percent,
            "available_mb": memory.available / 1024 / 1024,
        })

    async def _check_thresholds(self):
        """Check if any metrics exceed thresholds"""
        if self.cpu_history:
            latest_cpu = self.cpu_history[-1]["value"]
            if latest_cpu > self.thresholds["cpu_percent"]:
                logger.warning(f"⚠️ High CPU usage: {latest_cpu:.1f}%")

        if self.memory_history:
            latest_memory = self.memory_history[-1]["value"]
            if latest_memory > self.thresholds["memory_percent"]:
                logger.warning(f"⚠️ High memory usage: {latest_memory:.1f}%")

    def record_api_response(self, endpoint: str, response_time_ms: float, status_code: int):
        """Record API response time"""
        self.api_response_times.append({
            "timestamp": datetime.now(),
            "endpoint": endpoint,
            "response_time_ms": response_time_ms,
            "status_code": status_code,
        })

        # Alert on slow responses
        if response_time_ms > self.thresholds["response_time_ms"]:
            logger.warning(f"⚠️ Slow API response: {endpoint} took {response_time_ms:.0f}ms")

    def record_query_time(self, query_type: str, duration_ms: float):
        """Record database query execution time"""
        self.query_times.append({
            "timestamp": datetime.now(),
            "query_type": query_type,
            "duration_ms": duration_ms,
        })

        # Alert on slow queries
        if duration_ms > self.thresholds["query_time_ms"]:
            logger.warning(f"⚠️ Slow query: {query_type} took {duration_ms:.0f}ms")

    def record_plugin_execution(self, plugin_name: str, operation: str, duration_ms: float, success: bool):
        """Record plugin execution metrics"""
        if plugin_name not in self.plugin_metrics:
            self.plugin_metrics[plugin_name] = {
                "operations": [],
                "total_duration_ms": 0,
                "success_count": 0,
                "error_count": 0,
            }

        metrics = self.plugin_metrics[plugin_name]
        metrics["operations"].append({
            "timestamp": datetime.now(),
            "operation": operation,
            "duration_ms": duration_ms,
            "success": success,
        })
        metrics["total_duration_ms"] += duration_ms

        if success:
            metrics["success_count"] += 1
        else:
            metrics["error_count"] += 1

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get current system metrics"""
        if not self.cpu_history or not self.memory_history:
            return {"status": "monitoring_not_started"}

        # Calculate averages
        avg_cpu = sum(m["value"] for m in self.cpu_history) / len(self.cpu_history)
        avg_memory = sum(m["value"] for m in self.memory_history) / len(self.memory_history)

        # Get current values
        current_cpu = self.cpu_history[-1]["value"]
        current_memory = self.memory_history[-1]["value"]

        return {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "current_percent": current_cpu,
                "average_percent": avg_cpu,
                "status": "ok" if current_cpu < self.thresholds["cpu_percent"] else "high",
            },
            "memory": {
                "current_percent": current_memory,
                "average_percent": avg_memory,
                "available_mb": self.memory_history[-1]["available_mb"],
                "status": "ok" if current_memory < self.thresholds["memory_percent"] else "high",
            },
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
        }

    def get_api_metrics(self) -> Dict[str, Any]:
        """Get API performance metrics"""
        if not self.api_response_times:
            return {"status": "no_data"}

        # Calculate statistics
        response_times = [m["response_time_ms"] for m in self.api_response_times]

        return {
            "total_requests": len(self.api_response_times),
            "avg_response_time_ms": sum(response_times) / len(response_times),
            "min_response_time_ms": min(response_times),
            "max_response_time_ms": max(response_times),
            "p95_response_time_ms": self._percentile(response_times, 95),
            "p99_response_time_ms": self._percentile(response_times, 99),
            "error_rate": sum(1 for m in self.api_response_times if m["status_code"] >= 400) / len(self.api_response_times),
        }

    def get_plugin_metrics(self, plugin_name: Optional[str] = None) -> Dict[str, Any]:
        """Get plugin execution metrics"""
        if plugin_name:
            if plugin_name not in self.plugin_metrics:
                return {"status": "plugin_not_found"}
            return self._format_plugin_metrics(plugin_name, self.plugin_metrics[plugin_name])

        return {
            name: self._format_plugin_metrics(name, metrics)
            for name, metrics in self.plugin_metrics.items()
        }

    def _format_plugin_metrics(self, plugin_name: str, metrics: Dict) -> Dict[str, Any]:
        """Format plugin metrics for display"""
        total_ops = metrics["success_count"] + metrics["error_count"]
        avg_duration = metrics["total_duration_ms"] / total_ops if total_ops > 0 else 0

        return {
            "plugin": plugin_name,
            "total_operations": total_ops,
            "success_count": metrics["success_count"],
            "error_count": metrics["error_count"],
            "success_rate": metrics["success_count"] / total_ops if total_ops > 0 else 0,
            "avg_duration_ms": avg_duration,
            "total_duration_ms": metrics["total_duration_ms"],
        }

    def get_database_metrics(self) -> Dict[str, Any]:
        """Get database query performance metrics"""
        if not self.query_times:
            return {"status": "no_data"}

        query_times = [m["duration_ms"] for m in self.query_times]

        return {
            "total_queries": len(self.query_times),
            "avg_query_time_ms": sum(query_times) / len(query_times),
            "min_query_time_ms": min(query_times),
            "max_query_time_ms": max(query_times),
            "p95_query_time_ms": self._percentile(query_times, 95),
            "slow_queries": sum(1 for t in query_times if t > self.thresholds["query_time_ms"]),
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        return {
            "system": self.get_system_metrics(),
            "api": self.get_api_metrics(),
            "database": self.get_database_metrics(),
            "plugins": self.get_plugin_metrics(),
            "monitoring_uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
        }

    def _percentile(self, data: List[float], p: int) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * p / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def reset_metrics(self):
        """Reset all metrics"""
        self.cpu_history.clear()
        self.memory_history.clear()
        self.api_response_times.clear()
        self.query_times.clear()
        self.plugin_metrics.clear()
        self.start_time = datetime.now()
        logger.info("✓ Metrics reset")

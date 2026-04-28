"""
Hardware Resource Optimization Module
Optimizes CPU, memory, disk I/O, and network resource usage for Minder services.
"""

import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from functools import wraps
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from .resource_monitor import ResourceMonitor, ResourceUsage, ResourceThresholds

logger = logging.getLogger("minder.resource_optimizer")


class ResourceOptimizer:
    """
    Optimize hardware resources for Minder services.
    Provides adaptive resource management and optimization.
    """

    def __init__(
        self,
        monitor: Optional[ResourceMonitor] = None,
        max_workers: Optional[int] = None,
        adaptive: bool = True,
    ):
        """
        Initialize resource optimizer.

        Args:
            monitor: Resource monitor instance
            max_workers: Maximum worker threads (None = auto)
            adaptive: Enable adaptive resource management
        """
        self.monitor = monitor or ResourceMonitor()
        self.max_workers = max_workers
        self.adaptive = adaptive
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        if max_workers is None:
            # Auto-determine optimal workers based on CPU cores
            import os
            self.max_workers = max(1, os.cpu_count() - 1)

        logger.info(
            f"Resource optimizer initialized: max_workers={self.max_workers}, "
            f"adaptive={self.adaptive}"
        )

    async def optimize_resources(self) -> Dict[str, Any]:
        """Optimize resources based on current usage"""
        usage = self.monitor.get_current_usage()
        alerts = self.monitor.check_thresholds(usage)

        optimizations = {
            "timestamp": datetime.now().isoformat(),
            "usage": {
                "cpu_percent": usage.cpu_percent,
                "memory_percent": usage.memory_percent,
                "disk_percent": usage.disk_percent,
            },
            "alerts": alerts,
            "recommendations": [],
        }

        # Generate recommendations
        if usage.cpu_percent > 80:
            optimizations["recommendations"].append(
                {
                    "resource": "cpu",
                    "action": "reduce_workers",
                    "message": f"Reduce worker threads to {self.max_workers // 2}",
                }
            )

        if usage.memory_percent > 80:
            optimizations["recommendations"].append(
                {
                    "resource": "memory",
                    "action": "increase_cache_gc",
                    "message": "Increase cache garbage collection frequency",
                }
            )

        if usage.disk_percent > 80:
            optimizations["recommendations"].append(
                {
                    "resource": "disk",
                    "action": "cleanup_logs",
                    "message": "Clean up old log files and temporary data",
                }
            )

        logger.info(f"Resource optimization complete: {optimizations}")
        return optimizations

    async def adapt_worker_count(self) -> int:
        """Adapt worker count based on resource usage"""
        if not self.adaptive:
            return self.max_workers

        usage = self.monitor.get_current_usage()

        # Adjust workers based on CPU usage
        if usage.cpu_percent > 80:
            new_workers = max(1, self.max_workers // 2)
        elif usage.cpu_percent < 30:
            new_workers = self.max_workers
        else:
            new_workers = self.max_workers

        if new_workers != self.max_workers:
            logger.info(f"Adjusting worker count: {self.max_workers} -> {new_workers}")
            self.max_workers = new_workers
            # Recreate executor with new worker count
            self.executor.shutdown(wait=True)
            self.executor = ThreadPoolExecutor(max_workers=new_workers)

        return self.max_workers

    async def check_resources(self) -> Dict[str, Any]:
        """Check resource status and alerts"""
        usage = self.monitor.get_current_usage()
        alerts = self.monitor.check_thresholds(usage)

        return {
            "usage": usage.__dict__,
            "alerts": alerts,
            "status": "ok" if not alerts else "alert",
        }

    async def get_optimization_suggestions(self) -> Dict[str, Any]:
        """Get optimization suggestions"""
        usage = self.monitor.get_current_usage()

        suggestions = {
            "cpu": [],
            "memory": [],
            "disk": [],
            "network": [],
        }

        # CPU suggestions
        if usage.cpu_percent > 80:
            suggestions["cpu"].append("Reduce concurrent operations")
            suggestions["cpu"].append("Implement request batching")
            suggestions["cpu"].append("Use caching for frequently accessed data")

        # Memory suggestions
        if usage.memory_percent > 80:
            suggestions["memory"].append("Increase cache eviction policy")
            suggestions["memory"].append("Implement memory-efficient data structures")
            suggestions["memory"].append("Use lazy loading where possible")

        # Disk suggestions
        if usage.disk_percent > 80:
            suggestions["disk"].append("Clean up temporary files")
            suggestions["disk"].append("Compress old logs")
            suggestions["disk"].append("Archive old data")

        # Network suggestions
        network_usage = (
            usage.network_sent_bytes + usage.network_recv_bytes
        ) / (1024 * 1024)  # MB
        if network_usage > 100:  # 100 MB threshold
            suggestions["network"].append("Use compression for data transfer")
            suggestions["network"].append("Implement CDN for static assets")
            suggestions["network"].append("Use connection pooling")

        return suggestions

    def resource_limited(self, resource: str = "cpu", threshold: float = 80.0) -> bool:
        """Check if a specific resource is limited"""
        usage = self.monitor.get_current_usage()

        if resource == "cpu":
            return usage.cpu_percent >= threshold
        elif resource == "memory":
            return usage.memory_percent >= threshold
        elif resource == "disk":
            return usage.disk_percent >= threshold
        else:
            logger.warning(f"Unknown resource: {resource}")
            return False

    async def run_with_resource_limit(
        self,
        func: Callable[..., Any],
        *args,
        resource: str = "cpu",
        threshold: float = 80.0,
        fallback: Optional[Any] = None,
        **kwargs,
    ) -> Any:
        """Run function only if resource usage is below threshold"""
        if self.resource_limited(resource, threshold):
            logger.warning(
                f"Resource {resource} is limited, skipping execution of {func.__name__}"
            )
            return fallback

        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(self.executor, func, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in resource-limited execution: {e}")
            raise


def resource_aware(resource: str = "cpu", threshold: float = 80.0):
    """
    Decorator to make functions resource-aware.

    Args:
        resource: Resource to monitor
        threshold: Threshold percentage

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        optimizer = ResourceOptimizer()

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            if optimizer.resource_limited(resource, threshold):
                logger.warning(
                    f"Resource {resource} is limited, skipping execution of {func.__name__}"
                )
                return None

            return await func(*args, **kwargs)

        return wrapper

    return decorator

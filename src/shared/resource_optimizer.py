"""
Hardware Resource Optimization Module
Optimizes CPU, memory, disk I/O, and network resource usage for Minder services.
"""

import asyncio
import psutil
import logging
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("minder.resource_optimizer")


@dataclass
class ResourceUsage:
    """Current resource usage"""

    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_available_gb: float
    network_sent_bytes: int
    network_recv_bytes: int
    timestamp: datetime


@dataclass
class ResourceThresholds:
    """Resource usage thresholds"""

    cpu_warning: float = 70.0
    cpu_critical: float = 90.0
    memory_warning: float = 75.0
    memory_critical: float = 90.0
    disk_warning: float = 80.0
    disk_critical: float = 90.0


class ResourceMonitor:
    """Monitor system resources and trigger alerts"""

    def __init__(self, thresholds: Optional[ResourceThresholds] = None):
        self.thresholds = thresholds or ResourceThresholds()
        self._history: list[ResourceUsage] = []
        self._max_history_size = 1000

    def get_current_usage(self) -> ResourceUsage:
        """Get current resource usage"""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        network = psutil.net_io_counters()

        usage = ResourceUsage(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_available_mb=memory.available / (1024 * 1024),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024 * 1024 * 1024),
            disk_available_gb=disk.free / (1024 * 1024 * 1024),
            network_sent_bytes=network.bytes_sent,
            network_recv_bytes=network.bytes_recv,
            timestamp=datetime.now(),
        )

        # Store in history
        self._history.append(usage)
        if len(self._history) > self._max_history_size:
            self._history.pop(0)

        return usage

    def check_thresholds(self, usage: Optional[ResourceUsage] = None) -> Dict[str, str]:
        """Check if resource usage exceeds thresholds"""
        usage = usage or self.get_current_usage()
        alerts = {}

        if usage.cpu_percent >= self.thresholds.cpu_critical:
            alerts["cpu"] = f"CRITICAL: CPU usage at {usage.cpu_percent}%"
        elif usage.cpu_percent >= self.thresholds.cpu_warning:
            alerts["cpu"] = f"WARNING: CPU usage at {usage.cpu_percent}%"

        if usage.memory_percent >= self.thresholds.memory_critical:
            alerts["memory"] = f"CRITICAL: Memory usage at {usage.memory_percent}%"
        elif usage.memory_percent >= self.thresholds.memory_warning:
            alerts["memory"] = f"WARNING: Memory usage at {usage.memory_percent}%"

        if usage.disk_percent >= self.thresholds.disk_critical:
            alerts["disk"] = f"CRITICAL: Disk usage at {usage.disk_percent}%"
        elif usage.disk_percent >= self.thresholds.disk_warning:
            alerts["disk"] = f"WARNING: Disk usage at {usage.disk_percent}%"

        return alerts

    def get_average_usage(self, minutes: int = 5) -> ResourceUsage:
        """Get average resource usage over time period"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent = [u for u in self._history if u.timestamp >= cutoff_time]

        if not recent:
            return self.get_current_usage()

        avg_cpu = sum(u.cpu_percent for u in recent) / len(recent)
        avg_memory = sum(u.memory_percent for u in recent) / len(recent)

        # Return current usage with averaged CPU and memory
        current = recent[-1]
        return ResourceUsage(
            cpu_percent=avg_cpu,
            memory_percent=avg_memory,
            memory_used_mb=current.memory_used_mb,
            memory_available_mb=current.memory_available_mb,
            disk_percent=current.disk_percent,
            disk_used_gb=current.disk_used_gb,
            disk_available_gb=current.disk_available_gb,
            network_sent_bytes=current.network_sent_bytes,
            network_recv_bytes=current.network_recv_bytes,
            timestamp=datetime.now(),
        )


class ConnectionPoolOptimizer:
    """Optimize database and connection pool usage"""

    def __init__(
        self,
        min_connections: int = 5,
        max_connections: int = 20,
        target_utilization: float = 0.7,
    ):
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.target_utilization = target_utilization
        self._current_connections = min_connections

    def calculate_optimal_pool_size(
        self, concurrent_requests: int, avg_request_time_ms: float = 100.0
    ) -> int:
        """
        Calculate optimal connection pool size.

        Formula: pool_size = concurrent_requests * (1 + (wait_time / service_time))

        Args:
            concurrent_requests: Number of concurrent requests
            avg_request_time_ms: Average request processing time in ms

        Returns:
            Optimal pool size
        """
        # Estimate wait time (assume 20% of request time)
        wait_time_ms = avg_request_time_ms * 0.2

        # Little's Law
        optimal_size = concurrent_requests * (1 + (wait_time_ms / avg_request_time_ms))

        # Clamp to min/max
        optimal_size = max(self.min_connections, min(optimal_size, self.max_connections))

        return int(optimal_size)

    def should_increase_pool(self, utilization: float, queue_length: int) -> bool:
        """Check if pool size should be increased"""
        return utilization > self.target_utilization and queue_length > 0 and self._current_connections < self.max_connections

    def should_decrease_pool(self, utilization: float, queue_length: int) -> bool:
        """Check if pool size should be decreased"""
        return utilization < self.target_utilization - 0.2 and queue_length == 0 and self._current_connections > self.min_connections


class MemoryOptimizer:
    """Optimize memory usage"""

    @staticmethod
    def get_memory_usage_by_type() -> Dict[str, float]:
        """Get memory usage breakdown by type"""
        memory_info = psutil.virtual_memory()

        return {
            "total_gb": memory_info.total / (1024**3),
            "available_gb": memory_info.available / (1024**3),
            "used_gb": memory_info.used / (1024**3),
            "free_gb": memory_info.free / (1024**3),
            "cached_gb": memory_info.cached / (1024**3),
            "buffers_gb": memory_info.buffers / (1024**3),
        }

    @staticmethod
    def optimize_caches(cache_sizes: Dict[str, int]) -> Dict[str, int]:
        """
        Optimize cache sizes based on available memory.

        Args:
            cache_sizes: Current cache sizes

        Returns:
            Optimized cache sizes
        """
        memory_info = psutil.virtual_memory()
        available_memory_gb = memory_info.available / (1024**3)

        # Reserve 20% of available memory for other processes
        allocatable_memory_gb = available_memory_gb * 0.8
        allocatable_memory_mb = allocatable_memory_gb * 1024

        total_current = sum(cache_sizes.values())

        if total_current > allocatable_memory_mb:
            # Scale down proportionally
            scale_factor = allocatable_memory_mb / total_current
            optimized = {k: int(v * scale_factor) for k, v in cache_sizes.items()}
            return optimized

        return cache_sizes

    @staticmethod
    def check_memory_pressure() -> str:
        """Check if system is under memory pressure"""
        memory_info = psutil.virtual_memory()

        if memory_info.percent >= 90:
            return "critical"
        elif memory_info.percent >= 75:
            return "warning"
        elif memory_info.percent >= 50:
            return "moderate"
        else:
            return "normal"


class CPUOptimizer:
    """Optimize CPU usage"""

    @staticmethod
    def get_cpu_info() -> Dict[str, Any]:
        """Get CPU information"""
        return {
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "current_usage_percent": psutil.cpu_percent(interval=0.1),
            "frequency_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None,
        }

    @staticmethod
    def get_cpu_times() -> Dict[str, float]:
        """Get CPU time breakdown"""
        cpu_times = psutil.cpu_times()

        return {
            "user_seconds": cpu_times.user,
            "system_seconds": cpu_times.system,
            "idle_seconds": cpu_times.idle,
            "iowait_seconds": cpu_times.iowait if hasattr(cpu_times, "iowait") else 0.0,
        }

    @staticmethod
    def optimize_thread_pool_size(io_bound: bool = False, cpu_count: Optional[int] = None) -> int:
        """
        Calculate optimal thread pool size.

        Args:
            io_bound: If True, use larger pool for I/O-bound tasks
            cpu_count: Override CPU count

        Returns:
            Optimal thread pool size
        """
        cpu_count = cpu_count or psutil.cpu_count(logical=True)

        if io_bound:
            # I/O-bound tasks: pool size = number of cores * 2
            return cpu_count * 2
        else:
            # CPU-bound tasks: pool size = number of cores + 1
            return cpu_count + 1


class DiskOptimizer:
    """Optimize disk I/O"""

    @staticmethod
    def get_disk_usage(path: str = "/") -> Dict[str, float]:
        """Get disk usage"""
        disk = psutil.disk_usage(path)

        return {
            "total_gb": disk.total / (1024**3),
            "used_gb": disk.used / (1024**3),
            "free_gb": disk.free / (1024**3),
            "percent": disk.percent,
        }

    @staticmethod
    def get_disk_io_stats() -> Dict[str, float]:
        """Get disk I/O statistics"""
        disk_io = psutil.disk_io_counters()

        return {
            "read_bytes": disk_io.read_bytes,
            "write_bytes": disk_io.write_bytes,
            "read_count": disk_io.read_count,
            "write_count": disk_io.write_count,
        }

    @staticmethod
    def check_disk_space(path: str = "/", warning_threshold: float = 80.0) -> str:
        """Check disk space status"""
        disk = psutil.disk_usage(path)

        if disk.percent >= 90:
            return "critical"
        elif disk.percent >= warning_threshold:
            return "warning"
        elif disk.percent >= 50:
            return "moderate"
        else:
            return "normal"


class NetworkOptimizer:
    """Optimize network usage"""

    @staticmethod
    def get_network_stats() -> Dict[str, Any]:
        """Get network statistics"""
        network = psutil.net_io_counters()

        return {
            "bytes_sent": network.bytes_sent,
            "bytes_recv": network.bytes_recv,
            "packets_sent": network.packets_sent,
            "packets_recv": network.packets_recv,
            "errors_in": network.errin,
            "errors_out": network.errout,
            "drops_in": network.dropin,
            "drops_out": network.dropout,
        }

    @staticmethod
    def get_network_connections() -> Dict[str, int]:
        """Get network connection counts"""
        connections = psutil.net_connections(kind="inet")

        status_counts: Dict[str, int] = {}
        for conn in connections:
            status = conn.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return status_counts


class AdaptiveExecutor:
    """Adaptive executor that adjusts based on system load"""

    def __init__(
        self,
        max_workers: Optional[int] = None,
        min_workers: int = 2,
        monitor: Optional[ResourceMonitor] = None,
    ):
        self.max_workers = max_workers or psutil.cpu_count(logical=True)
        self.min_workers = min_workers
        self.monitor = monitor or ResourceMonitor()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._current_workers = min_workers

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with adaptive worker count"""
        # Get current resource usage
        usage = self.monitor.get_current_usage()

        # Adjust worker count based on CPU usage
        if usage.cpu_percent > 80:
            # Reduce workers under high CPU load
            target_workers = self.min_workers
        elif usage.cpu_percent < 50:
            # Increase workers under low CPU load
            target_workers = min(self.max_workers, self._current_workers + 2)
        else:
            # Maintain current workers
            target_workers = self._current_workers

        # Update executor if needed
        if target_workers != self._current_workers:
            self._resize_executor(target_workers)

        # Execute function
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, func, *args, **kwargs)

    def _resize_executor(self, target_workers: int):
        """Resize executor to target worker count"""
        if self._executor:
            self._executor.shutdown(wait=False)

        self._current_workers = target_workers
        self._executor = ThreadPoolExecutor(max_workers=target_workers)

    async def shutdown(self):
        """Shutdown executor"""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


def resource_limit_check(
    cpu_limit: float = 80.0,
    memory_limit: float = 80.0,
):
    """
    Decorator to check resource limits before executing function.

    Args:
        cpu_limit: Maximum CPU usage percentage
        memory_limit: Maximum memory usage percentage
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            monitor = ResourceMonitor()
            usage = monitor.get_current_usage()

            if usage.cpu_percent > cpu_limit:
                logger.warning(f"CPU usage {usage.cpu_percent}% exceeds limit {cpu_limit}%")
                # Could queue the request or return error

            if usage.memory_percent > memory_limit:
                logger.warning(
                    f"Memory usage {usage.memory_percent}% exceeds limit {memory_limit}%"
                )
                # Could queue the request or return error

            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def optimize_resources_continuously(
    check_interval: int = 60,
    thresholds: Optional[ResourceThresholds] = None,
    alert_callback: Optional[Callable[[Dict[str, str]], None]] = None,
):
    """
    Continuously monitor and optimize resources.

    Args:
        check_interval: Check interval in seconds
        thresholds: Resource thresholds
        alert_callback: Callback for alerts
    """
    monitor = ResourceMonitor(thresholds)

    while True:
        try:
            alerts = monitor.check_thresholds()

            if alerts and alert_callback:
                if asyncio.iscoroutinefunction(alert_callback):
                    await alert_callback(alerts)

            logger.debug(f"Resource check: {monitor.get_current_usage()}")

        except Exception as e:
            logger.error(f"Error monitoring resources: {e}")

        await asyncio.sleep(check_interval)

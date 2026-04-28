"""
Resource monitoring for Minder.
Monitors CPU, memory, disk, and network usage.
"""

import psutil
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger("minder.resource_monitor")


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
        """
        Initialize resource monitor.

        Args:
            thresholds: Resource usage thresholds
        """
        self.thresholds = thresholds or ResourceThresholds()
        self._history: List[ResourceUsage] = []
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

    def get_history(self, hours: int = 1) -> List[ResourceUsage]:
        """Get resource usage history"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [usage for usage in self._history if usage.timestamp >= cutoff]

    def get_average_usage(self, hours: int = 1) -> ResourceUsage:
        """Get average resource usage over time period"""
        history = self.get_history(hours)

        if not history:
            return self.get_current_usage()

        avg_cpu = sum(u.cpu_percent for u in history) / len(history)
        avg_memory = sum(u.memory_percent for u in history) / len(history)
        avg_disk = sum(u.disk_percent for u in history) / len(history)

        return ResourceUsage(
            cpu_percent=avg_cpu,
            memory_percent=avg_memory,
            memory_used_mb=sum(u.memory_used_mb for u in history) / len(history),
            memory_available_mb=sum(u.memory_available_mb for u in history) / len(history),
            disk_percent=avg_disk,
            disk_used_gb=sum(u.disk_used_gb for u in history) / len(history),
            disk_available_gb=sum(u.disk_available_gb for u in history) / len(history),
            network_sent_bytes=sum(u.network_sent_bytes for u in history) / len(history),
            network_recv_bytes=sum(u.network_recv_bytes for u in history) / len(history),
            timestamp=datetime.now(),
        )

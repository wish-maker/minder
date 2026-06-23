"""
Raspberry Pi 4 Resource Manager

Manages system resources for RAG pipeline operations on RPi 4 hardware.
Implements throttling, concurrency control, and resource monitoring.

This is an infrastructure component with system-level dependencies.
"""

import asyncio
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class Pi4ResourceManager:
    """
    Raspberry Pi 4 resource manager for RAG pipeline

    Monitors and manages RPi 4 resources to prevent system overload:
    - Memory usage monitoring
    - CPU load tracking
    - Thermal throttling at 80°C
    - Concurrency limiting (max 2 requests)

    Features:
    - Resource availability checking
    - Automatic throttling when constrained
    - Semaphore-based concurrency control
    - Configurable resource thresholds

    Attributes:
        max_concurrent_requests (int): Max concurrent requests (default: 2)
        max_memory_mb (int): Max memory for RAG pipeline (default: 4000)
        cpu_threshold (int): Thermal throttle threshold in °C (default: 80)
        request_semaphore (asyncio.Semaphore): Concurrency control
        embedding_batch_size (int): Batch size for embedding generation

    Example:
        >>> manager = Pi4ResourceManager()
        >>> await manager.throttle_if_needed()
        >>> async with manager.request_semaphore:
        ...     # Process request
        ...     pass
    """

    def __init__(
        self,
        max_concurrent_requests: int = 2,
        max_memory_mb: int = 4000,
        cpu_threshold: int = 80,
        embedding_batch_size: int = 5,
    ):
        """
        Initialize RPi 4 resource manager

        Args:
            max_concurrent_requests: Max concurrent requests (RPi 4 constraint)
            max_memory_mb: Max memory allocation in MB
            cpu_threshold: Thermal throttle threshold in Celsius
            embedding_batch_size: Batch size for embedding generation

        Raises:
            ValueError: If parameters invalid
        """
        if max_concurrent_requests <= 0:
            raise ValueError(
                f"max_concurrent_requests must be positive, got {max_concurrent_requests}"
            )

        if max_memory_mb <= 0:
            raise ValueError(f"max_memory_mb must be positive, got {max_memory_mb}")

        if not 0 < cpu_threshold <= 100:
            raise ValueError(f"cpu_threshold must be in (0, 100], got {cpu_threshold}")

        if embedding_batch_size <= 0:
            raise ValueError(
                f"embedding_batch_size must be positive, got {embedding_batch_size}"
            )

        self.max_concurrent_requests = max_concurrent_requests
        self.max_memory_mb = max_memory_mb
        self.cpu_threshold = cpu_threshold
        self.request_semaphore = asyncio.Semaphore(max_concurrent_requests)
        self.embedding_batch_size = embedding_batch_size

        logger.info(
            f"✅ Pi4ResourceManager initialized: "
            f"max_concurrent={max_concurrent_requests}, "
            f"max_memory={max_memory_mb}MB, "
            f"cpu_threshold={cpu_threshold}°C"
        )

    async def check_resources(self) -> Dict[str, Any]:
        """
        Check available resources before processing

        Reads system metrics:
        - Available memory from /proc/meminfo
        - CPU load from /proc/loadavg
        - Temperature from /sys/class/thermal/thermal_zone0/temp

        Returns:
            Dict with keys:
                available_memory_mb (int): Available memory in MB
                cpu_load (float): 1-minute CPU load average
                temperature_c (float): CPU temperature in Celsius
                can_process (bool): Whether resources are sufficient

        Note:
            Returns optimistic default (can_process=True) if checks fail
        """
        try:
            # Read memory info
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
                available = (
                    int(
                        [
                            line
                            for line in meminfo.split("\n")
                            if "MemAvailable" in line
                        ][0].split()[1]
                    )
                    // 1024
                )  # Convert KB to MB

            # Read CPU load
            with open("/proc/loadavg", "r") as f:
                load = float(f.read().split()[0])  # 1-minute load average

            # Read thermal
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temp = (
                        int(f.read().strip()) / 1000
                    )  # Convert millidegrees to Celsius
            except (FileNotFoundError, ValueError, IndexError):
                temp = 0  # Thermal read failed
                logger.debug("Unable to read CPU temperature")

            # Determine if resources are sufficient
            can_process = available > 1000 and load < 10.0 and temp < self.cpu_threshold

            return {
                "available_memory_mb": available,
                "cpu_load": load,
                "temperature_c": temp,
                "can_process": can_process,
            }

        except Exception as e:
            logger.warning(f"Resource check failed: {e}")
            return {"can_process": True}  # Optimistic default

    async def throttle_if_needed(self) -> None:
        """
        Throttle if resources constrained

        Blocks until resources are sufficient for processing.
        Implements exponential backoff based on temperature.

        Note:
            Wait time increases with temperature (up to 5 seconds max)
        """
        while True:
            resources = await self.check_resources()

            if not resources["can_process"]:
                # Calculate wait time based on temperature
                temp = resources.get("temperature_c", 0)
                wait_time = min(5, temp / 20 if temp > 0 else 1)

                logger.warning(
                    f"⏳ Throttling: {resources.get('available_memory_mb')}MB available, "
                    f"{resources.get('cpu_load'):.2f} load, "
                    f"{temp:.1f}°C"
                )

                await asyncio.sleep(wait_time)
            else:
                break

        logger.debug("✅ Resources sufficient for processing")

"""
Connection pool management for Minder.
Implements optimal connection pool sizing based on Little's Law.
"""

import asyncpg
import logging
import math
from typing import Optional, Dict, Any

logger = logging.getLogger("minder.connection_pool")


class ConnectionPoolOptimizer:
    """
    Connection pool optimizer for Minder.
    Provides optimal pool sizing based on Little's Law.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        target_throughput: float = 1000.0,
        target_latency_ms: float = 100.0,
        max_connections: int = 100
    ):
        """
        Initialize connection pool optimizer.

        Args:
            pool: Database connection pool
            target_throughput: Target queries per second
            target_latency_ms: Target average query latency
            max_connections: Maximum number of connections
        """
        self.pool = pool
        self.target_throughput = target_throughput
        self.target_latency_ms = target_latency_ms
        self.max_connections = max_connections

    async def calculate_optimal_pool_size(self) -> int:
        """
        Calculate optimal pool size based on Little's Law.

        Returns:
            Optimal pool size
        """
        try:
            # Get current pool statistics
            min_size = self.pool.get_min_size()
            max_size = self.pool.get_max_size()
            current_size = self.pool.get_size()
            idle_size = self.pool.get_idle_size()

            logger.info(f"Current pool stats: min={min_size}, max={max_size}, current={current_size}, idle={idle_size}")

            # Calculate optimal pool size using Little's Law
            # L = λ * W (Number in system = Arrival rate * Time in system)
            # Rearranged for pool size: pool_size = throughput * latency

            target_latency_seconds = self.target_latency_ms / 1000.0
            optimal_size = math.ceil(self.target_throughput * target_latency_seconds)

            # Constrain to max connections
            optimal_size = min(optimal_size, self.max_connections)

            logger.info(f"Optimal pool size: {optimal_size}")
            return optimal_size

        except Exception as e:
            logger.error(f"Failed to calculate optimal pool size: {e}")
            return max_size // 2

    async def get_pool_metrics(self) -> Dict[str, Any]:
        """
        Get current pool metrics.

        Returns:
            Dictionary of pool metrics
        """
        try:
            metrics = {
                "min_size": self.pool.get_min_size(),
                "max_size": self.pool.get_max_size(),
                "current_size": self.pool.get_size(),
                "idle_size": self.pool.get_idle_size(),
                "available_size": self.pool.get_idle_size(),  # alias
            }

            return metrics

        except Exception as e:
            logger.error(f"Failed to get pool metrics: {e}")
            return {}

    async def resize_pool(self, new_size: int) -> bool:
        """
        Resize the connection pool.

        Args:
            new_size: New pool size

        Returns:
            True if successful
        """
        try:
            # Note: asyncpg doesn't support direct pool resizing
            # This is a placeholder for future implementation
            logger.info(f"Resize pool to {new_size} (not yet implemented)")
            return False

        except Exception as e:
            logger.error(f"Failed to resize pool: {e}")
            return False

    async def tune_pool_for_workload(self) -> Dict[str, Any]:
        """
        Tune pool for current workload.

        Returns:
            Dictionary of tuning recommendations
        """
        try:
            # Get current metrics
            metrics = await self.get_pool_metrics()
            optimal_size = await self.calculate_optimal_pool_size()

            # Calculate utilization
            current_size = metrics["current_size"]
            idle_size = metrics["idle_size"]
            active_size = current_size - idle_size
            utilization = (active_size / current_size) * 100 if current_size > 0 else 0

            recommendations = {}

            # High utilization - increase pool
            if utilization > 80:
                recommended_size = min(optimal_size, self.max_connections)
                recommendations["action"] = "increase_pool"
                recommendations["current_size"] = current_size
                recommendations["recommended_size"] = recommended_size
                recommendations["reason"] = f"High utilization: {utilization:.1f}%"

            # Low utilization - decrease pool
            elif utilization < 20:
                recommended_size = max(optimal_size, metrics["min_size"])
                recommendations["action"] = "decrease_pool"
                recommendations["current_size"] = current_size
                recommendations["recommended_size"] = recommended_size
                recommendations["reason"] = f"Low utilization: {utilization:.1f}%"

            # Optimal - no change
            else:
                recommendations["action"] = "no_change"
                recommendations["current_size"] = current_size
                recommendations["utilization"] = f"{utilization:.1f}%"
                recommendations["reason"] = "Pool size is optimal"

            logger.info(f"Pool tuning recommendations: {recommendations}")
            return recommendations

        except Exception as e:
            logger.error(f"Failed to tune pool: {e}")
            return {"error": str(e)}

    def calculate_littles_law(
        self,
        throughput: float,
        latency_seconds: float
    ) -> float:
        """
        Apply Little's Law to calculate required resources.

        Args:
            throughput: Requests per second
            latency_seconds: Average time per request

        Returns:
            Required number of connections
        """
        return throughput * latency_seconds

    def estimate_throughput(
        self,
        connections: int,
        latency_seconds: float
    ) -> float:
        """
        Estimate maximum throughput.

        Args:
            connections: Number of connections
            latency_seconds: Average time per request

        Returns:
            Estimated throughput (requests per second)
        """
        return connections / latency_seconds

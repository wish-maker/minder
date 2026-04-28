"""
Database optimizer main class for Minder.
Coordinates query optimization, index management, and connection pooling.
"""

import asyncpg
import logging
from typing import List, Dict, Any, Optional

from .models import QueryPlan, IndexRecommendation, TableStatistics
from .query_optimizer import QueryOptimizer
from .index_manager import IndexManager
from .connection_pool import ConnectionPoolOptimizer

logger = logging.getLogger("minder.database_optimizer")


class DatabaseOptimizer:
    """
    Database optimizer for Minder.
    Coordinates query optimization, index management, and connection pooling.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        target_throughput: float = 1000.0,
        target_latency_ms: float = 100.0,
        max_connections: int = 100
    ):
        """
        Initialize database optimizer.

        Args:
            pool: Database connection pool
            target_throughput: Target queries per second
            target_latency_ms: Target average query latency
            max_connections: Maximum number of connections
        """
        self.pool = pool
        self.query_optimizer = QueryOptimizer(pool)
        self.index_manager = IndexManager(pool)
        self.connection_pool_optimizer = ConnectionPoolOptimizer(
            pool,
            target_throughput=target_throughput,
            target_latency_ms=target_latency_ms,
            max_connections=max_connections
        )

    async def analyze_slow_queries(self, threshold_ms: int = 100) -> List[Dict[str, Any]]:
        """
        Analyze slow queries from pg_stat_statements.

        Args:
            threshold_ms: Minimum execution time to consider slow

        Returns:
            List of slow query information
        """
        return await self.query_optimizer.analyze_slow_queries(threshold_ms)

    async def explain_query(self, query: str, params: Optional[List[Any]] = None) -> QueryPlan:
        """
        Get query execution plan.

        Args:
            query: SQL query to explain
            params: Query parameters

        Returns:
            QueryPlan with execution plan
        """
        return await self.query_optimizer.explain_query(query, params)

    async def generate_index_recommendations(self) -> List[IndexRecommendation]:
        """
        Generate index recommendations based on query patterns.

        Returns:
            List of index recommendations
        """
        return await self.index_manager.generate_index_recommendations()

    async def optimize_pool(self) -> Dict[str, Any]:
        """
        Optimize connection pool for current workload.

        Returns:
            Dictionary of tuning recommendations
        """
        return await self.connection_pool_optimizer.tune_pool_for_workload()

    async def get_pool_metrics(self) -> Dict[str, Any]:
        """
        Get current pool metrics.

        Returns:
            Dictionary of pool metrics
        """
        return await self.connection_pool_optimizer.get_pool_metrics()

    async def optimize_database(self) -> Dict[str, Any]:
        """
        Run comprehensive database optimization.

        Returns:
            Dictionary of optimization results
        """
        results = {
            "slow_queries": [],
            "index_recommendations": [],
            "pool_recommendations": {}
        }

        # Analyze slow queries
        try:
            slow_queries = await self.analyze_slow_queries()
            results["slow_queries"] = [
                {
                    "query": sq.query,
                    "calls": sq.calls,
                    "mean_time_ms": sq.mean_time_ms,
                    "max_time_ms": sq.max_time_ms
                }
                for sq in slow_queries
            ]
        except Exception as e:
            logger.error(f"Failed to analyze slow queries: {e}")

        # Generate index recommendations
        try:
            index_recommendations = await self.generate_index_recommendations()
            results["index_recommendations"] = [
                {
                    "table": ir.table,
                    "columns": ir.columns,
                    "index_type": ir.index_type,
                    "estimated_impact": ir.estimated_impact,
                    "reason": ir.reason
                }
                for ir in index_recommendations
            ]
        except Exception as e:
            logger.error(f"Failed to generate index recommendations: {e}")

        # Optimize pool
        try:
            pool_recommendations = await self.optimize_pool()
            results["pool_recommendations"] = pool_recommendations
        except Exception as e:
            logger.error(f"Failed to optimize pool: {e}")

        logger.info(f"Database optimization complete: {results}")
        return results

    async def create_index(self, table: str, columns: List[str], index_type: str = "btree") -> bool:
        """
        Create an index on a table.

        Args:
            table: Table name
            columns: List of column names
            index_type: Index type (btree, hash, gin, etc.)

        Returns:
            True if successful
        """
        return await self.index_manager.create_index(table, columns, index_type)

    async def drop_index(self, table: str, columns: List[str]) -> bool:
        """
        Drop an index from a table.

        Args:
            table: Table name
            columns: List of column names

        Returns:
            True if successful
        """
        return await self.index_manager.drop_index(table, columns)

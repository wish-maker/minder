"""
Query optimization for Minder.
Implements query analysis and optimization strategies.
"""

import asyncpg
import logging
import re
from typing import List, Dict, Any, Optional

from .models import QueryPlan, SlowQuery

logger = logging.getLogger("minder.query_optimizer")


class QueryOptimizer:
    """
    Query optimizer for Minder.
    Provides query analysis and optimization strategies.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize query optimizer.

        Args:
            pool: Database connection pool
        """
        self.pool = pool

    async def analyze_slow_queries(self, threshold_ms: int = 100) -> List[SlowQuery]:
        """
        Analyze slow queries from pg_stat_statements.

        Args:
            threshold_ms: Minimum execution time to consider slow

        Returns:
            List of slow query information
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        query,
                        calls,
                        total_time,
                        mean_time,
                        max_time,
                        rows
                    FROM pg_stat_statements
                    WHERE mean_time > $1
                    ORDER BY mean_time DESC
                    LIMIT 10
                """, threshold_ms)

                slow_queries = [
                    SlowQuery(
                        query=row["query"],
                        calls=row["calls"],
                        total_time_ms=row["total_time"],
                        mean_time_ms=row["mean_time"],
                        max_time_ms=row["max_time"],
                        rows=row["rows"]
                    )
                    for row in rows
                ]

                logger.info(f"Found {len(slow_queries)} slow queries")
                return slow_queries

        except Exception as e:
            logger.error(f"Failed to analyze slow queries: {e}")
            return []

    async def explain_query(self, query: str, params: Optional[List[Any]] = None) -> QueryPlan:
        """
        Get query execution plan.

        Args:
            query: SQL query to explain
            params: Query parameters

        Returns:
            QueryPlan with execution plan
        """
        try:
            async with self.pool.acquire() as conn:
                plan_rows = await conn.fetch(f"EXPLAIN (FORMAT JSON, ANALYZE) {query}", *(params or []))
                plan_str = plan_rows[0]["QUERY PLAN"]
                estimated_cost = self._extract_cost(plan_str)

                return QueryPlan(
                    query=query,
                    plan=plan_str,
                    estimated_cost=estimated_cost
                )

        except Exception as e:
            logger.error(f"Failed to explain query: {e}")
            raise

    def _extract_cost(self, plan_str: str) -> float:
        """Extract estimated cost from execution plan"""
        # Simple cost extraction - can be improved with regex
        if "Cost=" in plan_str:
            try:
                cost_match = re.search(r'Cost=(\d+\.\d+)', plan_str)
                if cost_match:
                    return float(cost_match.group(1))
            except Exception:
                pass
        return 0.0

    async def optimize_query(self, query: str) -> List[str]:
        """
        Suggest optimizations for a query.

        Args:
            query: SQL query to optimize

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        # Check for SELECT *
        if "SELECT *" in query.upper():
            suggestions.append("Consider specifying columns instead of SELECT *")

        # Check for missing WHERE clause
        if "WHERE" not in query.upper() and query.upper().startswith("SELECT"):
            suggestions.append("Consider adding a WHERE clause to limit results")

        # Check for ORDER BY without LIMIT
        if "ORDER BY" in query.upper() and "LIMIT" not in query.upper():
            suggestions.append("Consider adding LIMIT to ORDER BY queries")

        # Check for LIKE without leading wildcard
        if "LIKE" in query.upper() and query.startswith("%"):
            suggestions.append("Consider removing leading wildcard for better performance")

        return suggestions

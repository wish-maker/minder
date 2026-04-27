"""
Database optimization strategies for Minder.
Implements query optimization, indexing, and connection pooling.
"""

import asyncio
import asyncpg
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger("minder.database_optimization")


@dataclass
class QueryPlan:
    """Represents a query execution plan"""
    query: str
    plan: str
    estimated_cost: float
    actual_cost: Optional[float] = None


@dataclass
class IndexRecommendation:
    """Represents an index recommendation"""
    table: str
    columns: List[str]
    index_type: str
    estimated_impact: str
    reason: str


class DatabaseOptimizer:
    """
    Database optimizer for Minder.
    Provides query optimization, indexing, and connection pooling.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize database optimizer.

        Args:
            pool: Database connection pool
        """
        self.pool = pool
        self.recommendations: List[IndexRecommendation] = []

    async def analyze_slow_queries(self, threshold_ms: int = 100) -> List[Dict[str, Any]]:
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
                    {
                        "query": row["query"],
                        "calls": row["calls"],
                        "total_time_ms": row["total_time"],
                        "mean_time_ms": row["mean_time"],
                        "max_time_ms": row["max_time"],
                        "rows": row["rows"]
                    }
                    for row in rows
                ]

                logger.info(f"Found {len(slow_queries)} slow queries")
                return slow_queries

        except Exception as e:
            logger.error(f"Failed to analyze slow queries: {e}")
            return []

    async def explain_query(self, query: str, params: List[Any] = None) -> QueryPlan:
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
                import re
                cost_match = re.search(r'Cost=(\d+\.\d+)', plan_str)
                if cost_match:
                    return float(cost_match.group(1))
            except:
                pass
        return 0.0

    async def generate_index_recommendations(self) -> List[IndexRecommendation]:
        """
        Generate index recommendations based on query patterns.

        Returns:
            List of index recommendations
        """
        self.recommendations = []

        try:
            async with self.pool.acquire() as conn:
                # Analyze missing indexes from pg_stat_user_tables
                tables = await conn.fetch("""
                    SELECT
                        schemaname,
                        tablename,
                        n_live_tup as row_count
                    FROM pg_stat_user_tables
                    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY n_live_tup DESC
                    LIMIT 20
                """)

                for table in tables:
                    await self._analyze_table_indexes(conn, table)

            logger.info(f"Generated {len(self.recommendations)} index recommendations")
            return self.recommendations

        except Exception as e:
            logger.error(f"Failed to generate index recommendations: {e}")
            return []

    async def _analyze_table_indexes(
        self,
        conn: asyncpg.Connection,
        table: Dict[str, Any]
    ):
        """Analyze indexes for a specific table"""
        schema_name = table["schemaname"]
        table_name = table["tablename"]
        row_count = table["row_count"]

        # Get existing indexes
        indexes = await conn.fetch("""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = $1 AND tablename = $2
        """, schema_name, table_name)

        existing_columns = set()
        for idx in indexes:
            columns = self._extract_index_columns(idx["indexdef"])
            existing_columns.update(columns)

        # Check for common patterns that need indexes
        # Pattern 1: Tables with many rows but few indexes
        if row_count > 1000 and len(indexes) < 2:
            self.recommendations.append(IndexRecommendation(
                table=f"{schema_name}.{table_name}",
                columns=["id"],
                index_type="btree",
                estimated_impact="High",
                reason=f"Large table with {row_count} rows needs primary index"
            ))

        # Pattern 2: Foreign key columns without indexes
        fk_columns = await self._get_foreign_key_columns(conn, schema_name, table_name)
        for fk_col in fk_columns:
            if fk_col not in existing_columns:
                self.recommendations.append(IndexRecommendation(
                    table=f"{schema_name}.{table_name}",
                    columns=[fk_col],
                    index_type="btree",
                    estimated_impact="Medium",
                    reason=f"Foreign key column {fk_col} not indexed"
                ))

        # Pattern 3: Tables with sequential access patterns
        if row_count > 10000:
            self.recommendations.append(IndexRecommendation(
                table=f"{schema_name}.{table_name}",
                columns=["created_at", "updated_at"],
                index_type="btree",
                estimated_impact="Medium",
                reason="Timestamp columns often used in range queries"
            ))

    async def _get_foreign_key_columns(
        self,
        conn: asyncpg.Connection,
        schema: str,
        table: str
    ) -> List[str]:
        """Get foreign key columns for a table"""
        try:
            rows = await conn.fetch("""
                SELECT
                    a.attname as column_name
                FROM pg_constraint c
                JOIN pg_attribute a ON a.attnum = ANY(c.conkey)
                WHERE
                    c.conrelid = (
                        SELECT oid FROM pg_class WHERE relname = $2 AND relnamespace = (
                            SELECT oid FROM pg_namespace WHERE nspname = $1
                        )
                    )
                    AND c.contype = 'f'
            """, schema, table)

            return [row["column_name"] for row in rows]

        except Exception as e:
            logger.warning(f"Failed to get foreign key columns: {e}")
            return []

    def _extract_index_columns(self, index_def: str) -> List[str]:
        """Extract column names from index definition"""
        import re
        # Simple column extraction - can be improved
        match = re.search(r'\((.*?)\)', index_def)
        if match:
            columns_str = match.group(1)
            columns = [col.strip().split()[0] for col in columns_str.split(',')]
            return columns
        return []

    async def create_recommendation(
        self,
        recommendation: IndexRecommendation
    ) -> bool:
        """
        Create an index based on recommendation.

        Args:
            recommendation: Index recommendation to implement

        Returns:
            True if successful
        """
        try:
            async with self.pool.acquire() as conn:
                index_name = f"idx_{recommendation.table.replace('.', '_')}_{'_'.join(recommendation.columns)}"
                columns_str = ', '.join(recommendation.columns)

                query = f"""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                    ON {recommendation.table} USING {recommendation.index_type} ({columns_str})
                """

                await conn.execute(query)

                logger.info(f"Created index {index_name} on {recommendation.table}")
                return True

        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False

    async def optimize_database(self, aggressive: bool = False) -> Dict[str, Any]:
        """
        Perform database optimization.

        Args:
            aggressive: If True, perform more aggressive optimization

        Returns:
            Dictionary with optimization results
        """
        results = {
            "vacuum_analyzed": False,
            "indexes_created": 0,
            "statistics_updated": False,
            "queries_analyzed": 0
        }

        try:
            async with self.pool.acquire() as conn:
                # VACUUM ANALYZE
                logger.info("Running VACUUM ANALYZE")
                if aggressive:
                    await conn.execute("VACUUM ANALYZE")
                    results["vacuum_analyzed"] = True
                else:
                    # Non-aggressive vacuum
                    await conn.execute("VACUUM (ANALYZE, VERBOSE, INDEX_CLEANUP OFF)")
                    results["vacuum_analyzed"] = True

                # Update statistics
                logger.info("Updating statistics")
                await conn.execute("ANALYZE")
                results["statistics_updated"] = True

                # Analyze slow queries
                slow_queries = await self.analyze_slow_queries()
                results["queries_analyzed"] = len(slow_queries)

                # Generate and apply index recommendations
                recommendations = await self.generate_index_recommendations()
                for rec in recommendations:
                    if rec.estimated_impact == "High" or aggressive:
                        success = await self.create_recommendation(rec)
                        if success:
                            results["indexes_created"] += 1

            logger.info("Database optimization completed")
            return results

        except Exception as e:
            logger.error(f"Database optimization failed: {e}")
            raise

    async def get_connection_pool_stats(self) -> Dict[str, Any]:
        """
        Get connection pool statistics.

        Returns:
            Dictionary with pool statistics
        """
        try:
            pool_stats = {
                "min_size": self.pool._min,
                "max_size": self.pool._max,
                "size": self.pool._queue.qsize(),
                "available": self.pool._queue.qsize(),
                "used": self.pool._max - self.pool._queue.qsize()
            }

            # Get active connections
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT
                        count(*) as total_connections,
                        count(*) filter (where state = 'active') as active_connections,
                        count(*) filter (where state = 'idle') as idle_connections
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                """)

                pool_stats.update({
                    "total_db_connections": row["total_connections"],
                    "active_db_connections": row["active_connections"],
                    "idle_db_connections": row["idle_db_connections"]
                })

            return pool_stats

        except Exception as e:
            logger.error(f"Failed to get pool stats: {e}")
            return {}

    async def recommend_pool_size(self) -> Dict[str, int]:
        """
        Recommend optimal pool size based on workload.

        Returns:
            Dictionary with recommended pool settings
        """
        try:
            async with self.pool.acquire() as conn:
                # Get database size
                row = await conn.fetchrow("""
                    SELECT
                        pg_database_size(current_database()) as db_size,
                        pg_size_pretty(pg_database_size(current_database())) as db_size_pretty
                """)

                db_size_mb = row["db_size"] / (1024 * 1024)

                # Get active connections
                active_row = await conn.fetchrow("""
                    SELECT count(*) as active_connections
                    FROM pg_stat_activity
                    WHERE state = 'active' AND datname = current_database()
                """)

                active_conns = active_row["active_connections"]

                # Simple formula: (2 * CPU cores) + effective_disk_count
                # Default to conservative values if we can't get exact metrics
                recommended_min = max(5, active_conns * 2)
                recommended_max = max(20, active_conns * 4)

                # Adjust based on database size
                if db_size_mb > 1000:  # Large database
                    recommended_max = min(100, recommended_max * 2)

                return {
                    "min_size": recommended_min,
                    "max_size": recommended_max
                }

        except Exception as e:
            logger.error(f"Failed to recommend pool size: {e}")
            return {
                "min_size": 10,
                "max_size": 50
            }


class QueryCache:
    """
    Simple query cache for frequently executed queries.
    Uses Redis for distributed caching.
    """

    def __init__(self, redis_client, default_ttl: int = 300):
        """
        Initialize query cache.

        Args:
            redis_client: Redis client
            default_ttl: Default TTL in seconds
        """
        self.redis = redis_client
        self.default_ttl = default_ttl

    def _get_cache_key(self, query: str, params: tuple = None) -> str:
        """Generate cache key"""
        import hashlib
        query_hash = hashlib.md5(query.encode()).hexdigest()
        if params:
            params_hash = hashlib.md5(str(params).encode()).hexdigest()
            return f"query_cache:{query_hash}:{params_hash}"
        return f"query_cache:{query_hash}"

    async def get(self, query: str, params: tuple = None) -> Optional[Any]:
        """
        Get cached query result.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            Cached result or None
        """
        try:
            key = self._get_cache_key(query, params)
            result = await self.redis.get(key)

            if result:
                logger.debug(f"Cache hit for query: {query[:50]}...")
                import json
                return json.loads(result)

            return None

        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    async def set(
        self,
        query: str,
        params: tuple,
        result: Any,
        ttl: int = None
    ) -> bool:
        """
        Cache query result.

        Args:
            query: SQL query
            params: Query parameters
            result: Query result to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        try:
            key = self._get_cache_key(query, params)
            import json

            await self.redis.setex(
                key,
                ttl or self.default_ttl,
                json.dumps(result)
            )

            logger.debug(f"Cached query: {query[:50]}...")
            return True

        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
            return False

    async def invalidate(self, query: str) -> bool:
        """
        Invalidate cached query results.

        Args:
            query: SQL query to invalidate

        Returns:
            True if successful
        """
        try:
            # Invalidate all cache entries for this query
            import hashlib
            query_hash = hashlib.md5(query.encode()).hexdigest()
            pattern = f"query_cache:{query_hash}:*"

            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
                logger.debug(f"Invalidated {len(keys)} cache entries")

            return True

        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")
            return False

    async def clear_all(self) -> bool:
        """Clear all cached query results"""
        try:
            pattern = "query_cache:*"
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries")

            return True

        except Exception as e:
            logger.warning(f"Cache clear failed: {e}")
            return False


# Connection pool optimization strategies

class ConnectionPoolOptimizer:
    """
    Optimizes database connection pool settings.
    """

    @staticmethod
    def calculate_optimal_pool_size(
        cpu_cores: int,
        target_utilization: float = 0.75
    ) -> Dict[str, int]:
        """
        Calculate optimal connection pool size.

        Formula: (CPU cores * target_utilization) + (effective_spindle_count)

        Args:
            cpu_cores: Number of CPU cores
            target_utilization: Target CPU utilization (0-1)

        Returns:
            Dictionary with pool settings
        """
        connections_per_core = max(2, int(cpu_cores * target_utilization))
        max_connections = connections_per_core * cpu_cores

        return {
            "min_size": max(5, int(max_connections * 0.2)),
            "max_size": min(100, max_connections)
        }

    @staticmethod
    def get_pool_health_metrics(pool: asyncpg.Pool) -> Dict[str, Any]:
        """
        Get pool health metrics.

        Args:
            pool: Database connection pool

        Returns:
            Dictionary with health metrics
        """
        return {
            "pool_size": pool._max,
            "available_connections": pool._queue.qsize(),
            "used_connections": pool._max - pool._queue.qsize(),
            "utilization_percent": (pool._max - pool._queue.qsize()) / pool._max * 100
        }

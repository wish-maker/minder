"""
Index management for Minder.
Implements index analysis and recommendations.
"""

import asyncpg
import logging
from typing import List, Dict, Any, Set

from .models import IndexRecommendation, TableStatistics

logger = logging.getLogger("minder.index_manager")


class IndexManager:
    """
    Index manager for Minder.
    Provides index analysis and recommendations.
    """

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize index manager.

        Args:
            pool: Database connection pool
        """
        self.pool = pool
        self.recommendations: List[IndexRecommendation] = []

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

        # Pattern 2: Tables with foreign keys without indexes
        await self._check_foreign_key_indexes(conn, schema_name, table_name)

    async def _check_foreign_key_indexes(
        self,
        conn: asyncpg.Connection,
        schema_name: str,
        table_name: str
    ):
        """Check for foreign key indexes"""
        fk_columns = await conn.fetch("""
            SELECT
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE
                tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = $1
                AND tc.table_name = $2
        """, schema_name, table_name)

        # Check if each FK column has an index
        for fk in fk_columns:
            column_name = fk["column_name"]
            indexes = await conn.fetch("""
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE schemaname = $1 AND tablename = $2
            """, schema_name, table_name)

            # Check if any index includes the FK column
            has_index = False
            for idx in indexes:
                columns = self._extract_index_columns(idx["indexdef"])
                if column_name in columns:
                    has_index = True
                    break

            if not has_index:
                self.recommendations.append(IndexRecommendation(
                    table=f"{schema_name}.{table_name}",
                    columns=[column_name],
                    index_type="btree",
                    estimated_impact="Medium",
                    reason=f"Foreign key column {column_name} lacks index"
                ))

    def _extract_index_columns(self, index_def: str) -> List[str]:
        """Extract column names from index definition"""
        try:
            # Parse column names from index definition
            match = re.search(r'\((.*?)\)', index_def)
            if match:
                columns_str = match.group(1)
                return [col.strip().split()[0] for col in columns_str.split(',')]
        except Exception:
            pass
        return []

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
        try:
            schema_name, table_name = table.split('.')

            async with self.pool.acquire() as conn:
                index_name = f"idx_{table_name}_{'_'.join(columns)}"
                columns_str = ', '.join(columns)

                await conn.execute(f"""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                    ON {schema_name}.{table_name} USING {index_type} ({columns_str})
                """)

                logger.info(f"Created index {index_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            return False

    async def drop_index(self, table: str, columns: List[str]) -> bool:
        """
        Drop an index from a table.

        Args:
            table: Table name
            columns: List of column names

        Returns:
            True if successful
        """
        try:
            schema_name, table_name = table.split('.')

            async with self.pool.acquire() as conn:
                index_name = f"idx_{table_name}_{'_'.join(columns)}"

                await conn.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}")

                logger.info(f"Dropped index {index_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to drop index: {e}")
            return False

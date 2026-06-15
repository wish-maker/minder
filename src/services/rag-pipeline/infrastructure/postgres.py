"""
PostgreSQL Client Manager

Manages PostgreSQL connection pool for RAG pipeline data persistence.
Provides connection lifecycle and schema initialization.

This is an infrastructure component for PostgreSQL integration.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Optional dependency handling
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None
    logging.warning("asyncpg not available. Install with: pip install asyncpg")


class PostgreSQLClient:
    """
    PostgreSQL connection pool manager

    Manages async connection pool for database operations.
    Handles connection lifecycle and schema initialization.

    Features:
    - Async connection pool
    - Schema initialization
    - Connection testing
    - Graceful degradation

    Attributes:
        host: PostgreSQL host
        port: PostgreSQL port
        database: Database name
        user: Database user
        password: Database password
        pool: Connection pool instance

    Example:
        >>> client = PostgreSQLClient(
        ...     host="localhost",
        ...     database="minder_rag",
        ...     user="minder",
        ...     password="secret"
        ... )
        >>> await client.initialize()
        >>> pool = client.get_pool()
    """

    def __init__(
        self,
        host: str = "postgres",
        port: int = 5432,
        database: str = "minder",
        user: str = "minder",
        password: str = "minder",
        min_size: int = 5,
        max_size: int = 20
    ):
        """
        Initialize PostgreSQL client

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
            min_size: Minimum pool size
            max_size: Maximum pool size

        Raises:
            ValueError: If parameters invalid
        """
        if not host:
            raise ValueError("host cannot be empty")

        if not database:
            raise ValueError("database cannot be empty")

        if not user:
            raise ValueError("user cannot be empty")

        if port <= 0 or port > 65535:
            raise ValueError(f"port must be in (0, 65535], got {port}")

        if min_size <= 0:
            raise ValueError(f"min_size must be positive, got {min_size}")

        if max_size <= 0:
            raise ValueError(f"max_size must be positive, got {max_size}")

        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_size = min_size
        self.max_size = max_size
        self.pool: Optional[Any] = None
        self._initialized = False

        logger.info(f"✅ PostgreSQLClient created: {host}:{port}/{database}")

    async def initialize(self) -> None:
        """
        Initialize connection pool

        Creates connection pool and tests connectivity.

        Raises:
            RuntimeError: If asyncpg not available
            ConnectionError: If connection fails
        """
        if not ASYNCPG_AVAILABLE:
            raise RuntimeError("asyncpg package not installed")

        if self._initialized:
            logger.debug("PostgreSQLClient already initialized")
            return

        try:
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=self.min_size,
                max_size=self.max_size,
            )

            # Test connection
            async with self.pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                logger.info(f"✅ PostgreSQL connected: {version[:50]}...")

            self._initialized = True

        except Exception as e:
            logger.error(f"❌ Failed to initialize PostgreSQL: {e}")
            raise

    async def initialize_schema(self, schema_file: str = None) -> bool:
        """
        Initialize database schema

        Args:
            schema_file: Optional path to SQL schema file

        Returns:
            True if schema initialized successfully

        Raises:
            RuntimeError: If pool not initialized
        """
        if not self._initialized or self.pool is None:
            raise RuntimeError("PostgreSQLClient not initialized")

        try:
            if schema_file:
                # Load schema from file
                with open(schema_file, 'r') as f:
                    schema_sql = f.read()
            else:
                # Use default schema
                schema_sql = """
                CREATE TABLE IF NOT EXISTS knowledge_bases (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    embedding_model VARCHAR(100) NOT NULL DEFAULT 'nomic-embed-text',
                    llm_model VARCHAR(100) NOT NULL DEFAULT 'llama3',
                    chunk_size INTEGER NOT NULL DEFAULT 512,
                    chunk_overlap INTEGER NOT NULL DEFAULT 50,
                    parent_child_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                    document_count INTEGER NOT NULL DEFAULT 0,
                    vector_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    conversation_id VARCHAR(255) NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}'::jsonb
                );
                """

            async with self.pool.acquire() as conn:
                # Split and execute statements
                statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
                for statement in statements:
                    await conn.execute(statement)

            logger.info("✅ Database schema initialized")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize schema: {e}")
            raise

    def get_pool(self) -> Any:
        """
        Get connection pool

        Returns:
            asyncpg connection pool

        Raises:
            RuntimeError: If pool not initialized
        """
        if not self._initialized or self.pool is None:
            raise RuntimeError("PostgreSQLClient not initialized")

        return self.pool

    async def close(self) -> None:
        """
        Close connection pool

        Gracefully closes all connections in the pool.
        """
        if self.pool and not self.pool._closed:
            await self.pool.close()
            self._initialized = False
            logger.info("✅ PostgreSQL connection pool closed")

    async def health_check(self) -> bool:
        """
        Check database connectivity

        Returns:
            True if database is healthy
        """
        if not self._initialized or self.pool is None:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True

        except Exception as e:
            logger.warning(f"⚠️ PostgreSQL health check failed: {e}")
            return False

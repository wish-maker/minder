"""
Shared Database Pool Manager for Minder Platform
Provides centralized connection pool management for all plugins
"""

import asyncpg
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class DatabasePoolManager:
    """
    Centralized database connection pool manager

    Eliminates code duplication across plugins and provides:
    - Single point of configuration
    - Connection pooling optimization
    - Consistent error handling
    - Automatic cleanup
    """

    _instance: Optional['DatabasePoolManager'] = None
    _pools: Dict[str, asyncpg.Pool] = {}

    def __new__(cls):
        """Singleton pattern to ensure only one instance exists"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def create_pool(
        self,
        config: Dict,
        pool_name: str = "default",
        min_size: int = 2,
        max_size: int = 10,
        command_timeout: int = 60
    ) -> asyncpg.Pool:
        """
        Create or get existing database connection pool

        Args:
            config: Database configuration dict with keys:
                - host: Database host
                - port: Database port (default: 5432)
                - database: Database name
                - user: Database user
                - password: Database password
            pool_name: Unique name for this pool (allows multiple pools)
            min_size: Minimum number of connections in pool
            max_size: Maximum number of connections in pool
            command_timeout: Command timeout in seconds

        Returns:
            asyncpg.Pool: Database connection pool

        Raises:
            ValueError: If configuration is invalid
            asyncpg.PostgresError: If connection fails
        """
        # Return existing pool if already created
        if pool_name in self._pools:
            logger.debug(f"Using existing pool: {pool_name}")
            return self._pools[pool_name]

        # Validate configuration
        required_keys = ["host", "database", "user", "password"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required config key: {key}")

        # Extract configuration
        host = config.get("host", "localhost")
        port = config.get("port", 5432)
        database = config.get("database")
        user = config.get("user")
        password = config.get("password")

        # Create connection pool
        try:
            logger.info(f"Creating database pool: {pool_name} -> {host}:{port}/{database}")

            pool = await asyncpg.create_pool(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                min_size=min_size,
                max_size=max_size,
                command_timeout=command_timeout,
                # Connection settings
                server_settings={
                    "application_name": "minder_platform",
                    "timezone": "UTC",
                }
            )

            self._pools[pool_name] = pool

            logger.info(
                f"✅ Database pool created: {pool_name} "
                f"(min={min_size}, max={max_size})"
            )

            return pool

        except Exception as e:
            logger.error(f"❌ Failed to create pool {pool_name}: {e}")
            raise

    async def get_pool(self, pool_name: str = "default") -> Optional[asyncpg.Pool]:
        """
        Get existing pool by name

        Args:
            pool_name: Name of pool to retrieve

        Returns:
            asyncpg.Pool if exists, None otherwise
        """
        return self._pools.get(pool_name)

    async def close_pool(self, pool_name: str = "default") -> bool:
        """
        Close a specific pool

        Args:
            pool_name: Name of pool to close

        Returns:
            True if pool was closed, False if pool didn't exist
        """
        if pool_name in self._pools:
            pool = self._pools[pool_name]
            await pool.close()
            del self._pools[pool_name]
            logger.info(f"Closed database pool: {pool_name}")
            return True
        return False

    async def close_all_pools(self) -> int:
        """
        Close all connection pools

        Returns:
            Number of pools closed
        """
        count = 0
        for pool_name in list(self._pools.keys()):
            await self.close_pool(pool_name)
            count += 1
        logger.info(f"Closed {count} database pool(s)")
        return count

    def list_pools(self) -> Dict[str, Dict]:
        """
        List all active pools with their stats

        Returns:
            Dict mapping pool names to their statistics
        """
        stats = {}
        for pool_name, pool in self._pools.items():
            stats[pool_name] = {
                "min_size": pool._minsize,
                "max_size": pool._maxsize,
                "size": pool.size,
                "idle": pool._idle.size,
            }
        return stats

    def get_pool_status(self, pool_name: str = "default") -> Optional[Dict]:
        """
        Get status of a specific pool

        Args:
            pool_name: Name of pool

        Returns:
            Dict with pool stats or None if pool doesn't exist
        """
        if pool_name not in self._pools:
            return None

        pool = self._pools[pool_name]
        return {
            "name": pool_name,
            "min_size": pool._minsize,
            "max_size": pool._maxsize,
            "size": pool.size,
            "idle": pool._idle.size,
            "in_use": pool.size - pool._idle.size,
        }


# Global instance
db_pool_manager = DatabasePoolManager()


async def create_plugin_pool(
    plugin_name: str,
    db_config: Dict,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: int = 60
) -> asyncpg.Pool:
    """
    Convenience function to create pool for a plugin

    Args:
        plugin_name: Name of plugin (used as pool name)
        db_config: Database configuration
        min_size: Minimum pool size
        max_size: Maximum pool size
        command_timeout: Command timeout

    Returns:
        asyncpg.Pool: Database connection pool
    """
    pool_name = f"plugin_{plugin_name}"
    return await db_pool_manager.create_pool(
        config=db_config,
        pool_name=pool_name,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout
    )


async def get_plugin_pool(plugin_name: str) -> Optional[asyncpg.Pool]:
    """
    Convenience function to get plugin's pool

    Args:
        plugin_name: Name of plugin

    Returns:
        asyncpg.Pool if exists, None otherwise
    """
    pool_name = f"plugin_{plugin_name}"
    return await db_pool_manager.get_pool(pool_name)


# ============================================================================
# Usage Examples
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def example():
        """Example usage"""

        # Example 1: Create pool for plugin
        config = {
            "host": "localhost",
            "port": 5432,
            "database": "minder",
            "user": "minder",
            "password": "password"
        }

        pool = await create_plugin_pool("crypto", config)
        print(f"Pool created: {pool}")

        # Example 2: Use pool
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT version()")
            print(f"PostgreSQL version: {result}")

        # Example 3: Check pool status
        status = db_pool_manager.get_pool_status("plugin_crypto")
        print(f"Pool status: {status}")

        # Example 4: Cleanup
        await db_pool_manager.close_all_pools()

    asyncio.run(example())

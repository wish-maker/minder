"""
Plugin registry for Minder.
Handles plugin registration, storage, and retrieval from database.
"""

import asyncpg
import json
import logging
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger("minder.plugin_registry")


class PluginRegistry:
    """
    Plugin registry for Minder.
    Handles plugin registration, storage, and retrieval.
    """

    def __init__(
        self,
        db_pool: Optional[asyncpg.Pool] = None,
        redis_pool: Optional[Any] = None,
    ):
        """
        Initialize plugin registry.

        Args:
            db_pool: Database connection pool
            redis_pool: Redis connection pool
        """
        self.db_pool = db_pool
        self.redis_pool = redis_pool

    async def register_plugin(
        self,
        plugin_id: str,
        manifest_url: Optional[str] = None,
        manifest_data: Optional[Dict[str, Any]] = None,
        status: str = "installed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Register a plugin in the registry.

        Args:
            plugin_id: Plugin ID
            manifest_url: URL to manifest (optional)
            manifest_data: Manifest data (optional)
            status: Plugin status (installed, active, disabled)
            metadata: Additional metadata (optional)

        Returns:
            Registration result
        """
        try:
            if manifest_data is None:
                manifest_data = {}

            # Check if plugin already exists
            existing = await self._get_plugin_from_db(plugin_id)

            if existing:
                # Update existing plugin
                await self._update_plugin_in_db(
                    plugin_id=plugin_id,
                    manifest_url=manifest_url,
                    manifest_data=manifest_data,
                    status=status,
                    metadata=metadata,
                )

                logger.info(f"Updated plugin in registry: {plugin_id}")

                return {
                    "plugin_id": plugin_id,
                    "status": "updated",
                    "message": f"Plugin {plugin_id} updated successfully",
                    "registered_at": existing.get("registered_at", ""),
                    "updated_at": datetime.now().isoformat(),
                }
            else:
                # Register new plugin
                plugin_hash = self._generate_plugin_hash(plugin_id, manifest_url)

                await self._insert_plugin_in_db(
                    plugin_id=plugin_id,
                    plugin_hash=plugin_hash,
                    manifest_url=manifest_url,
                    manifest_data=manifest_data,
                    status=status,
                    metadata=metadata,
                )

                logger.info(f"Registered plugin in registry: {plugin_id}")

                return {
                    "plugin_id": plugin_id,
                    "status": "registered",
                    "message": f"Plugin {plugin_id} registered successfully",
                    "registered_at": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Error registering plugin {plugin_id}: {e}")

            return {
                "plugin_id": plugin_id,
                "status": "registration_failed",
                "error": str(e),
            }

    async def unregister_plugin(self, plugin_id: str) -> bool:
        """
        Unregister a plugin from the registry.

        Args:
            plugin_id: Plugin ID

        Returns:
            True if successful
        """
        try:
            # Delete from database
            await self._delete_plugin_from_db(plugin_id)

            # Clear from Redis cache
            if self.redis_pool:
                await self.redis_pool.delete(f"plugin:{plugin_id}")

            logger.info(f"Unregistered plugin: {plugin_id}")

            return True

        except Exception as e:
            logger.error(f"Error unregistering plugin {plugin_id}: {e}")
            return False

    async def get_plugin_info(
        self, plugin_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get plugin information.

        Args:
            plugin_id: Plugin ID

        Returns:
            Plugin information or None
        """
        try:
            # Try Redis cache first
            if self.redis_pool:
                cached = await self.redis_pool.get(f"plugin:{plugin_id}")
                if cached:
                    return json.loads(cached)

            # Get from database
            plugin = await self._get_plugin_from_db(plugin_id)

            return plugin

        except Exception as e:
            logger.error(f"Error getting plugin info {plugin_id}: {e}")
            return None

    async def update_plugin_status(
        self, plugin_id: str, status: str
    ) -> bool:
        """
        Update plugin status.

        Args:
            plugin_id: Plugin ID
            status: Plugin status (installed, active, disabled, removed)

        Returns:
            True if successful
        """
        try:
            # Update in database
            await self._update_plugin_status_in_db(plugin_id, status)

            # Update in Redis cache
            if self.redis_pool:
                # Invalidate cache
                await self.redis_pool.delete(f"plugin:{plugin_id}")

            logger.info(f"Updated plugin status: {plugin_id} -> {status}")

            return True

        except Exception as e:
            logger.error(f"Error updating plugin status {plugin_id}: {e}")
            return False

    async def list_plugins(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List plugins.

        Args:
            status: Filter by status (installed, active, disabled, removed)
            limit: Maximum number of plugins to return

        Returns:
            List of plugins
        """
        try:
            # Get from database
            plugins = await self._list_plugins_from_db(status, limit)

            return plugins

        except Exception as e:
            logger.error(f"Error listing plugins: {e}")
            return []

    async def _get_plugin_from_db(
        self, plugin_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get plugin from database.

        Args:
            plugin_id: Plugin ID

        Returns:
            Plugin data or None
        """
        if not self.db_pool:
            return None

        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT id, name, version, author, description,
                           manifest_url, manifest_data, status, metadata,
                           plugin_hash, registered_at, updated_at
                    FROM plugins
                    WHERE id = $1
                """, plugin_id)

                if row:
                    return {
                        "id": row["id"],
                        "name": row["name"],
                        "version": row["version"],
                        "author": row["author"],
                        "description": row["description"],
                        "manifest_url": row["manifest_url"],
                        "manifest_data": row["manifest_data"],
                        "status": row["status"],
                        "metadata": row["metadata"],
                        "plugin_hash": row["plugin_hash"],
                        "registered_at": row["registered_at"].isoformat() if row["registered_at"] else "",
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
                    }

                return None

        except Exception as e:
            logger.error(f"Error getting plugin from db {plugin_id}: {e}")
            return None

    async def _insert_plugin_in_db(
        self,
        plugin_id: str,
        plugin_hash: str,
        manifest_url: Optional[str],
        manifest_data: Dict[str, Any],
        status: str,
        metadata: Optional[Dict[str, Any]],
    ):
        """Insert plugin into database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO plugins (id, name, version, author, description,
                                   manifest_url, manifest_data, status, metadata,
                                   plugin_hash, registered_at, updated_at)
                VALUES ($1, $2, $3, $4, $5,
                        $6, $7, $8, $9, $10,
                        $11, $12, $13)
            """,
                plugin_id,
                manifest_data.get("name", ""),
                manifest_data.get("version", ""),
                manifest_data.get("author", ""),
                manifest_data.get("description", ""),
                manifest_url,
                json.dumps(manifest_data),
                status,
                json.dumps(metadata or {}),
                plugin_hash,
                datetime.now(),
                datetime.now(),
            )

    async def _update_plugin_in_db(
        self,
        plugin_id: str,
        manifest_url: Optional[str],
        manifest_data: Dict[str, Any],
        status: str,
        metadata: Optional[Dict[str, Any]],
    ):
        """Update plugin in database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE plugins
                SET manifest_url = COALESCE($1, manifest_url),
                    manifest_data = COALESCE($2, manifest_data),
                    status = $3,
                    metadata = COALESCE($4, metadata),
                    updated_at = $5
                WHERE id = $6
            """,
                manifest_url,
                json.dumps(manifest_data),
                status,
                json.dumps(metadata or {}),
                datetime.now(),
                plugin_id,
            )

    async def _update_plugin_status_in_db(
        self, plugin_id: str, status: str
    ):
        """Update plugin status in database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE plugins
                SET status = $1,
                    updated_at = $2
                WHERE id = $3
            """, status, datetime.now(), plugin_id)

    async def _delete_plugin_from_db(self, plugin_id: str):
        """Delete plugin from database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("DELETE FROM plugins WHERE id = $1", plugin_id)

    async def _list_plugins_from_db(
        self, status: Optional[str], limit: int
    ) -> List[Dict[str, Any]]:
        """List plugins from database"""
        async with self.db_pool.acquire() as conn:
            if status:
                rows = await conn.fetch("""
                    SELECT id, name, version, author, description,
                           manifest_url, manifest_data, status, metadata,
                           registered_at, updated_at
                    FROM plugins
                    WHERE status = $1
                    ORDER BY registered_at DESC
                    LIMIT $2
                """, status, limit)
            else:
                rows = await conn.fetch("""
                    SELECT id, name, version, author, description,
                           manifest_url, manifest_data, status, metadata,
                           registered_at, updated_at
                    FROM plugins
                    ORDER BY registered_at DESC
                    LIMIT $1
                """, limit)

            plugins = []
            for row in rows:
                plugins.append({
                    "id": row["id"],
                    "name": row["name"],
                    "version": row["version"],
                    "author": row["author"],
                    "description": row["description"],
                    "manifest_url": row["manifest_url"],
                    "manifest_data": row["manifest_data"],
                    "status": row["status"],
                    "metadata": row["metadata"],
                    "registered_at": row["registered_at"].isoformat() if row["registered_at"] else "",
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
                })

            return plugins

    def _generate_plugin_hash(self, plugin_id: str, manifest_url: Optional[str]) -> str:
        """Generate plugin hash for versioning"""
        hash_input = f"{plugin_id}:{manifest_url or ''}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    async def _create_plugins_table(self):
        """Create plugins table if not exists"""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS plugins (
                    id VARCHAR(255) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    version VARCHAR(50) NOT NULL,
                    author VARCHAR(255) NOT NULL,
                    description TEXT,
                    manifest_url TEXT,
                    manifest_data JSONB,
                    status VARCHAR(50) NOT NULL,
                    metadata JSONB,
                    plugin_hash VARCHAR(64) NOT NULL,
                    registered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """)

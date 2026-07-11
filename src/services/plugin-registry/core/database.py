"""
Core Database Module

Owns the PostgreSQL connection pool and all plugin persistence: table creation,
loading the plugin cache from the database, and upserting plugin rows. The pool is
created lazily and lives here (it is the only reassigned piece of shared state);
the in-memory caches live in ``core.state``.
"""

import asyncpg
from core.state import logger, plugins_db
from models import PluginInfo

from config import settings

# Global connection pool (lazily created by get_postgres_connection)
postgres_pool = None


async def get_postgres_connection():
    """Get PostgreSQL connection pool (creating it on first use)."""
    global postgres_pool
    if postgres_pool is None:
        postgres_pool = await asyncpg.create_pool(
            host=(
                settings.POSTGRES_HOST
                if hasattr(settings, "POSTGRES_HOST")
                else "minder-postgres"
            ),
            port=settings.POSTGRES_PORT if hasattr(settings, "POSTGRES_PORT") else 5432,
            user=(
                settings.POSTGRES_USER
                if hasattr(settings, "POSTGRES_USER")
                else "minder"
            ),
            password=(
                settings.POSTGRES_PASSWORD
                if hasattr(settings, "POSTGRES_PASSWORD")
                else "dev_password_change_me"
            ),
            database=(
                settings.POSTGRES_DB if hasattr(settings, "POSTGRES_DB") else "minder"
            ),
            min_size=2,
            max_size=10,
        )
    return postgres_pool


async def create_plugins_table_if_not_exists():
    """Create plugins table if it doesn't exist"""
    try:
        pool = await get_postgres_connection()

        create_table_query = """
            CREATE TABLE IF NOT EXISTS plugins (
                name VARCHAR(255) PRIMARY KEY,
                version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
                description TEXT,
                author VARCHAR(255),
                status VARCHAR(50) NOT NULL DEFAULT 'registered',
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                dependencies TEXT,
                capabilities JSONB,
                data_sources JSONB,
                databases JSONB,
                health_status VARCHAR(50) DEFAULT 'unknown',
                last_health_check TIMESTAMP WITH TIME ZONE,
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """

        async with pool.acquire() as conn:
            await conn.execute(create_table_query)

        logger.info("✅ Plugins table verified/created in PostgreSQL")

    except Exception as e:
        logger.error(f"❌ Failed to create plugins table: {e}")
        raise


async def load_plugins_from_database():
    """Load plugins from PostgreSQL database into memory cache"""
    try:
        conn = await get_postgres_connection()

        query = """
            SELECT name, version, description, author, status, enabled,
                   capabilities, data_sources, databases, health_status,
                   last_health_check, registered_at
            FROM plugins
            ORDER BY name
        """

        rows = await conn.fetch(query)

        for row in rows:
            plugin_info = PluginInfo(
                name=row["name"],
                version=row["version"],
                description=row["description"],
                author=row["author"],
                status=row["status"],
                enabled=row["enabled"],
                capabilities=row["capabilities"] or [],
                data_sources=row["data_sources"] or [],
                databases=row["databases"] or [],
                registered_at=(
                    row["registered_at"].isoformat() if row["registered_at"] else None
                ),
                health_status=row["health_status"] or "unknown",
                last_health_check=(
                    row["last_health_check"].isoformat()
                    if row["last_health_check"]
                    else None
                ),
            )
            plugins_db[row["name"]] = plugin_info

        logger.info(f"✅ Loaded {len(plugins_db)} plugins from database")

    except Exception as e:
        logger.error(f"❌ Failed to load plugins from database: {e}")
        # Don't raise - allow startup to continue with empty plugins_db


async def update_plugin_in_database(plugin_name: str, **updates):
    """Update plugin in database (INSERT if not exists, UPDATE if exists)"""
    pool = await get_postgres_connection()

    try:
        # Only allow updating columns that exist in the plugins table
        allowed_columns = {
            "status",
            "enabled",
            "health_status",
            "last_health_check",
            "version",
            "description",
            "author",
            "dependencies",
            "capabilities",
            "data_sources",
            "databases",
        }
        valid_updates = {k: v for k, v in updates.items() if k in allowed_columns}

        if not valid_updates:
            return

        # Build parameter lists in correct order
        insert_columns = ["name"] + list(valid_updates.keys())
        insert_values = [f"${i+1}" for i in range(len(insert_columns))]

        # Build UPDATE clause for ON CONFLICT
        update_clauses = [f"{col} = EXCLUDED.{col}" for col in valid_updates.keys()]

        # Build values list (plugin_name first, then updates)
        values = [plugin_name] + list(valid_updates.values())

        # nosec B608 - SQL injection protected by allowed_columns whitelist
        # Use INSERT ... ON CONFLICT for UPSERT
        query = f"""
            INSERT INTO plugins ({', '.join(insert_columns)})
            VALUES ({', '.join(insert_values)})
            ON CONFLICT (name) DO UPDATE
              SET {', '.join(update_clauses)}
        """

        async with pool.acquire() as conn:
            await conn.execute(query, *values)
        logger.debug(
            f"Upserted plugin {plugin_name} in database: {list(valid_updates.keys())}"
        )

    except Exception as e:
        logger.error(f"Failed to update plugin {plugin_name} in database: {e}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")

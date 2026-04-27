# services/plugin-state-manager/core/database.py
"""
Database connection pool management
"""

import asyncpg
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


def get_db_config() -> dict:
    """Get database configuration from environment"""
    return {
        "host": os.getenv("DB_HOST", "postgres"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "minder"),
        "password": os.getenv("DB_PASSWORD", "minder_pass"),
        "database": os.getenv("DB_NAME", "minder_marketplace"),
    }


async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool"""
    global _pool

    if _pool is None:
        config = get_db_config()
        logger.info(f"Creating database connection pool for {config['database']}")

        _pool = await asyncpg.create_pool(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            min_size=2,
            max_size=10,
        )

        logger.info("Database connection pool created successfully")

    return _pool


async def close_db_pool():
    """Close database connection pool"""
    global _pool

    if _pool:
        logger.info("Closing database connection pool")
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


async def initialize_database():
    """Initialize database tables and schema"""
    pool = await get_db_pool()

    # Create plugin_states table
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS plugin_states (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plugin_name VARCHAR(255) UNIQUE NOT NULL,
            state VARCHAR(50) NOT NULL,
            license_tier VARCHAR(50) DEFAULT 'community',
            license_key VARCHAR(255),
            config JSONB DEFAULT '{}'::jsonb,
            enabled_at TIMESTAMP,
            disabled_at TIMESTAMP,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT valid_state CHECK (
                state IN ('installed', 'enabled', 'disabled', 'error',
                          'INSTALLED', 'ENABLED', 'DISABLED', 'ERROR')
            )
        )
    """)

    # Create default_plugins table
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS default_plugins (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plugin_name VARCHAR(255) UNIQUE NOT NULL,
            priority INTEGER NOT NULL,
            auto_enable BOOLEAN NOT NULL,
            required BOOLEAN NOT NULL,
            min_tier VARCHAR(50) NOT NULL,
            description TEXT,
            version VARCHAR(50),
            config JSONB DEFAULT '{}'::jsonb
        )
    """)

    # Create plugin_dependencies table
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS plugin_dependencies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plugin_name VARCHAR(255) NOT NULL,
            depends_on VARCHAR(255) NOT NULL,
            required BOOLEAN NOT NULL,
            UNIQUE(plugin_name, depends_on)
        )
    """)

    # Create user_subscriptions table
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) UNIQUE NOT NULL,
            tier VARCHAR(50) NOT NULL,
            license_key VARCHAR(255),
            valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            valid_until TIMESTAMP,
            auto_renew BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    logger.info("Database tables initialized successfully")

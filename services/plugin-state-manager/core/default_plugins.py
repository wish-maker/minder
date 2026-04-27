# services/plugin-state-manager/core/default_plugins.py
"""
Default plugins bootstrap logic
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import asyncpg
import yaml
from models.plugin_state import LicenseTier, PluginState

logger = logging.getLogger(__name__)


DEFAULT_PLUGINS_CONFIG = os.getenv(
    "DEFAULT_PLUGINS_CONFIG",
    "/config/default_plugins.yml"
)


async def load_default_plugins_config() -> Dict:
    """Load default plugins configuration from YAML file"""
    config_path = Path(DEFAULT_PLUGINS_CONFIG)

    if not config_path.exists():
        logger.warning(f"Default plugins config not found at {DEFAULT_PLUGINS_CONFIG}")
        return {"default_plugins": [], "dependencies": []}

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


async def bootstrap_default_plugins():
    """
    Bootstrap default plugins into the system

    1. Load configuration
    2. Insert default plugins into database
    3. Insert dependencies
    4. Create plugin states
    5. Enable plugins in dependency order
    """
    db = await get_db_pool()
    config = await load_default_plugins_config()

    if not config:
        logger.info("No default plugins configuration found, skipping bootstrap")
        return

    async with db.acquire() as conn:
        # Clear existing default plugins (for clean bootstrap)
        await conn.execute("DELETE FROM plugin_dependencies")
        await conn.execute("DELETE FROM default_plugins")

        # Insert default plugins
        for plugin_config in config.get("default_plugins", []):
            try:
                await conn.execute(
                    """
                    INSERT INTO default_plugins (
                        plugin_name, priority, auto_enable, required,
                        min_tier, description, version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (plugin_name) DO UPDATE SET
                        priority = EXCLUDED.priority,
                        auto_enable = EXCLUDED.auto_enable,
                        required = EXCLUDED.required,
                        min_tier = EXCLUDED.min_tier,
                        description = EXCLUDED.description,
                        version = EXCLUDED.version
                    """,
                    plugin_config["name"],
                    plugin_config.get("priority", 0),
                    plugin_config.get("auto_enable", True),
                    plugin_config.get("required", False),
                    plugin_config.get("min_tier", "community"),
                    plugin_config.get("description"),
                    plugin_config.get("version")
                )
                logger.info(f"✅ Registered default plugin: {plugin_config['name']}")
            except Exception as e:
                logger.error(f"❌ Failed to register default plugin {plugin_config.get('name')}: {e}")

        # Insert dependencies
        for dep_config in config.get("dependencies", []):
            try:
                # Handle both string and list for depends_on
                depends_on_list = dep_config["depends_on"]
                if isinstance(depends_on_list, str):
                    depends_on_list = [depends_on_list]

                # Create a row for each dependency
                for dep in depends_on_list:
                    await conn.execute(
                        """
                        INSERT INTO plugin_dependencies (plugin_name, depends_on, required)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (plugin_name, depends_on) DO UPDATE SET
                            required = EXCLUDED.required
                        """,
                        dep_config["plugin"],
                        dep,
                        dep_config.get("required", False)
                    )
                    logger.info(f"✅ Registered dependency: {dep_config['plugin']} → {dep}")
            except Exception as e:
                logger.error(f"❌ Failed to register dependency: {e}")

        # Create plugin states for default plugins
        default_plugin_names = [p["name"] for p in config.get("default_plugins", [])]

        for plugin_name in default_plugin_names:
            try:
                existing = await conn.fetchrow(
                    "SELECT id FROM plugin_states WHERE plugin_name = $1",
                    plugin_name
                )

                if not existing:
                    plugin_config = next(
                        (p for p in config.get("default_plugins", []) if p["name"] == plugin_name),
                        {}
                    )

                    initial_state = PluginState.ENABLED if plugin_config.get("auto_enable", True) else PluginState.INSTALLED

                    await conn.execute(
                        """
                        INSERT INTO plugin_states (plugin_name, state, license_tier)
                        VALUES ($1, $2, $3)
                        """,
                        plugin_name,
                        initial_state.value,
                        plugin_config.get("min_tier", "community")
                    )
                    logger.info(f"✅ Created state for default plugin: {plugin_name} ({initial_state.value})")
            except Exception as e:
                logger.error(f"❌ Failed to create state for {plugin_name}: {e}")

        # Enable plugins in dependency order
        if config.get("default_plugins"):
            await enable_plugins_in_dependency_order(conn, config)

    logger.info("✅ Default plugins bootstrap completed")


async def enable_plugins_in_dependency_order(
    conn: asyncpg.Connection,
    config: Dict
):
    """Enable plugins in dependency order (topological sort)"""
    # Build dependency graph
    plugins = {}
    for plugin_config in config.get("default_plugins", []):
        name = plugin_config["name"]
        plugins[name] = {
            "auto_enable": plugin_config.get("auto_enable", True),
            "deps": [],
            "enabled": False
        }

    # Add dependencies
    for dep_config in config.get("dependencies", []):
        plugin_name = dep_config["plugin"]
        depends_on = dep_config["depends_on"]
        if plugin_name in plugins:
            plugins[plugin_name]["deps"].append(depends_on)

    # Topological sort
    result = []
    visited = set()

    def visit(name: str, stack: set):
        if name in stack:
            logger.warning(f"Circular dependency detected: {' -> '.join(stack)} → {name}")
            return

        if name in visited or name not in plugins:
            return

        stack.add(name)

        # Visit dependencies first
        for dep in plugins[name]["deps"]:
            visit(dep, stack)

        stack.remove(name)
        visited.add(name)
        result.append(name)

    # Visit all plugins
    for name in plugins:
        visit(name, set())

    # Enable plugins in order
    for plugin_name in result:
        if plugins[plugin_name]["auto_enable"]:
            try:
                from core.state import enable_plugin

                await enable_plugin(conn, plugin_name, reason="system_bootstrap")
                plugins[plugin_name]["enabled"] = True
                logger.info(f"✅ Enabled default plugin: {plugin_name}")
            except Exception as e:
                logger.error(f"❌ Failed to enable default plugin {plugin_name}: {e}")


# Helper function to get DB pool (imported from core.database)
async def get_db_pool():
    from core.database import get_db_pool
    return await get_db_pool()

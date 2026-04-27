# services/plugin-state-manager/core/state.py
"""
Plugin state management core logic
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import asyncpg

from models.plugin_state import PluginState, LicenseTier

logger = logging.getLogger(__name__)


def _record_to_dict(record) -> Dict:
    """Convert asyncpg Record to dict, handling JSONB and UUID fields"""
    if not record:
        return None

    result = {}
    for key, value in record.items():
        # Handle UUID fields - convert to string
        if key == 'id' and hasattr(value, '__str__'):
            result[key] = str(value)
        # Handle JSONB fields - asyncpg returns them as strings
        elif key in ('config', 'metadata'):
            if isinstance(value, str):
                result[key] = json.loads(value)
            else:
                result[key] = value or {}
        else:
            result[key] = value
    return result


class StateTransitionError(Exception):
    """State transition error"""
    pass


class RequiredPluginError(Exception):
    """Required plugin error"""
    pass


async def get_plugin_state(conn: asyncpg.Connection, plugin_name: str) -> Optional[Dict]:
    """Get plugin state from database"""
    row = await conn.fetchrow(
        "SELECT * FROM plugin_states WHERE plugin_name = $1",
        plugin_name
    )
    return _record_to_dict(row)


async def create_plugin_state(
    conn: asyncpg.Connection,
    plugin_name: str,
    initial_state: PluginState = PluginState.INSTALLED,
    license_tier: LicenseTier = LicenseTier.COMMUNITY
) -> Dict:
    """Create new plugin state"""
    row = await conn.fetchrow(
        """
        INSERT INTO plugin_states (plugin_name, state, license_tier)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        plugin_name,
        initial_state.value,
        license_tier.value
    )
    return dict(row)


async def update_plugin_state(
    conn: asyncpg.Connection,
    plugin_name: str,
    state: PluginState,
    metadata: Optional[Dict] = None
) -> Dict:
    """Update plugin state"""
    now = datetime.now()

    if state == PluginState.ENABLED:
        query = """
            UPDATE plugin_states
            SET state = $1, enabled_at = $2, disabled_at = NULL, updated_at = $2
            WHERE plugin_name = $3
            RETURNING *
        """
    elif state == PluginState.DISABLED:
        query = """
            UPDATE plugin_states
            SET state = $1, disabled_at = $2, enabled_at = NULL, updated_at = $2
            WHERE plugin_name = $3
            RETURNING *
        """
    else:
        query = """
            UPDATE plugin_states
            SET state = $1, updated_at = $2
            WHERE plugin_name = $3
            RETURNING *
        """

    row = await conn.fetchrow(query, state.value, now, plugin_name)

    if metadata:
        await conn.execute(
            "UPDATE plugin_states SET metadata = $1 WHERE plugin_name = $2",
            metadata, plugin_name
        )

    return dict(row)


async def enable_plugin(
    conn: asyncpg.Connection,
    plugin_name: str,
    reason: Optional[str] = None
) -> Dict:
    """
    Enable a plugin

    Args:
        conn: Database connection
        plugin_name: Plugin name
        reason: Optional reason for enabling

    Returns:
        Updated plugin state

    Raises:
        StateTransitionError: If state transition is invalid
        RequiredPluginError: If plugin is required and cannot be disabled
    """
    # Check if plugin is required
    default_plugin = await conn.fetchrow(
        "SELECT required FROM default_plugins WHERE plugin_name = $1",
        plugin_name
    )

    if default_plugin and default_plugin["required"]:
        # Check if there's a specific reason to force enable
        if reason != "system_bootstrap":
            logger.warning(f"Plugin {plugin_name} is required and should always be enabled")

    # Get current state
    current = await get_plugin_state(conn, plugin_name)

    if not current:
        # Create new state as enabled
        logger.info(f"Creating new enabled state for plugin: {plugin_name}")
        return await create_plugin_state(conn, plugin_name, PluginState.ENABLED)

    # State transition: installed/disabled/error → enabled
    if current["state"] in ["installed", "disabled", "error"]:
        return await update_plugin_state(conn, plugin_name, PluginState.ENABLED)
    elif current["state"] == "enabled":
        logger.info(f"Plugin {plugin_name} is already enabled")
        return current
    else:
        raise StateTransitionError(
            f"Cannot enable plugin {plugin_name} from state {current['state']}"
        )


async def disable_plugin(
    conn: asyncpg.Connection,
    plugin_name: str,
    force: bool = False,
    reason: Optional[str] = None
) -> Dict:
    """
    Disable a plugin

    Args:
        conn: Database connection
        plugin_name: Plugin name
        force: Force disable even if required
        reason: Optional reason for disabling

    Returns:
        Updated plugin state

    Raises:
        RequiredPluginError: If plugin is required and force=False
        StateTransitionError: If state transition is invalid
    """
    # Check if plugin is required
    default_plugin = await conn.fetchrow(
        "SELECT required FROM default_plugins WHERE plugin_name = $1",
        plugin_name
    )

    if default_plugin and default_plugin["required"] and not force:
        raise RequiredPluginError(
            f"Plugin {plugin_name} is required and cannot be disabled. Use force=True to override."
        )

    # Check for dependent plugins
    dependents = await conn.fetch(
        """
        SELECT plugin_name, required
        FROM plugin_dependencies
        WHERE depends_on = $1
        """,
        plugin_name
    )

    if dependents:
        dependent_names = [d["plugin_name"] for d in dependents]
        required_dependents = [d["plugin_name"] for d in dependents if d["required"]]

        if required_dependents:
            raise StateTransitionError(
                f"Cannot disable {plugin_name}: required plugins depend on it: {required_dependents}"
            )

        logger.warning(
            f"Disabling {plugin_name} which {len(dependent_names)} plugin(s) depend on: {dependent_names}"
        )

    # Get current state
    current = await get_plugin_state(conn, plugin_name)

    if not current:
        raise StateTransitionError(f"Plugin {plugin_name} not found")

    # State transition: enabled → disabled
    if current["state"] == "enabled":
        return await update_plugin_state(conn, plugin_name, PluginState.DISABLED)
    elif current["state"] == "disabled":
        logger.info(f"Plugin {plugin_name} is already disabled")
        return current
    else:
        raise StateTransitionError(
            f"Cannot disable plugin {plugin_name} from state {current['state']}"
        )


async def list_plugin_states(
    conn: asyncpg.Connection,
    state_filter: Optional[PluginState] = None
) -> List[Dict]:
    """List all plugin states, optionally filtered by state"""
    if state_filter:
        rows = await conn.fetch(
            "SELECT * FROM plugin_states WHERE state = $1 ORDER BY plugin_name",
            state_filter.value
        )
    else:
        rows = await conn.fetch(
            "SELECT * FROM plugin_states ORDER BY plugin_name"
        )

    return [_record_to_dict(row) for row in rows]


async def get_dependent_plugins(
    conn: asyncpg.Connection,
    plugin_name: str
) -> List[Dict]:
    """Get plugins that depend on this plugin"""
    rows = await conn.fetch(
        """
        SELECT pd.plugin_name, pd.required, dp.auto_enable, dp.required as is_required
        FROM plugin_dependencies pd
        JOIN default_plugins dp ON pd.plugin_name = dp.plugin_name
        WHERE pd.depends_on = $1
        ORDER BY pd.required DESC, pd.plugin_name
        """,
        plugin_name
    )
    return [_record_to_dict(row) for row in rows]


async def resolve_dependencies(
    conn: asyncpg.Connection,
    plugin_name: str
) -> List[str]:
    """
    Resolve plugin dependencies (topological sort)

    Returns:
        Ordered list of plugin names to enable
    """
    # Build dependency graph
    plugins = {}
    dependencies = {}

    # Get all plugins and their dependencies
    rows = await conn.fetch(
        """
        SELECT dp.plugin_name, pd.depends_on, pd.required
        FROM default_plugins dp
        LEFT JOIN plugin_dependencies pd ON dp.plugin_name = pd.plugin_name
        ORDER BY dp.priority DESC
        """
    )

    for row in rows:
        name = row["plugin_name"]
        plugins[name] = {
            "visited": False,
            "deps": []
        }
        if row["depends_on"]:
            plugins[name]["deps"].append(row["depends_on"])

    # Topological sort with cycle detection
    result = []
    visited = set()

    def visit(name: str, stack: set):
        if name in stack:
            raise ValueError(f"Circular dependency detected: {' -> '.join(stack)} -> {name}")

        if name in visited:
            return

        stack.add(name)

        for dep in plugins.get(name, {}).get("deps", []):
            visit(dep, stack)

        stack.remove(name)
        visited.add(name)
        result.append(name)

    # Visit all plugins
    for name in plugins:
        visit(name, set())

    return result

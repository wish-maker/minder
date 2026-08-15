"""
Core Plugin Loader Module

Discovers and loads plugins from ``settings.PLUGINS_PATH``: every plugin is
module-based (a directory with an ``__init__.py``), imported and instantiated.
Loaded plugins are cached in ``core.state``, persisted via ``core.database``,
and their AI tools synced via ``core.marketplace_sync``.
"""

import json
from pathlib import Path

from core import plugin_config as cfgmod
from core.database import load_plugin_config, update_plugin_in_database
from core.marketplace_sync import sync_plugin_ai_tools
from core.state import logger, plugin_instances, plugins_db
from models import PluginInfo

from config import settings


async def load_plugins_from_disk():
    """Load all plugins from PLUGINS_PATH"""
    plugins_path = Path(settings.PLUGINS_PATH)

    if not plugins_path.exists():
        logger.warning(f"Plugins path does not exist: {plugins_path}")
        return

    for plugin_dir in plugins_path.iterdir():
        if not plugin_dir.is_dir():
            continue

        main_module = plugin_dir / "__init__.py"
        if main_module.exists():
            await load_plugin_from_module(plugin_dir)


async def load_plugin_from_module(plugin_dir: Path):
    """Load plugin from Python module directory"""
    plugin_name = plugin_dir.name

    try:
        # Import plugin module using importlib
        import importlib

        # Build module path: plugins.{plugin_name}
        # (/app/src is in sys.path, so we import from plugins subdir)
        module_path = f"plugins.{plugin_name}"

        module = importlib.import_module(module_path)

        # Look for Plugin class in __all__ or module attributes
        plugin_class = None
        if hasattr(module, "__all__"):
            for attr_name in module.__all__:
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and hasattr(attr, "__bases__"):
                    plugin_class = attr
                    break

        if not plugin_class:
            # Fallback: find a class exposing the plugin lifecycle. Plugins are
            # duck-typed (register/initialize/…) — there is no shared BaseModule
            # base class, so match on the lifecycle entry method defined on a
            # class that lives in this module (not an imported one).
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and hasattr(attr, "register")
                    and attr.__module__ == module.__name__
                ):
                    plugin_class = attr
                    break

        if plugin_class:
            # Create plugin configuration with proper database host
            plugin_config = {
                "database": {
                    "host": "minder-postgres",
                    "port": 5432,
                    "user": "minder",
                    # From settings (fail-fast if unset) — no weak-default secret baked in.
                    "password": settings.DB_PASSWORD,
                    "database": "minder",
                },
                "redis": {
                    "host": "minder-redis",
                    "port": 6379,
                    "password": settings.REDIS_PASSWORD,
                    "db": 0,
                },
                "influxdb": {
                    "enabled": True,
                    "host": "minder-influxdb",
                    "port": 8086,
                    "token": settings.INFLUXDB_TOKEN,
                    "org": "minder",
                    "bucket": "minder-metrics",
                },
            }

            # Instantiate and register plugin
            plugin_instance = plugin_class(plugin_config)
            metadata = await plugin_instance.register()

            # Initialize plugin to set status to READY
            await plugin_instance.initialize()

            plugin_info = PluginInfo(
                name=metadata.name,
                version=metadata.version,
                description=metadata.description,
                author=metadata.author,
                status="registered",  # Will be updated by health check
                dependencies=metadata.dependencies,
                capabilities=metadata.capabilities,
                data_sources=metadata.data_sources,
                databases=metadata.databases,
                registered_at=metadata.registered_at.isoformat(),
            )

            # Persist BEFORE mutating in-memory state (same fix shape as #351's
            # auto_enable_plugins): update_plugin_in_database re-raises on
            # failure, so a DB hiccup here must not leave the plugin instance
            # live in plugin_instances/plugins_db (reachable by health checks,
            # data collection, /actions) with nothing to show for it in the
            # database -- the two would stay out of sync until the next
            # restart's load_plugins_from_database silently drops it. Shut the
            # already-register()ed/initialize()d instance back down before
            # propagating, so it doesn't leak as an untracked live object.
            try:
                await update_plugin_in_database(
                    plugin_name,
                    version=plugin_info.version,
                    description=plugin_info.description,
                    author=plugin_info.author,
                    dependencies=(
                        json.dumps(plugin_info.dependencies)
                        if plugin_info.dependencies
                        else None
                    ),
                    capabilities=(
                        json.dumps(plugin_info.capabilities)
                        if plugin_info.capabilities
                        else None
                    ),
                    data_sources=(
                        json.dumps(plugin_info.data_sources)
                        if plugin_info.data_sources
                        else None
                    ),
                    databases=(
                        json.dumps(plugin_info.databases)
                        if plugin_info.databases
                        else None
                    ),
                )
            except Exception:
                await plugin_instance.shutdown()
                raise

            plugins_db[plugin_name] = plugin_info
            plugin_instances[plugin_name] = plugin_instance

            # Apply centrally-managed config (#34): default → env → persisted
            # (API-set) overrides, pushed live via the plugin's apply_config().
            try:
                persisted = await load_plugin_config(plugin_name)
                cfgmod.apply_effective(plugin_instance, persisted)
            except Exception as e:
                logger.warning(f"Config apply failed for {plugin_name}: {e}")

            logger.info(
                f"Loaded and registered plugin: {plugin_name} (version {plugin_info.version})"
            )

            # Auto-sync AI tools with marketplace. Module plugins have no manifest, so
            # pass their in-code AI_TOOLS, plus their real description/author (found
            # live: every module plugin was syncing with an empty description and no
            # author because this wasn't threaded through, even though metadata has
            # both right here) so the marketplace catalog isn't just placeholders.
            await sync_plugin_ai_tools(
                plugin_name,
                plugin_dir,
                module_ai_tools=getattr(plugin_instance, "AI_TOOLS", None),
                description=metadata.description,
                author=metadata.author,
                databases=metadata.databases,
                plugin_dependencies=metadata.dependencies,
            )

    except Exception as e:
        logger.error(f"Failed to load plugin from {plugin_dir}: {e}")

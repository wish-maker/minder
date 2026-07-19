"""
Core Plugin Loader Module

Discovers and loads plugins from ``settings.PLUGINS_PATH``: manifest-based plugins
(JSON/YAML) are registered from metadata, module-based plugins are imported and
instantiated. Loaded plugins are cached in ``core.state``, persisted via
``core.database``, and their AI tools synced via ``core.marketplace_sync``.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import yaml
from core.database import update_plugin_in_database
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

        # Look for plugin manifest (JSON or YAML) FIRST, then main module
        manifest_json = plugin_dir / "manifest.json"
        manifest_yml = plugin_dir / "manifest.yml"
        manifest_yaml = plugin_dir / "manifest.yaml"
        main_module = plugin_dir / "__init__.py"

        # Prefer manifest files over __init__.py
        if manifest_json.exists():
            await load_plugin_from_manifest(manifest_json, "json")
        elif manifest_yml.exists():
            await load_plugin_from_manifest(manifest_yml, "yaml")
        elif manifest_yaml.exists():
            await load_plugin_from_manifest(manifest_yaml, "yaml")
        elif main_module.exists():
            await load_plugin_from_module(plugin_dir)


async def load_plugin_from_manifest(manifest_path: Path, manifest_type: str = "json"):
    """Load plugin from manifest file (JSON or YAML)"""
    try:
        with open(manifest_path, "r") as f:
            if manifest_type == "json":
                manifest = json.load(f)
            else:  # yaml or yml
                manifest = yaml.safe_load(f)

        plugin_name = manifest.get("name")
        if not plugin_name:
            logger.error(f"Manifest missing 'name' field: {manifest_path}")
            return

        # Extract dependencies if present (handle both list and dict formats)
        dependencies_data = manifest.get("dependencies", {})
        if isinstance(dependencies_data, dict):
            dependencies_list = dependencies_data.get("python", [])
        else:
            dependencies_list = (
                dependencies_data if isinstance(dependencies_data, list) else []
            )

        # TODO: Load plugin module and call register()
        # For now, just store metadata
        plugin_info = PluginInfo(
            name=plugin_name,
            version=manifest.get("version", "1.0.0"),
            description=manifest.get("description", ""),
            author=manifest.get("author", ""),
            status="registered",
            dependencies=dependencies_list,
            capabilities=manifest.get("capabilities", []),
            data_sources=manifest.get("data_sources", []),
            databases=manifest.get("databases", []),
            registered_at=datetime.now().isoformat(),
        )

        plugins_db[plugin_name] = plugin_info
        logger.info(f"Loaded plugin: {plugin_name} (version {plugin_info.version})")

        # Persist to database
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
                json.dumps(plugin_info.databases) if plugin_info.databases else None
            ),
        )

        # Auto-sync AI tools with marketplace
        await sync_plugin_ai_tools(plugin_name, manifest_path.parent)

    except Exception as e:
        logger.error(f"Failed to load plugin from {manifest_path}: {e}")


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
                    "password": os.environ.get(
                        "POSTGRES_PASSWORD", "dev_password_change_me"
                    ),
                    "database": "minder",
                },
                "redis": {
                    "host": "minder-redis",
                    "port": 6379,
                    "password": os.environ.get(
                        "REDIS_PASSWORD", "dev_password_change_me"
                    ),
                    "db": 0,
                },
                "influxdb": {
                    "enabled": True,
                    "host": "minder-influxdb",
                    "port": 8086,
                    "token": os.environ.get(
                        "INFLUXDB_TOKEN",
                        "minder-super-secret-token-change-me-in-production",
                    ),
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

            plugins_db[plugin_name] = plugin_info
            plugin_instances[plugin_name] = plugin_instance

            logger.info(
                f"Loaded and registered plugin: {plugin_name} (version {plugin_info.version})"
            )

            # Persist to database
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
                    json.dumps(plugin_info.databases) if plugin_info.databases else None
                ),
            )

            # Auto-sync AI tools with marketplace. Module plugins have no manifest, so
            # pass their in-code AI_TOOLS so the marketplace catalog is populated too.
            await sync_plugin_ai_tools(
                plugin_name,
                plugin_dir,
                module_ai_tools=getattr(plugin_instance, "AI_TOOLS", None),
            )

    except Exception as e:
        logger.error(f"Failed to load plugin from {plugin_dir}: {e}")

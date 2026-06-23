"""
Core Plugin Loader Module

Handles plugin loading from disk, manifests, and modules.
Supports both manifest-based and module-based plugin discovery.
"""

import importlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

import yaml

logger = logging.getLogger(__name__)


async def load_plugins_from_disk():
    """
    Load all plugins from the plugins directory

    Scans /app/plugins for plugin directories and loads them.
    Supports both manifest.yml files and Python modules.

    Returns:
        Dict[str, dict]: Loaded plugins keyed by plugin name
    """
    plugins_dir = Path("/app/plugins")
    if not plugins_dir.exists():
        logger.warning(f"Plugins directory not found: {plugins_dir}")
        return {}

    plugins = {}

    for plugin_dir in plugins_dir.iterdir():
        if not plugin_dir.is_dir():
            continue

        plugin_name = plugin_dir.name
        manifest_path = plugin_dir / "manifest.yml"

        if manifest_path.exists():
            # Load from manifest
            try:
                plugin_data = await load_plugin_from_manifest(manifest_path)
                if plugin_data:
                    plugins[plugin_name] = plugin_data
                    logger.info(f"✅ Loaded plugin from manifest: {plugin_name}")
            except Exception as e:
                logger.error(f"❌ Failed to load plugin {plugin_name} from manifest: {e}")
        else:
            # Try loading as Python module
            try:
                plugin_data = await load_plugin_from_module(plugin_dir)
                if plugin_data:
                    plugins[plugin_name] = plugin_data
                    logger.info(f"✅ Loaded plugin from module: {plugin_name}")
            except Exception as e:
                logger.error(f"❌ Failed to load plugin {plugin_name} from module: {e}")

    logger.info(f"Loaded {len(plugins)} plugins from disk")
    return plugins


async def load_plugin_from_manifest(manifest_path: Path, manifest_type: str = "json") -> Dict:
    """
    Load plugin from manifest file

    Args:
        manifest_path: Path to manifest file (manifest.yml or manifest.json)
        manifest_type: Type of manifest ('json' or 'yaml')

    Returns:
        Plugin data dictionary

    Raises:
        ValueError: If manifest file not found or invalid
    """
    if not manifest_path.exists():
        raise ValueError(f"Manifest file not found: {manifest_path}")

    try:
        with open(manifest_path, 'r') as f:
            if manifest_type == "yaml":
                manifest_data = yaml.safe_load(f)
            else:
                manifest_data = json.load(f)

        # Validate manifest structure
        if not manifest_data.get('name'):
            raise ValueError("Manifest must have 'name' field")

        # Add metadata
        manifest_data['loaded_from'] = str(manifest_path)
        manifest_data['loaded_at'] = datetime.now().isoformat()

        return manifest_data

    except Exception as e:
        raise ValueError(f"Failed to load manifest: {e}")


async def load_plugin_from_module(plugin_dir: Path) -> Dict:
    """
    Load plugin from Python module

    Args:
        plugin_dir: Path to plugin directory

    Returns:
        Plugin data dictionary

    Raises:
        ValueError: If plugin module not found or invalid
    """
    plugin_name = plugin_dir.name
    module_path = plugin_dir / "plugin.py"

    if not module_path.exists():
        raise ValueError(f"Plugin module not found: {module_path}")

    try:
        # Add plugin directory to Python path
        sys.path.insert(0, str(plugin_dir))

        # Import plugin module
        module = importlib.import_module(f"{plugin_name}.plugin")

        # Extract plugin metadata from module
        plugin_data = {
            "name": getattr(module, "PLUGIN_NAME", plugin_name),
            "version": getattr(module, "PLUGIN_VERSION", "1.0.0"),
            "description": getattr(module, "PLUGIN_DESCRIPTION", ""),
            "author": getattr(module, "PLUGIN_AUTHOR", ""),
            "loaded_from": str(module_path),
            "loaded_at": datetime.now().isoformat(),
        }

        return plugin_data

    except Exception as e:
        raise ValueError(f"Failed to load plugin module: {e}")
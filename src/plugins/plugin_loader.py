"""
Plugin loader for Minder.
Handles plugin discovery and loading from local and remote sources.
"""

import asyncio
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Type, Any

import yaml

logger = logging.getLogger("minder.plugin_loader")


class PluginLoader:
    """
    Plugin loader for Minder.
    Provides plugin discovery and loading functionality.
    """

    def __init__(self, plugin_dir: Optional[Path] = None):
        """
        Initialize plugin loader.

        Args:
            plugin_dir: Directory to search for plugins
        """
        self.plugin_dir = plugin_dir or Path("src/plugins")
        self.plugins: Dict[str, Dict[str, Any]] = {}

    async def discover_plugins(
        self, plugin_dir: Optional[Path] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        Discover plugins from directory.

        Args:
            plugin_dir: Directory to search (uses default if None)

        Returns:
            Dictionary of discovered plugins
        """
        plugin_dir = plugin_dir or self.plugin_dir

        if not plugin_dir.exists():
            logger.warning(f"Plugin directory not found: {plugin_dir}")
            return {}

        plugins = {}

        # Search for manifest.yml files
        for manifest_file in plugin_dir.glob("**/manifest.yml"):
            try:
                with open(manifest_file) as f:
                    manifest = yaml.safe_load(f)

                plugin_id = manifest.get("id", "")
                if not plugin_id:
                    logger.warning(f"Missing plugin id in {manifest_file}")
                    continue

                plugins[plugin_id] = {
                    "manifest": manifest,
                    "path": manifest_file.parent,
                    "manifest_file": manifest_file,
                }

                logger.info(f"Discovered plugin: {plugin_id}")

            except Exception as e:
                logger.error(f"Error loading manifest {manifest_file}: {e}")

        self.plugins = plugins
        return plugins

    async def load_plugin(
        self, plugin_id: str, plugin_dir: Optional[Path] = None
    ) -> Optional[Any]:
        """
        Load a plugin by ID.

        Args:
            plugin_id: Plugin ID to load
            plugin_dir: Directory to search (uses default if None)

        Returns:
            Loaded plugin instance or None
        """
        plugin_dir = plugin_dir or self.plugin_dir

        if plugin_id not in self.plugins:
            logger.warning(f"Plugin not found: {plugin_id}")
            return None

        plugin_info = self.plugins[plugin_id]
        plugin_path = plugin_info["path"]

        # Load main.py from plugin directory
        main_file = plugin_path / "main.py"

        if not main_file.exists():
            logger.warning(f"Plugin main file not found: {main_file}")
            return None

        try:
            # Load plugin module
            spec = importlib.util.spec_from_file_location(
                f"src.plugins.{plugin_id}.main",
                str(main_file)
            )

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module.__name__, module)

            # Get plugin class
            plugin_class = getattr(module, "Plugin", None)

            if not plugin_class:
                logger.warning(f"Plugin class not found in {main_file}")
                return None

            # Instantiate plugin
            plugin_instance = plugin_class()

            logger.info(f"Loaded plugin: {plugin_id}")
            return plugin_instance

        except Exception as e:
            logger.error(f"Error loading plugin {plugin_id}: {e}")
            return None

    async def validate_plugin(
        self, plugin_id: str, manifest: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Validate plugin manifest.

        Args:
            plugin_id: Plugin ID to validate
            manifest: Plugin manifest (uses discovered if None)

        Returns:
            Validation result
        """
        if manifest is None:
            if plugin_id not in self.plugins:
                return {"valid": False, "errors": ["Plugin not found"]}
            manifest = self.plugins[plugin_id]["manifest"]

        errors = []

        # Validate required fields
        required_fields = ["id", "name", "version", "author", "main_file"]
        for field in required_fields:
            if field not in manifest:
                errors.append(f"Missing required field: {field}")

        # Validate version format
        version = manifest.get("version", "")
        if version and not self._is_valid_version(version):
            errors.append(f"Invalid version format: {version}")

        # Validate main file exists
        main_file = manifest.get("main_file", "")
        if main_file:
            plugin_path = self.plugin_dir / plugin_id
            main_file_path = plugin_path / main_file
            if not main_file_path.exists():
                errors.append(f"Main file not found: {main_file_path}")

        return {
            "valid": len(errors) == 0,
            "plugin_id": plugin_id,
            "errors": errors,
            "manifest": manifest,
        }

    async def unload_plugin(self, plugin_id: str) -> bool:
        """
        Unload a plugin.

        Args:
            plugin_id: Plugin ID to unload

        Returns:
            True if successful
        """
        if plugin_id in self.plugins:
            del self.plugins[plugin_id]
            logger.info(f"Unloaded plugin: {plugin_id}")
            return True

        return False

    def _is_valid_version(self, version: str) -> bool:
        """Check if version is valid (semver-like)"""
        parts = version.split(".")
        if len(parts) != 3:
            return False

        for part in parts:
            if not part.isdigit():
                return False

        return True

    def get_plugin_manifest(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        Get plugin manifest.

        Args:
            plugin_id: Plugin ID

        Returns:
            Plugin manifest or None
        """
        if plugin_id in self.plugins:
            return self.plugins[plugin_id]["manifest"]
        return None

    async def get_all_plugins(self) -> List[Dict[str, Any]]:
        """
        Get all plugins with metadata.

        Returns:
            List of plugins
        """
        return [
            {
                "id": plugin_id,
                "manifest": self.plugins[plugin_id]["manifest"],
                "path": str(self.plugins[plugin_id]["path"]),
            }
            for plugin_id in self.plugins
        ]

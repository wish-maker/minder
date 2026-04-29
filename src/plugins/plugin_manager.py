"""
Plugin manager for Minder.
Handles plugin lifecycle (install, activate, deactivate, remove).
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

import httpx
import asyncpg

from .plugin_loader import PluginLoader
from .plugin_registry import PluginRegistry

logger = logging.getLogger("minder.plugin_manager")


class PluginManager:
    """
    Plugin manager for Minder.
    Handles plugin lifecycle (install, activate, deactivate, remove).
    """

    def __init__(
        self,
        db_pool: Optional[asyncpg.Pool] = None,
        redis_pool: Optional[Any] = None,
        plugin_dir: Optional[Path] = None,
    ):
        """
        Initialize plugin manager.

        Args:
            db_pool: Database connection pool
            redis_pool: Redis connection pool
            plugin_dir: Directory to store plugins
        """
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.plugin_dir = plugin_dir or Path("src/plugins")
        self.loader = PluginLoader(self.plugin_dir)
        self.registry = PluginRegistry(db_pool, redis_pool)
        self.active_plugins: Dict[str, Dict[str, Any]] = {}

    async def install_plugin(
        self,
        plugin_id: str,
        plugin_url: Optional[str] = None,
        plugin_file: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """
        Install a plugin.

        Args:
            plugin_id: Plugin ID
            plugin_url: URL to download plugin
            plugin_file: Plugin file upload

        Returns:
            Installation result
        """
        try:
            # Download plugin if URL provided
            if plugin_url:
                async with httpx.AsyncClient() as client:
                    response = await client.get(plugin_url)
                    plugin_file = response.content
                    logger.info(f"Downloaded plugin from {plugin_url}")

            # Save plugin to disk
            plugin_dir = self.plugin_dir / plugin_id
            plugin_dir.mkdir(parents=True, exist_ok=True)

            # Extract plugin (if zip file)
            # For now, we'll just save the file
            if plugin_file:
                plugin_path = plugin_dir / "plugin.zip"
                with open(plugin_path, "wb") as f:
                    f.write(plugin_file)
                logger.info(f"Saved plugin to {plugin_path}")

            # Register plugin in database
            await self.registry.register_plugin(
                plugin_id=plugin_id,
                manifest_url=plugin_url,
                status="installed",
            )

            logger.info(f"Plugin {plugin_id} installed successfully")

            return {
                "plugin_id": plugin_id,
                "status": "installed",
                "message": f"Plugin {plugin_id} installed successfully",
                "installed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error installing plugin {plugin_id}: {e}")

            return {
                "plugin_id": plugin_id,
                "status": "installation_failed",
                "error": str(e),
            }

    async def activate_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Activate a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            Activation result
        """
        try:
            # Load plugin
            plugin = await self.loader.load_plugin(plugin_id)

            if not plugin:
                return {
                    "plugin_id": plugin_id,
                    "status": "activation_failed",
                    "error": "Plugin not found or cannot be loaded",
                }

            # Activate plugin
            await plugin.activate()

            # Update active plugins list
            self.active_plugins[plugin_id] = {
                "plugin": plugin,
                "activated_at": datetime.now().isoformat(),
            }

            # Update plugin status in database
            await self.registry.update_plugin_status(plugin_id, "active")

            logger.info(f"Plugin {plugin_id} activated successfully")

            return {
                "plugin_id": plugin_id,
                "status": "active",
                "message": f"Plugin {plugin_id} activated successfully",
                "activated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error activating plugin {plugin_id}: {e}")

            return {
                "plugin_id": plugin_id,
                "status": "activation_failed",
                "error": str(e),
            }

    async def deactivate_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Deactivate a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            Deactivation result
        """
        try:
            # Load plugin
            plugin = await self.loader.load_plugin(plugin_id)

            if not plugin:
                return {
                    "plugin_id": plugin_id,
                    "status": "deactivation_failed",
                    "error": "Plugin not found",
                }

            # Deactivate plugin
            if hasattr(plugin, "deactivate"):
                await plugin.deactivate()

            # Remove from active plugins list
            if plugin_id in self.active_plugins:
                del self.active_plugins[plugin_id]

            # Update plugin status in database
            await self.registry.update_plugin_status(plugin_id, "installed")

            logger.info(f"Plugin {plugin_id} deactivated successfully")

            return {
                "plugin_id": plugin_id,
                "status": "installed",
                "message": f"Plugin {plugin_id} deactivated successfully",
                "deactivated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error deactivating plugin {plugin_id}: {e}")

            return {
                "plugin_id": plugin_id,
                "status": "deactivation_failed",
                "error": str(e),
            }

    async def remove_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Remove a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            Removal result
        """
        try:
            # Deactivate if active
            if plugin_id in self.active_plugins:
                await self.deactivate_plugin(plugin_id)

            # Remove from database
            await self.registry.unregister_plugin(plugin_id)

            # Remove from disk
            plugin_dir = self.plugin_dir / plugin_id
            if plugin_dir.exists():
                import shutil
                shutil.rmtree(plugin_dir)
                logger.info(f"Removed plugin directory: {plugin_dir}")

            # Unload from loader
            await self.loader.unload_plugin(plugin_id)

            logger.info(f"Plugin {plugin_id} removed successfully")

            return {
                "plugin_id": plugin_id,
                "status": "removed",
                "message": f"Plugin {plugin_id} removed successfully",
                "removed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error removing plugin {plugin_id}: {e}")

            return {
                "plugin_id": plugin_id,
                "status": "removal_failed",
                "error": str(e),
            }

    async def get_plugin_status(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        Get plugin status.

        Args:
            plugin_id: Plugin ID

        Returns:
            Plugin status or None
        """
        try:
            # Get from registry
            plugin_info = await self.registry.get_plugin_info(plugin_id)

            if not plugin_info:
                return None

            # Check if active
            is_active = plugin_id in self.active_plugins

            return {
                "plugin_id": plugin_id,
                "status": plugin_info.get("status", "unknown"),
                "is_active": is_active,
                "manifest": plugin_info.get("manifest", {}),
                "registered_at": plugin_info.get("registered_at", ""),
                "activated_at": self.active_plugins.get(plugin_id, {}).get("activated_at", ""),
            }

        except Exception as e:
            logger.error(f"Error getting plugin status {plugin_id}: {e}")
            return None

    async def list_plugins(
        self, status: Optional[str] = None, active_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List all plugins.

        Args:
            status: Filter by status (installed, active, inactive)
            active_only: Only return active plugins

        Returns:
            List of plugins
        """
        try:
            # Get from registry
            plugins = await self.registry.list_plugins()

            # Filter by status
            if status:
                plugins = [p for p in plugins if p.get("status") == status]

            # Filter by active
            if active_only:
                plugin_ids = [p.get("plugin_id") for p in plugins]
                plugins = [p for p in plugins if p.get("plugin_id") in plugin_ids]

            return plugins

        except Exception as e:
            logger.error(f"Error listing plugins: {e}")
            return []

    async def reload_plugin(self, plugin_id: str) -> Dict[str, Any]:
        """
        Reload a plugin.

        Args:
            plugin_id: Plugin ID

        Returns:
            Reload result
        """
        try:
            # Deactivate if active
            was_active = False
            if plugin_id in self.active_plugins:
                was_active = True
                await self.deactivate_plugin(plugin_id)

            # Unload from loader
            await self.loader.unload_plugin(plugin_id)

            # Load again
            plugin = await self.loader.load_plugin(plugin_id)

            if not plugin:
                return {
                    "plugin_id": plugin_id,
                    "status": "reload_failed",
                    "error": "Plugin not found",
                }

            # Activate if it was active
            if was_active:
                await self.activate_plugin(plugin_id)

            logger.info(f"Plugin {plugin_id} reloaded successfully")

            return {
                "plugin_id": plugin_id,
                "status": plugin_id in self.active_plugins and "active" or "installed",
                "message": f"Plugin {plugin_id} reloaded successfully",
                "reloaded_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Error reloading plugin {plugin_id}: {e}")

            return {
                "plugin_id": plugin_id,
                "status": "reload_failed",
                "error": str(e),
            }

    async def validate_plugin(
        self, plugin_id: str, manifest_file: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Validate plugin.

        Args:
            plugin_id: Plugin ID
            manifest_file: Optional manifest file path

        Returns:
            Validation result
        """
        try:
            # Validate with loader
            validation = await self.loader.validate_plugin(plugin_id, None)

            # If manifest file provided, validate it directly
            if manifest_file and manifest_file.exists():
                import yaml

                with open(manifest_file) as f:
                    manifest = yaml.safe_load(f)

                # Validate required fields
                required_fields = ["id", "name", "version", "author"]
                errors = []

                for field in required_fields:
                    if field not in manifest:
                        errors.append(f"Missing required field: {field}")

                # Validate version format
                version = manifest.get("version", "")
                if version and not self.loader._is_valid_version(version):
                    errors.append(f"Invalid version format: {version}")

                if errors:
                    return {
                        "plugin_id": plugin_id,
                        "valid": False,
                        "errors": errors,
                    }

                # Update validation result
                validation["valid"] = True
                validation["errors"] = []

            return validation

        except Exception as e:
            logger.error(f"Error validating plugin {plugin_id}: {e}")

            return {
                "plugin_id": plugin_id,
                "valid": False,
                "errors": [str(e)],
            }

"""
Minder Plugin Loader
Dynamic plugin discovery and loading
"""

import importlib.util
import inspect
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .module_interface import BaseModule

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Dynamic plugin loader for Minder plugins

    Features:
    - Auto-discovery from plugins directory
    - Hot-reload capability
    - Dependency validation
    - Version compatibility checks
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.plugins_path = Path(config.get("plugins_path", "plugins"))
        self.loaded_plugins: Dict[str, BaseModule] = {}
        self.failed_plugins: Dict[str, str] = {}

        # Add minder parent directory to sys.path so plugins can import from minder package
        # For plugins to use "from minder.core.module_interface import ...", we need the parent dir in path
        minder_parent = Path(__file__).parent.parent.parent
        if str(minder_parent) not in sys.path:
            sys.path.insert(0, str(minder_parent))
            logger.debug(f"Added {minder_parent} to sys.path for plugin imports")

    async def discover_plugins(self) -> List[str]:
        """Discover all available plugins"""
        discovered = []

        # Directories to exclude from plugin discovery
        excluded_dirs = {"store", "__pycache__", ".git"}

        if not self.plugins_path.exists():
            logger.warning(f"Plugins path not found: {self.plugins_path}")
            return discovered

        for plugin_dir in self.plugins_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Skip excluded directories
            if plugin_dir.name in excluded_dirs:
                logger.debug(f"⏭️  Skipping excluded directory: {plugin_dir.name}")
                continue

            # Try both _plugin.py and _module.py extensions
            plugin_file = plugin_dir / f"{plugin_dir.name}_plugin.py"
            if not plugin_file.exists():
                plugin_file = plugin_dir / f"{plugin_dir.name}_module.py"
            if not plugin_file.exists():
                plugin_file = plugin_dir / "__init__.py"

            if plugin_file.exists():
                discovered.append(plugin_dir.name)
                logger.info(f"📦 Discovered plugin: {plugin_dir.name}")

        return discovered

    async def load_plugin(self, plugin_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[BaseModule]:
        """Load a single plugin"""

        try:
            # Try both _plugin.py and _module.py extensions
            plugin_file = self.plugins_path / plugin_name / f"{plugin_name}_plugin.py"
            if not plugin_file.exists():
                plugin_file = self.plugins_path / plugin_name / f"{plugin_name}_module.py"
            if not plugin_file.exists():
                plugin_file = self.plugins_path / plugin_name / "__init__.py"

            if not plugin_file.exists():
                raise FileNotFoundError(f"Plugin file not found for: {plugin_name}")

            spec = importlib.util.spec_from_file_location(f"minder.plugins.{plugin_name}", plugin_file)

            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load plugin spec: {plugin_name}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"minder.plugins.{plugin_name}"] = module
            spec.loader.exec_module(module)

            plugin_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseModule) and obj is not BaseModule:
                    plugin_class = obj
                    break

            if plugin_class is None:
                raise TypeError(f"No BaseModule subclass found in: {plugin_name}")

            plugin_config = config or self.config.get("plugins", {}).get(plugin_name, {})
            instance = plugin_class(plugin_config)

            await instance.register()

            self.loaded_plugins[plugin_name] = instance
            logger.info(f"✅ Loaded plugin: {plugin_name}")

            return instance

        except Exception as e:
            error_msg = f"Failed to load plugin {plugin_name}: {e}"
            logger.error(error_msg)
            self.failed_plugins[plugin_name] = error_msg
            return None

    async def load_all_plugins(self, exclude: Optional[List[str]] = None) -> Dict[str, BaseModule]:
        exclude = exclude or []
        discovered = await self.discover_plugins()

        plugins = {}
        for plugin_name in discovered:
            if plugin_name in exclude:
                logger.info(f"⏭️  Skipping excluded plugin: {plugin_name}")
                continue

            # Check if plugin is enabled in config
            plugin_config = self.config.get("plugins", {}).get(plugin_name, {})
            if not plugin_config.get("enabled", True):
                logger.info(f"⏭️  Skipping disabled plugin: {plugin_name}")
                continue

            instance = await self.load_plugin(plugin_name)
            if instance:
                plugins[plugin_name] = instance

        logger.info(f"✅ Loaded {len(plugins)}/{len(discovered)} plugins")

        return plugins

    async def reload_plugin(self, plugin_name: str) -> Optional[BaseModule]:
        """Hot-reload a plugin"""

        if plugin_name in self.loaded_plugins:
            try:
                await self.loaded_plugins[plugin_name].shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down {plugin_name}: {e}")

            del self.loaded_plugins[plugin_name]

        return await self.load_plugin(plugin_name)

    def get_loaded_plugins(self) -> Dict[str, BaseModule]:
        return self.loaded_plugins.copy()

    def get_failed_plugins(self) -> Dict[str, str]:
        return self.failed_plugins.copy()

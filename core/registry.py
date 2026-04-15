"""
Minder Plugin Registry
Discovers, registers, and manages all plugins
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import logging
from pathlib import Path

from .module_interface import BaseModule, ModuleMetadata, ModuleStatus

logger = logging.getLogger(__name__)

class PluginRegistry:
    """Central registry for all Minder plugins"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.plugins: Dict[str, 'BaseModule'] = {}
        self.metadata: Dict[str, 'ModuleMetadata'] = {}
        self.dependency_graph: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()

    async def register_plugin(self, plugin: 'BaseModule') -> bool:
        """Register a new plugin"""
        async with self._lock:
            try:
                metadata = await plugin.register()

                if metadata.name in self.plugins:
                    logger.warning(f"Plugin {metadata.name} already registered, skipping")
                    return False

                # Check if plugin is enabled in config
                plugin_config = self.config.get('plugins', {}).get(metadata.name, {})
                if not plugin_config.get('enabled', True):
                    logger.info(f"⏭️  Plugin {metadata.name} is disabled in config, skipping")
                    return False

                for dep in metadata.dependencies:
                    if dep not in self.plugins:
                        logger.error(f"Plugin {metadata.name} depends on {dep} which is not registered")
                        return False

                self.plugins[metadata.name] = plugin
                self.metadata[metadata.name] = metadata
                self.dependency_graph[metadata.name] = metadata.dependencies

                plugin.status = ModuleStatus.REGISTERED
                logger.info(f"✅ Plugin registered: {metadata.name} v{metadata.version}")

                return True

            except Exception as e:
                logger.error(f"Failed to register plugin: {e}")
                return False

    async def initialize_all(self) -> Dict[str, bool]:
        """Initialize all registered plugins in dependency order"""
        results = {}

        order = self._get_dependency_order()

        for plugin_name in order:
            plugin = self.plugins[plugin_name]
            try:
                plugin.status = ModuleStatus.INITIALIZING
                await self._initialize_plugin(plugin)
                plugin.status = ModuleStatus.READY
                results[plugin_name] = True
                logger.info(f"✅ Plugin initialized: {plugin_name}")
            except Exception as e:
                plugin.status = ModuleStatus.ERROR
                results[plugin_name] = False
                logger.error(f"❌ Plugin initialization failed: {plugin_name} - {e}")

        return results

    async def get_plugin(self, name: str) -> Optional['BaseModule']:
        """Get registered plugin by name"""
        return self.plugins.get(name)

    async def list_plugins(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all plugins, optionally filtered by status"""
        plugins = []
        for name, plugin in self.plugins.items():
            if status is None or plugin.status.value == status:
                plugins.append({
                    'name': name,
                    'metadata': {
                        'name': self.metadata[name].name,
                        'version': self.metadata[name].version,
                        'description': self.metadata[name].description,
                        'capabilities': self.metadata[name].capabilities,
                        'author': self.metadata[name].author
                    },
                    'status': plugin.status.value
                })
        return plugins

    def _get_dependency_order(self) -> List[str]:
        """Topological sort for initialization order"""
        order = []
        visited = set()

        def visit(plugin_name):
            if plugin_name in visited:
                return
            visited.add(plugin_name)
            for dep in self.dependency_graph.get(plugin_name, []):
                visit(dep)
            order.append(plugin_name)

        for plugin_name in self.plugins:
            visit(plugin_name)

        return order

    async def _initialize_plugin(self, plugin: 'BaseModule'):
        """Plugin-specific initialization hook"""
        pass

    async def shutdown_all(self):
        """Shutdown all plugins"""
        for name, plugin in self.plugins.items():
            try:
                await plugin.shutdown()
                logger.info(f"✅ Plugin shut down: {name}")
            except Exception as e:
                logger.error(f"❌ Plugin shutdown failed: {name} - {e}")

    async def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin at runtime"""
        if plugin_name in self.plugins:
            logger.warning(f"Plugin {plugin_name} is already loaded")
            return True

        # Update config
        if 'plugins' not in self.config:
            self.config['plugins'] = {}
        if plugin_name not in self.config['plugins']:
            self.config['plugins'][plugin_name] = {}
        self.config['plugins'][plugin_name]['enabled'] = True

        logger.info(f"✅ Plugin {plugin_name} enabled")
        return True

    async def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin at runtime"""
        if plugin_name not in self.plugins:
            logger.warning(f"Plugin {plugin_name} is not loaded")
            return True

        # Shutdown the plugin
        try:
            await self.plugins[plugin_name].shutdown()
        except Exception as e:
            logger.error(f"Error shutting down plugin {plugin_name}: {e}")

        # Remove from registry
        del self.plugins[plugin_name]
        del self.metadata[plugin_name]
        if plugin_name in self.dependency_graph:
            del self.dependency_graph[plugin_name]

        # Update config
        if 'plugins' not in self.config:
            self.config['plugins'] = {}
        if plugin_name not in self.config['plugins']:
            self.config['plugins'][plugin_name] = {}
        self.config['plugins'][plugin_name]['enabled'] = False

        logger.info(f"✅ Plugin {plugin_name} disabled and unloaded")
        return True

    def is_plugin_enabled(self, plugin_name: str) -> bool:
        """Check if a plugin is enabled in config"""
        plugin_config = self.config.get('plugins', {}).get(plugin_name, {})
        return plugin_config.get('enabled', True)

    def list_available_plugins(self) -> List[str]:
        """List all available plugins (enabled + disabled)"""
        plugins_dir = Path("plugins")
        if not plugins_dir.exists():
            return []

        plugin_dirs = [d.name for d in plugins_dir.iterdir() if d.is_dir() and not d.name.startswith('_')]
        return plugin_dirs

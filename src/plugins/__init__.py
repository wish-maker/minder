"""
Plugin system for Minder.
Provides plugin discovery, installation, and lifecycle management.
"""

from .plugin_loader import PluginLoader
from .plugin_manager import PluginManager
from .plugin_registry import PluginRegistry

__all__ = [
    "PluginLoader",
    "PluginManager",
    "PluginRegistry",
]

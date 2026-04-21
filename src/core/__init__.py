"""
Minder Core Module
Microkernel architecture for modular RAG platform
"""

__version__ = "2.0.0"
__author__ = "FundMind AI"

from .event_bus import Event, EventBus, EventType

# Note: MinderKernel is disabled (not yet implemented)
# from .kernel import MinderKernel
from .module_interface_v2 import BaseModule, ModuleMetadata, ModuleStatus
from .plugin_loader import PluginLoader
from .registry import PluginRegistry

__all__ = [
    "BaseModule",
    "ModuleMetadata",
    "ModuleStatus",
    "PluginRegistry",
    # "MinderKernel",  # Disabled
    "EventBus",
    "EventType",
    "Event",
    "PluginLoader",
]

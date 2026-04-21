"""
Minder Plugin Interface v1 (Legacy)
This file re-exports v2 interface for backward compatibility
DEPRECATED: Use module_interface_v2.py instead
"""

from .module_interface_v2 import BaseModule, ModuleMetadata, ModuleStatus

__all__ = ["BaseModule", "ModuleMetadata", "ModuleStatus"]

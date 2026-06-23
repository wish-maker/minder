"""
Shared configuration package
Common configuration classes and settings for Minder services
"""

from .base_settings import MinderBaseSettings, get_service_settings

__all__ = [
    "MinderBaseSettings",
    "get_service_settings",
]

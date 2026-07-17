"""
Shared runtime state for the plugin registry.

Centralizes the in-memory caches and the Redis client that the loader, webhook,
monitoring and database helpers all read from and write to. Keeping this state in
one module lets those concerns live in separate `core/` modules (instead of one
main.py monolith) while still operating on the same objects.

The caches are mutated in place (never reassigned), so importing them by name and
mutating them from any module is safe. The PostgreSQL pool is reassigned lazily and
therefore lives in `core.database`, which owns it.
"""

import logging
from typing import Any, Dict

import redis
from models import PluginInfo, ServiceRegistration

from config import settings

logger = logging.getLogger("minder.plugin-registry")

# ============================================================================
# In-memory caches
# ============================================================================

plugins_db: Dict[str, PluginInfo] = {}  # name -> PluginInfo
plugin_instances: Dict[str, Any] = {}  # name -> live plugin instance
services_db: Dict[str, ServiceRegistration] = {}  # name -> ServiceRegistration
webhook_routes: Dict[str, str] = {}  # /webhook/<path> -> plugin_name
plugin_manifests: Dict[str, Dict] = {}  # plugin_name -> manifest

# ============================================================================
# Infrastructure clients
# ============================================================================

# Redis client for service discovery and caching
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    db=0,
)

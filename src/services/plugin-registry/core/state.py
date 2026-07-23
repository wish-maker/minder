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
import sys
from typing import Any, Dict

from models import PluginInfo, ServiceRegistration

from config import settings

# Shared Redis factory is the single source of truth for client construction
# (issue #49). main.py inserts /app/src before importing this module, but guard
# here too so import order can't break the shared import.
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.utils.redis_client import create_redis_client_from_settings  # noqa: E402

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

# Redis client for service discovery and caching. ping=False keeps the original lazy
# behaviour (module-level singleton created at import) — redis.Redis connects on first
# command, unchanged from the previous hand-rolled client. Same params/db=0/decode.
redis_client = create_redis_client_from_settings(settings, ping=False)

"""Centralized settings for the Plugin State Manager service.

Single source of truth for the service's configuration. Extends
shared.config.MinderBaseSettings, inheriting the required-secret contract
(DB_PASSWORD, REDIS_PASSWORD, JWT_SECRET must come from the environment — no weak
defaults). Previously the Settings class lived in main.py while core/ helpers read
env vars directly via os.getenv; keeping settings in this module lets every module
import one object instead of re-reading the environment.
"""

import sys

# shared.config lives under /app/src; guard the path so this module imports cleanly
# regardless of who imports it first (main.py inserts it too).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.config import MinderBaseSettings  # noqa: E402


class Settings(MinderBaseSettings):
    """Plugin State Manager settings.

    Inherits common fields + the required-secret contract from
    shared.config.MinderBaseSettings; only the service-specific overrides live here.
    """

    APP_NAME: str = "Plugin State Manager"
    VERSION: str = "2.1.0"
    PORT: int = 8003
    DB_NAME: str = "minder_marketplace"
    DEFAULT_PLUGINS_CONFIG: str = "/app/src/bootstrap/config/default_plugins.yml"

    # Downstream service URLs. Resolved from config (env-overridable) instead of
    # hardcoded literals scattered across core/, so a moved peer / renamed container /
    # off-network run doesn't require editing call sites.
    MARKETPLACE_URL: str = "http://minder-marketplace:8002"
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"

    # HTTP timeouts (seconds). An actual AI-tool execution may do real work (e.g. the
    # network/nmap plugin), so it gets a generous ceiling aligned with the gateway's
    # _call_plugin_tool (60s) — otherwise a slow tool 504s via this path while
    # succeeding via the gateway. Marketplace catalog lookups are fast reads.
    TOOL_EXECUTION_TIMEOUT: float = 60.0
    CATALOG_HTTP_TIMEOUT: float = 10.0


settings = Settings()

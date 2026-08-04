"""
Plugin Registry Configuration
Loads settings from environment variables with sensible defaults
"""

import sys

# MinderBaseSettings + shared packages live under /app/src (#265).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.config import MinderBaseSettings  # noqa: E402


class Settings(MinderBaseSettings):
    """Plugin Registry Settings"""

    # Database
    DB_NAME: str = "minder"

    # Service Discovery
    SERVICE_REGISTRY_BACKEND: str = "redis"

    # InfluxDB token passed to data plugins' write config. Optional (empty default —
    # dev influx runs --without-auth, #109) so we never bake in a weak fallback secret.
    INFLUXDB_TOKEN: str = ""

    # Plugin Storage
    PLUGINS_PATH: str = "/app/plugins"
    PLUGINS_DATA_PATH: str = "/app/plugins-data"

    # Bundles (#65 item 2). The compose file (bundle map source of truth via
    # minder.bundle= labels) is mounted read-only; the secret-free enable-state is
    # mounted read-WRITE for the mutating endpoints (enable/disable/reconcile persist
    # intent here — the same file the host CLI writes). Absent → everything enabled.
    BUNDLES_COMPOSE_PATH: str = "/app/bundles/docker-compose.yml"
    BUNDLES_STATE_PATH: str = "/app/bundles/bundles.state.json"
    # Container-name prefix (compose names services `minder-<svc>`) — used to map a
    # bundle's service names to container names for start/stop via the socket-proxy.
    CONTAINER_PREFIX: str = "minder"

    # Health Monitoring
    HEALTH_CHECK_INTERVAL_SECONDS: int = 30
    HEALTH_CHECK_TIMEOUT_SECONDS: int = 10

    # Application
    API_VERSION: str = "v1"


# Global settings instance
settings = Settings()

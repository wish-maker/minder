"""
Plugin Registry Configuration
Loads settings from environment variables with sensible defaults
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Plugin Registry Settings"""

    # Database
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "minder"
    POSTGRES_PASSWORD: str  # Required: must be set via environment variable
    POSTGRES_DB: str = "minder"

    @field_validator("POSTGRES_PASSWORD")
    @classmethod
    def check_postgres_password(cls, v: str) -> str:
        if not v:
            raise ValueError("POSTGRES_PASSWORD must be set via environment variable")
        return v

    # Service Discovery
    SERVICE_REGISTRY_BACKEND: str = "redis"
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str  # Required: must be set via environment variable

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def check_redis_password(cls, v: str) -> str:
        if not v:
            raise ValueError("REDIS_PASSWORD must be set via environment variable")
        return v

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
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    API_VERSION: str = "v1"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


# Global settings instance
settings = Settings()

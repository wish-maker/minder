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

    # Plugin Storage
    PLUGINS_PATH: str = "/app/plugins"
    PLUGINS_DATA_PATH: str = "/app/plugins-data"

    # Bundles (read-only view, #65 item 2). The compose file (bundle map source of
    # truth via minder.bundle= labels) and the secret-free enable-state are mounted
    # read-only; the state file may be absent (→ everything enabled).
    BUNDLES_COMPOSE_PATH: str = "/app/bundles/docker-compose.yml"
    BUNDLES_STATE_PATH: str = "/app/bundles/bundles.state.json"

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

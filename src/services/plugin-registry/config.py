"""
Plugin Registry Configuration
Loads settings from environment variables with sensible defaults
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Plugin Registry Settings"""

    # Database
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "minder"
    POSTGRES_PASSWORD: str = "dev_password_change_me"
    POSTGRES_DB: str = "minder"

    # Service Discovery
    SERVICE_REGISTRY_BACKEND: str = "redis"
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "dev_password_change_me"

    # Plugin Storage
    PLUGINS_PATH: str = "/app/plugins"
    PLUGINS_DATA_PATH: str = "/app/plugins-data"

    # Health Monitoring
    HEALTH_CHECK_INTERVAL_SECONDS: int = 30
    HEALTH_CHECK_TIMEOUT_SECONDS: int = 10

    # Application
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    API_VERSION: str = "v1"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()

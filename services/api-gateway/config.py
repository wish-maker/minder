"""
API Gateway Configuration
Loads settings from environment variables with sensible defaults
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API Gateway Settings"""

    # Service Discovery
    PLUGIN_REGISTRY_URL: str = "http://plugin-registry:8001"
    RAG_PIPELINE_URL: str = "http://rag-pipeline:8004"
    MODEL_MANAGEMENT_URL: str = "http://model-management:8005"

    # Infrastructure
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "dev_password_change_me"

    # JWT Authentication
    JWT_SECRET: str = "dev_jwt_secret_change_me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 100

    # Application
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    API_VERSION: str = "v1"

    # CORS Configuration
    CORS_ALLOWED_ORIGINS: str = "*"  # Comma-separated list, e.g., "http://localhost:3000,https://example.com"

    # Phase Configuration (for health check)
    MINDER_PHASE: int = 1  # Current deployment phase

    # Pydantic V2 Configuration
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="allow")


# Global settings instance
settings = Settings()

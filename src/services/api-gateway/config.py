"""
API Gateway Configuration
Loads settings from environment variables with sensible defaults
"""

from pydantic import field_validator
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
    REDIS_PASSWORD: str  # Required: must be set via environment variable

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def check_redis_password(cls, v: str) -> str:
        if not v:
            raise ValueError("REDIS_PASSWORD must be set via environment variable")
        return v

    # PostgreSQL
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

    # JWT Authentication
    JWT_SECRET: str  # Required: must be set via environment variable
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    @field_validator("JWT_SECRET")
    @classmethod
    def check_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError("JWT_SECRET must be set via environment variable")
        return v

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 100

    # Application
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    API_VERSION: str = "v1"

    # CORS Configuration
    CORS_ALLOWED_ORIGINS: str = (
        "*"  # Comma-separated list, e.g., "http://localhost:3000,https://example.com"
    )

    # Phase Configuration (for health check)
    MINDER_PHASE: int = 1  # Current deployment phase

    # Pydantic V2 Configuration
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="allow"
    )


# Global settings instance
settings = Settings()

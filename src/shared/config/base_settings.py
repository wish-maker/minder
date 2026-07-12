"""
Base settings class for Minder services
Provides common configuration defaults to reduce duplication across services.

Secrets (DB_PASSWORD, REDIS_PASSWORD, JWT_SECRET) are REQUIRED — no defaults — so
adopting this base hardens a service rather than silently falling back to a weak
"dev" password. Services that use those backends supply them via the environment
(compose passes POSTGRES_PASSWORD/REDIS_PASSWORD/JWT_SECRET from .env). Services
that need none of the secret-bearing backends should not inherit this base.
"""

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MinderBaseSettings(BaseSettings):
    """Base settings with common Minder platform defaults"""

    # ========================================================================
    # Service Identity
    # ========================================================================
    APP_NAME: str = "Minder Service"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    # ========================================================================
    # Server Configuration
    # ========================================================================
    HOST: str = "0.0.0.0"  # nosec B104 — containers bind all interfaces
    PORT: int = 8000

    # ========================================================================
    # Database Configuration
    # ========================================================================
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_USER: str = "minder"
    DB_PASSWORD: str  # Required — must be set via environment variable
    DB_NAME: Optional[str] = None  # Service-specific

    # ========================================================================
    # Redis Configuration
    # ========================================================================
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str  # Required — must be set via environment variable
    REDIS_DB: int = 0

    # ========================================================================
    # Logging Configuration
    # ========================================================================
    LOG_LEVEL: str = "INFO"

    # ========================================================================
    # Security Configuration
    # ========================================================================
    JWT_SECRET: str  # Required — must be set via environment variable
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # ========================================================================
    # CORS Configuration
    # ========================================================================
    CORS_ALLOWED_ORIGINS: Optional[str] = None  # Comma-separated list

    # ========================================================================
    # Service URLs (Common Internal Services)
    # ========================================================================
    MARKETPLACE_URL: str = "http://minder-marketplace:8002"
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"
    API_GATEWAY_URL: str = "http://minder-api-gateway:8000"
    RAG_PIPELINE_URL: str = "http://minder-rag-pipeline:8004"

    # ========================================================================
    # AI/Model Configuration
    # ========================================================================
    OLLAMA_HOST: str = "http://ollama:11434"
    DEFAULT_MODEL: str = "llama3.2"

    @field_validator("DB_PASSWORD", "REDIS_PASSWORD", "JWT_SECRET")
    @classmethod
    def _require_non_empty_secret(cls, v: str, info) -> str:
        if not v:
            raise ValueError(f"{info.field_name} must be set via environment variable")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="allow",  # Allow service-specific settings
    )

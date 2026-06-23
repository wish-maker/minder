"""
Base settings class for Minder services
Provides common configuration defaults to reduce duplication across services
"""

from typing import Optional

from pydantic_settings import BaseSettings


class MinderBaseSettings(BaseSettings):
    """Base settings with common Minder platform defaults"""

    # ============================================================================
    # Service Identity
    # ============================================================================
    APP_NAME: str = "Minder Service"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    # ============================================================================
    # Server Configuration
    # ============================================================================
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ============================================================================
    # Database Configuration
    # ============================================================================
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_USER: str = "minder"
    DB_PASSWORD: str = "minder"
    DB_NAME: Optional[str] = None  # Service-specific

    # ============================================================================
    # Redis Configuration
    # ============================================================================
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "minder"
    REDIS_DB: int = 0

    # ============================================================================
    # Logging Configuration
    # ============================================================================
    LOG_LEVEL: str = "INFO"

    # ============================================================================
    # Security Configuration
    # ============================================================================
    JWT_SECRET: str = "dev_jwt_secret_change_me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # ============================================================================
    # CORS Configuration
    # ============================================================================
    CORS_ALLOWED_ORIGINS: Optional[str] = None  # Comma-separated list

    # ============================================================================
    # Service URLs (Common Internal Services)
    # ============================================================================
    MARKETPLACE_URL: str = "http://minder-marketplace:8002"
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"
    API_GATEWAY_URL: str = "http://minder-api-gateway:8000"
    RAG_PIPELINE_URL: str = "http://minder-rag-pipeline:8004"

    # ============================================================================
    # AI/Model Configuration
    # ============================================================================
    OLLAMA_HOST: str = "http://ollama:11434"
    DEFAULT_MODEL: str = "llama3.2"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # Allow service-specific settings


def get_service_settings(service_name: str, **kwargs) -> MinderBaseSettings:
    """
    Factory function to create settings for a specific service

    Args:
        service_name: Name of the service (e.g., "marketplace", "plugin-registry")
        **kwargs: Service-specific overrides

    Returns:
        Configured settings instance

    Example:
        >>> settings = get_service_settings(
        ...     "marketplace",
        ...     PORT=8002,
        ...     DB_NAME="minder_marketplace"
        ... )
    """
    defaults = {
        "APP_NAME": f"Minder {service_name.replace('-', ' ').title()}",
        "VERSION": "1.0.0",
    }
    defaults.update(kwargs)
    return MinderBaseSettings(**defaults)

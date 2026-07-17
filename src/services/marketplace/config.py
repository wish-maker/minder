# services/marketplace/config.py
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketplaceSettings(BaseSettings):
    """Marketplace service settings"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Service settings
    MARKETPLACE_HOST: str = "0.0.0.0"
    MARKETPLACE_PORT: int = 8002

    # Database
    MARKETPLACE_DATABASE_HOST: str = "minder-postgres"
    MARKETPLACE_DATABASE_PORT: int = 5432
    MARKETPLACE_DATABASE_USER: str = "minder"
    MARKETPLACE_DATABASE_NAME: str = "minder_marketplace"
    # Use platform-standard POSTGRES_PASSWORD (set via env)
    POSTGRES_PASSWORD: str  # Required: must be set via environment variable

    @field_validator("POSTGRES_PASSWORD")
    @classmethod
    def check_postgres_password(cls, v: str) -> str:
        if not v:
            raise ValueError("POSTGRES_PASSWORD must be set via environment variable")
        return v

    # Redis
    MARKETPLACE_REDIS_HOST: str = "minder-redis"
    MARKETPLACE_REDIS_PORT: int = 6379
    MARKETPLACE_REDIS_DB: int = 1  # Use separate DB for marketplace
    # Use platform-standard REDIS_PASSWORD (set via env)
    REDIS_PASSWORD: str  # Required: must be set via environment variable

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def check_redis_password(cls, v: str) -> str:
        if not v:
            raise ValueError("REDIS_PASSWORD must be set via environment variable")
        return v

    # Security — HMAC secret for license-key generation. Falls back to JWT_SECRET
    # (a required, auto-generated secret) when unset, so there is no weak hardcoded
    # default. Set explicitly only to decouple license keys from JWT_SECRET.
    LICENSE_SECRET: Optional[str] = None
    JWT_SECRET: str  # Required: must be set via environment variable
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    @field_validator("JWT_SECRET")
    @classmethod
    def check_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError("JWT_SECRET must be set via environment variable")
        return v

    # Plugin Registry integration
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"

    # CORS — comma-separated origins; when unset, falls back to the dev localhost
    # list in main. Set to a real origin list in production.
    CORS_ALLOWED_ORIGINS: Optional[str] = None

    # Neo4j Graph Database - use platform-standard NEO4J_AUTH (format: neo4j/password)
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_AUTH: (
        str  # Required: must be set via environment variable (format: neo4j/password)
    )

    @field_validator("NEO4J_AUTH")
    @classmethod
    def check_neo4j_auth(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "NEO4J_AUTH must be set via environment variable (format: neo4j/password)"
            )
        return v

    # Application
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    # Marketplace settings
    MAX_PLUGINS_PER_USER: int = 100
    MAX_UPLOAD_SIZE_MB: int = 100

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60


# Global settings instance
settings = MarketplaceSettings()

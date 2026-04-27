# services/marketplace/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class MarketplaceSettings(BaseSettings):
    """Marketplace service settings"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    # Service settings
    MARKETPLACE_HOST: str = "0.0.0.0"
    MARKETPLACE_PORT: int = 8002

    # Database
    MARKETPLACE_DATABASE_HOST: str = "minder-postgres"
    MARKETPLACE_DATABASE_PORT: int = 5432
    MARKETPLACE_DATABASE_USER: str = "minder"
    MARKETPLACE_DATABASE_PASSWORD: str = "dev_password_change_me"
    MARKETPLACE_DATABASE_NAME: str = "minder_marketplace"

    # Redis
    MARKETPLACE_REDIS_HOST: str = "minder-redis"
    MARKETPLACE_REDIS_PORT: int = 6379
    MARKETPLACE_REDIS_PASSWORD: str = "dev_password_change_me"
    MARKETPLACE_REDIS_DB: int = 1  # Use separate DB for marketplace

    # Security
    LICENSE_SECRET: str = "dev_license_secret_change_me_in_production"
    JWT_SECRET: str = "dev_jwt_secret_change_me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 60

    # Plugin Registry integration
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"

    # Neo4j Graph Database
    NEO4J_URI: str = "bolt://neo4j:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_test_password_change_me"

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

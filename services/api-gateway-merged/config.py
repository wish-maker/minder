"""
Minder API Gateway & Plugin Registry - Configuration
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""

    # Database
    database_url: str = "postgresql://minder:minder@postgres:5432/minder"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # JWT
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # API Gateway
    api_title: str = "Minder API Gateway & Plugin Registry"
    api_version: str = "2.1.0"
    environment: str = "production"

    # Plugin Registry
    plugin_registry_path: str = "/plugins"
    plugin_security_level: str = "moderate"

    # CORS
    cors_origins: list = ["http://localhost:3000", "http://localhost:8080"]

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

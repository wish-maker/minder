"""
API Gateway Configuration
Loads settings from environment variables with sensible defaults
"""

import sys

# MinderBaseSettings + shared packages live under /app/src (#265).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.config import MinderBaseSettings  # noqa: E402


class Settings(MinderBaseSettings):
    """API Gateway Settings"""

    # Service Discovery (service-specific; not on the shared base)
    MODEL_MANAGEMENT_URL: str = "http://model-management:8005"

    # Database
    DB_NAME: str = "minder"

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 100

    # Application
    API_VERSION: str = "v1"
    APP_VERSION: str = "1.0.0"

    # CORS Configuration — api-gateway defaults to allow-all, unlike the base's
    # Optional[None] default (comma-separated list, e.g. "http://localhost:3000").
    CORS_ALLOWED_ORIGINS: str = "*"

    # Phase Configuration (for health check)
    MINDER_PHASE: int = 1  # Current deployment phase


# Global settings instance
settings = Settings()

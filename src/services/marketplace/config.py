# services/marketplace/config.py
import sys
from typing import Optional

from pydantic import field_validator

# MinderBaseSettings + shared packages live under /app/src (#265).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.config import MinderBaseSettings  # noqa: E402


class MarketplaceSettings(MinderBaseSettings):
    """Marketplace service settings"""

    # Service settings
    MARKETPLACE_HOST: str = "0.0.0.0"  # nosec B104 — containers bind all interfaces
    MARKETPLACE_PORT: int = 8002

    # Database
    DB_HOST: str = "minder-postgres"
    DB_NAME: str = "minder_marketplace"

    # Redis — marketplace uses a separate Redis DB index from the platform default.
    REDIS_HOST: str = "minder-redis"
    REDIS_DB: int = 1

    # Security — HMAC secret for license-key generation. Falls back to JWT_SECRET
    # (a required, auto-generated secret) when unset, so there is no weak hardcoded
    # default. Set explicitly only to decouple license keys from JWT_SECRET.
    LICENSE_SECRET: Optional[str] = None

    # Plugin Registry integration
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"

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

    # Marketplace settings
    MAX_PLUGINS_PER_USER: int = 100
    MAX_UPLOAD_SIZE_MB: int = 100

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60


# Global settings instance
settings = MarketplaceSettings()

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

    # OIDC login against Authelia (#<issue>) -- api-gateway is a confidential
    # OIDC client; a successful Authelia login still mints Minder's own
    # existing JWT shape (see routes/auth.py's oidc_callback), so nothing
    # downstream that already trusts a Minder JWT needs to change.
    AUTHELIA_ISSUER_URL: str = "https://authelia.minder.local"
    # api-gateway's own server-to-server calls (discovery/token/JWKS) go
    # straight to the container on the docker network -- authelia.minder.local
    # only resolves via Traefik, which isn't reachable from inside the network
    # api-gateway itself is on. The Host header is still overridden to the
    # public issuer name on every such call (see core/oidc.py) so Authelia's
    # own responses (issuer, token/jwks URLs) stay self-consistent with what
    # the browser and the ID token's iss claim both use.
    AUTHELIA_INTERNAL_URL: str = "http://minder-authelia:9091"
    MINDER_OIDC_CLIENT_ID: str = "minder-client"
    MINDER_OIDC_CLIENT_SECRET: str = ""
    MINDER_OIDC_REDIRECT_URI: str = "https://api.minder.local/v1/auth/oidc/callback"
    MINDER_CLIENT_BASE_URL: str = "https://client.minder.local"

    # Proxy request body cap (routes/proxy.py's proxy_request) -- every write
    # to a proxied service (rag-pipeline ingestion, tts-stt audio, model pulls,
    # ...) is fully buffered into memory here before the request even reaches
    # the downstream service's own limit (e.g. rag-pipeline's own 50MB
    # MAX_UPLOAD_SIZE_MB only runs *after* the gateway already buffered the
    # whole thing). Without a cap here, a large/malicious upload can exhaust
    # gateway memory regardless of what any downstream service enforces. Set
    # above every real downstream limit (marketplace's own MAX_UPLOAD_SIZE_MB
    # is the largest at 100MB) so legitimate traffic is never rejected here.
    MAX_PROXY_BODY_SIZE_MB: int = 150


# Global settings instance
settings = Settings()

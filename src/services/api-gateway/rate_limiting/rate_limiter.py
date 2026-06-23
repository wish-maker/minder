"""
Redis-based Rate Limiting Middleware for FastAPI

Provides production-grade rate limiting with sliding window algorithm,
Redis backend, and Prometheus metrics integration.
"""

import json
import logging
import time
from typing import Callable, Dict, Optional, Tuple

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram
from redis import Redis

logger = logging.getLogger(__name__)

# ============================================================================
# Prometheus Metrics
# ============================================================================

rate_limit_requests_total = Counter(
    "rate_limit_requests_total",
    "Total rate limit checks",
    ["endpoint", "status"],  # status: allowed, blocked, error
)

rate_limit_response_time_seconds = Histogram(
    "rate_limit_response_time_seconds", "Rate limiting check duration", ["endpoint"]
)

rate_limit_blocked_total = Counter(
    "rate_limit_blocked_total",
    "Total blocked requests by rate limit",
    ["endpoint", "limit_type"],
)

# ============================================================================
# Rate Limiter Configuration
# ============================================================================

# Rate limit tiers (requests per minute)
RATE_LIMITS = {
    "default": 60,  # 60 requests per minute
    "strict": 30,  # 30 requests per minute
    "lenient": 120,  # 120 requests per minute
    "bypass": None,  # No rate limiting
}

# Endpoint-specific rate limits
ENDPOINT_LIMITS = {
    "/health": "bypass",
    "/metrics": "bypass",
    "/api/agent/": "lenient",  # Agent endpoints
    "/api/plugins/": "default",  # Plugin endpoints
    "/api/knowledge-base/": "strict",  # Knowledge base endpoints
}

# Sliding window size (seconds)
WINDOW_SIZE = 60

# ============================================================================
# Rate Limiter Implementation
# ============================================================================


class RedisRateLimiter:
    """
    Redis-based rate limiter using sliding window algorithm.

    Features:
    - Sliding window for accurate rate limiting
    - Redis backend for distributed limiting
    - Configurable rate limits per endpoint
    - Automatic cleanup of expired windows
    - Prometheus metrics integration
    """

    def __init__(
        self,
        redis_client: Redis,
        default_limit: int = 60,
        window_size: int = 60,
        key_prefix: str = "rate_limit",
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client instance
            default_limit: Default requests per window
            window_size: Time window in seconds
            key_prefix: Redis key prefix for rate limit data
        """
        self.redis = redis_client
        self.default_limit = default_limit
        self.window_size = window_size
        self.key_prefix = key_prefix

        # Test Redis connection
        try:
            self.redis.ping()
            logger.info("✅ Rate limiter initialized with Redis backend")
        except Exception as e:
            logger.error(f"❌ Rate limiter Redis connection failed: {e}")
            raise

    def _get_key(self, identifier: str, endpoint: str) -> str:
        """Generate Redis key for rate limiting."""
        return f"{self.key_prefix}:{identifier}:{endpoint}"

    def _get_window_key(self, key: str, window_timestamp: int) -> str:
        """Generate window-specific key."""
        return f"{key}:window:{window_timestamp}"

    def check_rate_limit(
        self, identifier: str, endpoint: str, limit: Optional[int] = None
    ) -> Tuple[bool, Dict]:
        """
        Check if request should be rate limited.

        Args:
            identifier: Unique identifier (IP address, user ID, etc.)
            endpoint: API endpoint path
            limit: Custom rate limit (overrides default)

        Returns:
            Tuple of (allowed: bool, info: dict)
        """
        start_time = time.time()

        try:
            # Use custom limit or default
            current_limit = limit if limit is not None else self.default_limit

            # No limiting if bypass
            if current_limit is None:
                return True, {"limit": None, "remaining": None, "reset": None}

            # Current window timestamp
            current_window = int(time.time() // self.window_size)
            key = self._get_key(identifier, endpoint)
            window_key = self._get_window_key(key, current_window)

            # Use Redis pipeline for atomic operations
            pipe = self.redis.pipeline()

            # Increment request count for current window
            pipe.incr(window_key)

            # Set expiration for current window
            pipe.expire(window_key, self.window_size * 2)

            # Get current count
            pipe.get(window_key)

            # Execute pipeline
            results = pipe.execute()
            current_count = int(results[2])

            # Calculate remaining requests and reset time
            remaining = max(0, current_limit - current_count)
            reset_time = (current_window + 1) * self.window_size

            # Check if rate limited
            is_allowed = current_count <= current_limit

            # Update Prometheus metrics
            endpoint_safe = endpoint.replace("/", "_").strip("_") or "root"
            rate_limit_requests_total.labels(
                endpoint=endpoint_safe, status="allowed" if is_allowed else "blocked"
            ).inc()

            if not is_allowed:
                rate_limit_blocked_total.labels(
                    endpoint=endpoint_safe, limit_type="default"
                ).inc()

            # Record response time
            rate_limit_response_time_seconds.labels(endpoint=endpoint_safe).observe(
                time.time() - start_time
            )

            info = {
                "limit": current_limit,
                "remaining": remaining,
                "reset": reset_time,
                "current": current_count,
            }

            return is_allowed, info

        except Exception as e:
            logger.error(f"❌ Rate limit check error: {e}")
            # On error, allow request (fail open)
            rate_limit_requests_total.labels(
                endpoint=endpoint.replace("/", "_").strip("_") or "root", status="error"
            ).inc()
            return True, {"error": str(e)}


class RateLimitMiddleware:
    """
    FastAPI middleware for rate limiting.

    Automatically applies rate limiting to all endpoints based on
    configured limits and client identification.
    """

    def __init__(
        self,
        redis_client: Redis,
        rate_limiter: Optional[RedisRateLimiter] = None,
        identifier_func: Optional[Callable] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            redis_client: Redis client instance
            rate_limiter: Custom rate limiter (creates default if None)
            identifier_func: Function to extract identifier from request
        """
        self.rate_limiter = rate_limiter or RedisRateLimiter(redis_client)
        self.identifier_func = identifier_func or self._default_identifier

        logger.info("✅ Rate limit middleware initialized")

    def _default_identifier(self, request: Request) -> str:
        """
        Extract identifier from request (default: IP address).

        Args:
            request: FastAPI request object

        Returns:
            Identifier string (IP address or fallback)
        """
        # Try to get real IP from X-Forwarded-For header
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # X-Forwarded-For can contain multiple IPs, take the first one
            return forwarded.split(",")[0].strip()

        # Fallback to remote address
        if request.client and request.client.host:
            return request.client.host

        # Final fallback
        return "unknown"

    def _get_endpoint_limit(self, endpoint: str) -> Optional[int]:
        """Get rate limit for specific endpoint."""
        # Check exact match first
        if endpoint in ENDPOINT_LIMITS:
            return RATE_LIMITS.get(ENDPOINT_LIMITS[endpoint])

        # Check prefix match
        for prefix, tier in ENDPOINT_LIMITS.items():
            if endpoint.startswith(prefix):
                return RATE_LIMITS.get(tier)

        # Use default
        return RATE_LIMITS.get("default")

    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """
        Middleware handler for rate limiting.

        Args:
            request: FastAPI request object
            call_next: Next middleware/handler in chain

        Returns:
            FastAPI response (or rate limit error)
        """
        # Get endpoint path
        endpoint = request.url.path

        # Get rate limit for this endpoint
        limit = self._get_endpoint_limit(endpoint)

        # Skip rate limiting if bypass
        if limit is None:
            return await call_next(request)

        # Get client identifier
        identifier = self._identifier_func(request)

        # Check rate limit
        is_allowed, info = self.rate_limiter.check_rate_limit(
            identifier=identifier, endpoint=endpoint, limit=limit
        )

        # Handle rate limit exceeded
        if not is_allowed:
            logger.warning(f"⚠️ Rate limit exceeded for {identifier} on {endpoint}")
            return Response(
                content=json.dumps(
                    {
                        "error": "Rate limit exceeded",
                        "limit": info.get("limit"),
                        "reset": info.get("reset"),
                    }
                ),
                status_code=429,
                media_type="application/json",
                headers={
                    "X-RateLimit-Limit": str(info.get("limit")),
                    "X-RateLimit-Remaining": str(info.get("remaining")),
                    "X-RateLimit-Reset": str(info.get("reset")),
                    "Retry-After": str(info.get("reset") - int(time.time())),
                },
            )

        # Add rate limit headers to allowed requests
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info.get("limit"))
        response.headers["X-RateLimit-Remaining"] = str(info.get("remaining"))
        response.headers["X-RateLimit-Reset"] = str(info.get("reset"))

        return response


# ============================================================================
# FastAPI Integration
# ============================================================================


def add_rate_limiting(
    app: FastAPI, redis_client: Redis, identifier_func: Optional[Callable] = None
):
    """
    Add rate limiting middleware to FastAPI application.

    Args:
        app: FastAPI application instance
        redis_client: Redis client instance
        identifier_func: Optional custom identifier function

    Example:
        ```python
        from fastapi import FastAPI
        from redis import Redis

        app = FastAPI()
        redis_client = Redis(host="redis", port=6379, db=0)

        add_rate_limiting(app, redis_client)
        ```
    """
    middleware = RateLimitMiddleware(redis_client, identifier_func=identifier_func)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
        return await middleware(request, call_next)

    logger.info("✅ Rate limiting middleware added to FastAPI application")


# ============================================================================
# Standalone Usage
# ============================================================================

if __name__ == "__main__":
    # Test rate limiter
    import redis

    redis_client = redis.Redis(host="localhost", port=6379, db=0)
    rate_limiter = RedisRateLimiter(redis_client)

    # Test rate limiting
    identifier = "test_client"
    endpoint = "/api/test"

    for i in range(65):  # Test default limit of 60
        is_allowed, info = rate_limiter.check_rate_limit(identifier, endpoint)
        print(
            f"Request {i+1}: Allowed={is_allowed}, Count={info.get('current')}, Remaining={info.get('remaining')}"
        )

"""
Rate limiting middleware for Minder services.
Redis-based rate limiting with configurable limits.
"""

import asyncio
import json
import logging
import time
from functools import wraps
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, Response
from redis.asyncio import Redis

logger = logging.getLogger("minder.rate_limiter")


class RateLimiter:
    """Redis-based rate limiter"""

    def __init__(self, redis_client: Redis, default_limit: int = 100, default_window: int = 60):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client instance
            default_limit: Default request limit per window
            default_window: Default time window in seconds
        """
        self.redis = redis_client
        self.default_limit = default_limit
        self.default_window = default_window

    async def is_allowed(
        self, key: str, limit: Optional[int] = None, window: Optional[int] = None
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if request is allowed based on rate limit.

        Args:
            key: Unique key for rate limiting (e.g., user_id, IP)
            limit: Request limit (uses default if None)
            window: Time window in seconds (uses default if None)

        Returns:
            Tuple of (is_allowed, info dict with remaining, reset_time)
        """
        limit = limit or self.default_limit
        window = window or self.default_window

        current_time = int(time.time())
        window_start = current_time - window

        # Redis key for tracking requests
        redis_key = f"rate_limit:{key}"

        try:
            # Use Redis pipeline for atomic operations
            async with self.redis.pipeline() as pipe:
                # Remove old entries outside the window
                pipe.zremrangebyscore(redis_key, 0, window_start)

                # Count current requests
                pipe.zcard(redis_key)

                # Add current request
                pipe.zadd(redis_key, {str(current_time): current_time})

                # Set expiration
                pipe.expire(redis_key, window)

                results = await pipe.execute()

                current_count = results[1]

                # Calculate info
                remaining = max(0, limit - current_count)
                reset_time = window_start + window

                is_allowed = current_count < limit

                info = {
                    "limit": limit,
                    "window": window,
                    "remaining": remaining,
                    "reset_time": reset_time,
                    "current_count": current_count,
                }

                return is_allowed, info

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Fail open: allow request if Redis is down
            return True, {"limit": limit, "remaining": limit, "window": window}

    async def get_rate_limit_info(self, key: str) -> Dict[str, Any]:
        """
        Get current rate limit info.

        Args:
            key: Unique key for rate limiting

        Returns:
            Dictionary with rate limit info
        """
        redis_key = f"rate_limit:{key}"

        try:
            current_time = int(time.time())
            window_start = current_time - self.default_window

            current_count = await self.redis.zcount(redis_key, window_start, current_time)
            remaining = max(0, self.default_limit - current_count)
            reset_time = current_time + self.default_window - (current_time % self.default_window)

            return {
                "limit": self.default_limit,
                "window": self.default_window,
                "remaining": remaining,
                "reset_time": reset_time,
                "current_count": current_count,
            }
        except Exception as e:
            logger.error(f"Failed to get rate limit info: {e}")
            return {}


def get_client_identifier(request: Request) -> str:
    """
    Get client identifier from request.

    Args:
        request: FastAPI request

    Returns:
        Client identifier (user ID or IP)
    """
    # Try to get user ID from authentication
    if hasattr(request.state, "user") and request.state.user:
        return f"user:{request.state.user.get('id', 'unknown')}"

    # Fallback to IP address
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


async def add_rate_limit_headers(response: Response, info: Dict[str, Any]) -> None:
    """
    Add rate limit headers to response.

    Args:
        response: FastAPI response
        info: Rate limit info dictionary
    """
    response.headers["X-RateLimit-Limit"] = str(info.get("limit", ""))
    response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", ""))
    response.headers["X-RateLimit-Reset"] = str(info.get("reset_time", ""))
    response.headers["X-RateLimit-Window"] = str(info.get("window", ""))


def rate_limit(limit: int = 100, window: int = 60, key_func: Optional[callable] = None):
    """
    Decorator for rate limiting API endpoints.

    Args:
        limit: Request limit per window
        window: Time window in seconds
        key_func: Custom function to generate rate limit key

    Example:
        @rate_limit(limit=10, window=60)
        async def my_endpoint(request: Request):
            return {"message": "Hello"}
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = args[0] if args else None

            if not isinstance(request, Request):
                # Not a request handler, just call the function
                return await func(*args, **kwargs)

            # Get or create rate limiter from app state
            if not hasattr(request.app.state, "rate_limiter"):
                logger.warning("Rate limiter not configured, skipping rate limit check")
                return await func(*args, **kwargs)

            rate_limiter: RateLimiter = request.app.state.rate_limiter

            # Generate rate limit key
            if key_func:
                key = key_func(request)
            else:
                key = get_client_identifier(request)

            # Check rate limit
            is_allowed, info = await rate_limiter.is_allowed(key, limit, window)

            # Create response
            response_obj = None
            try:
                result = await func(*args, **kwargs)
                response_obj = result if isinstance(result, Response) else None
            except Exception as e:
                raise

            # Get response object if not already created
            if response_obj is None:
                # This is a normal return value, need to get response from context
                # For simplicity, we'll skip adding headers here
                # In production, you'd get the response from the context
                pass
            else:
                await add_rate_limit_headers(response_obj, info)

            if not is_allowed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Try again after {info.get('reset_time', 0)}",
                    headers={
                        "X-RateLimit-Limit": str(info.get("limit", "")),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(info.get("reset_time", "")),
                        "X-RateLimit-Window": str(info.get("window", "")),
                        "Retry-After": str(int(info.get("reset_time", 0) - int(time.time()))),
                    },
                )

            return result

        return wrapper

    return decorator


async def setup_rate_limiter(
    redis_client: Redis, default_limit: int = 100, default_window: int = 60
) -> RateLimiter:
    """
    Setup rate limiter and attach to FastAPI app state.

    Args:
        redis_client: Redis client instance
        default_limit: Default request limit
        default_window: Default time window

    Returns:
        RateLimiter instance

    Example:
        rate_limiter = await setup_rate_limiter(redis, limit=100, window=60)
        app.state.rate_limiter = rate_limiter
    """
    rate_limiter = RateLimiter(redis_client, default_limit, default_window)
    logger.info(f"Rate limiter initialized: {default_limit} requests per {default_window} seconds")
    return rate_limiter


# Rate limit presets for different use cases


class RateLimitPresets:
    """Common rate limit configurations"""

    # Public endpoints - more restrictive
    PUBLIC_API = {"limit": 10, "window": 60}  # 10 requests/minute
    PUBLIC_SEARCH = {"limit": 5, "window": 60}  # 5 searches/minute

    # Authenticated users - moderate
    USER_API = {"limit": 100, "window": 60}  # 100 requests/minute
    USER_SEARCH = {"limit": 30, "window": 60}  # 30 searches/minute

    # Admin users - generous
    ADMIN_API = {"limit": 500, "window": 60}  # 500 requests/minute

    # Heavy operations - very restrictive
    HEAVY_OPERATION = {"limit": 2, "window": 60}  # 2 operations/minute

    # Plugin operations
    PLUGIN_INSTALL = {"limit": 5, "window": 300}  # 5 installs/5 minutes
    PLUGIN_COLLECT = {"limit": 30, "window": 60}  # 30 collections/minute


def get_rate_limit_for_operation(operation: str) -> Dict[str, int]:
    """
    Get rate limit configuration for operation type.

    Args:
        operation: Operation type (e.g., 'public', 'user', 'admin')

    Returns:
        Dictionary with limit and window
    """
    presets = {
        "public": RateLimitPresets.PUBLIC_API,
        "public_search": RateLimitPresets.PUBLIC_SEARCH,
        "user": RateLimitPresets.USER_API,
        "user_search": RateLimitPresets.USER_SEARCH,
        "admin": RateLimitPresets.ADMIN_API,
        "heavy": RateLimitPresets.HEAVY_OPERATION,
        "plugin_install": RateLimitPresets.PLUGIN_INSTALL,
        "plugin_collect": RateLimitPresets.PLUGIN_COLLECT,
    }

    return presets.get(operation, RateLimitPresets.PUBLIC_API)


class IPWhitelist:
    """IP whitelist manager"""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.whitelist_key = "ip_whitelist"

    async def add_ip(self, ip: str, reason: str = "") -> bool:
        """Add IP to whitelist"""
        try:
            await self.redis.sadd(self.whitelist_key, ip)
            logger.info(f"Added IP to whitelist: {ip} ({reason})")
            return True
        except Exception as e:
            logger.error(f"Failed to add IP to whitelist: {e}")
            return False

    async def remove_ip(self, ip: str) -> bool:
        """Remove IP from whitelist"""
        try:
            await self.redis.srem(self.whitelist_key, ip)
            logger.info(f"Removed IP from whitelist: {ip}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove IP from whitelist: {e}")
            return False

    async def is_whitelisted(self, ip: str) -> bool:
        """Check if IP is whitelisted"""
        try:
            return await self.redis.sismember(self.whitelist_key, ip)
        except Exception as e:
            logger.error(f"Failed to check IP whitelist: {e}")
            return False


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""

    def __init__(self, limit: int, window: int, reset_time: int):
        self.limit = limit
        self.window = window
        self.reset_time = reset_time
        super().__init__(f"Rate limit exceeded: {limit} requests per {window} seconds")

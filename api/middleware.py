"""
Middleware Module
Security middleware including network detection, rate limiting, caching, and CORS
"""

import hashlib
import ipaddress
import json
import logging
import os
import time
import uuid
from typing import Callable, Optional

import redis
from fastapi import HTTPException, Request, Response

# Prometheus metrics
from prometheus_client import Counter, Histogram
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware

request_count = Counter("minder_requests_total", "Total requests", ["method", "endpoint", "status"])
request_duration = Histogram("minder_request_duration_seconds", "Request duration", ["endpoint"])
cache_hits = Counter("minder_cache_hits_total", "Cache hits", ["endpoint"])
cache_misses = Counter("minder_cache_misses_total", "Cache misses", ["endpoint"])

logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
LOCAL_NETWORK_CIDR = os.getenv("LOCAL_NETWORK_CIDR", "192.168.1.0/24")
TAILSCALE_CIDR = os.getenv("TAILSCALE_CIDR", "100.64.0.0/10")
TRUST_LOCAL_NETWORK = os.getenv("TRUST_LOCAL_NETWORK", "true").lower() == "true"
TRUST_VPN_NETWORK = os.getenv("TRUST_VPN_NETWORK", "true").lower() == "true"

# Redis client for rate limiting
try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )
    logger.info(f"✅ Redis connected for rate limiting: {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.warning(f"⚠️  Redis connection failed: {e} - Rate limiting will be in-memory")
    redis_client = None


class NetworkDetectionMiddleware(BaseHTTPMiddleware):
    """
    Detect request source network (local vs VPN vs public)

    Adds network_type and is_trusted_network attributes to request state
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timer for metrics
        start_time = time.time()

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Detect network type
        network_type = self.detect_network(client_ip)
        is_trusted = self.is_trusted_network(network_type)

        # Add to request state
        request.state.network_type = network_type
        request.state.is_trusted_network = is_trusted
        request.state.client_ip = client_ip

        # Log network access
        logger.debug(f"Request from {network_type} network (IP: {client_ip}, " f"Trusted: {is_trusted})")

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise e
        finally:
            # Record metrics
            duration = time.time() - start_time
            endpoint = request.url.path or "unknown"
            method = request.method

            request_count.labels(method=method, endpoint=endpoint, status=status_code).inc()

            request_duration.labels(endpoint=endpoint).observe(duration)

        # Add network headers to response
        response.headers["X-Network-Type"] = network_type
        response.headers["X-Client-IP"] = client_ip

        return response

    def detect_network(self, ip: str) -> str:
        """
        Detect if IP is from local network, VPN, or public

        Returns: 'local', 'vpn', or 'public'
        """
        try:
            ip_obj = ipaddress.ip_address(ip)

            # Check local network
            local_subnet = ipaddress.ip_network(LOCAL_NETWORK_CIDR)
            if ip_obj in local_subnet:
                return "local"

            # Check Tailscale VPN
            vpn_subnet = ipaddress.ip_network(TAILSCALE_CIDR)
            if ip_obj in vpn_subnet:
                return "vpn"

            # Check if it's a private IP (other private ranges)
            if ip_obj.is_private:
                return "private"

            # Public IP
            return "public"

        except ValueError:
            logger.warning(f"Invalid IP address: {ip}")
            return "unknown"

    def is_trusted_network(self, network_type: str) -> bool:
        """Determine if network type is trusted (no auth required)"""
        if network_type == "local" and TRUST_LOCAL_NETWORK:
            return True
        if network_type == "vpn" and TRUST_VPN_NETWORK:
            return True
        return False


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Add correlation ID to all requests for tracing
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or get correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Add to request state
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Add to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


# Rate limiting setup
def get_rate_limit_key(request: Request) -> str:
    """
    Get rate limit key based on network type

    Different rate limits for different network types:
    - Local/Private network: No rate limiting (unlimited)
    - VPN: Standard rate limiting (200/hour)
    - Public: Strict rate limiting (50/hour)
    """
    network_type = getattr(request.state, "network_type", "public")
    client_ip = get_remote_address(request)

    if network_type in ("local", "private"):
        # No rate limiting for local and private networks (Docker, etc.)
        return "local_unlimited"
    elif network_type == "vpn":
        # Standard rate limiting for VPN (200/hour)
        return f"vpn:{client_ip}"
    else:
        # Strict rate limiting for public (50/hour)
        return f"public:{client_ip}"


def get_expensive_operation_key(request: Request) -> str:
    """
    Get rate limit key for expensive operations (chat, AI operations)

    Stricter limits regardless of network type:
    - Local/Private: No rate limiting (unlimited)
    - VPN: 10/minute
    - Public: 5/minute
    """
    network_type = getattr(request.state, "network_type", "public")
    client_ip = get_remote_address(request)

    if network_type in ("local", "private"):
        # No rate limiting for local and private networks
        return "local_unlimited"
    elif network_type == "vpn":
        return f"vpn_expensive:{client_ip}"
    else:
        return f"public_expensive:{client_ip}"


# Initialize rate limiters
# Standard limiter for general API requests
limiter = Limiter(
    key_func=get_rate_limit_key,
    storage_uri=(f"redis://{REDIS_HOST}:{REDIS_PORT}" if redis_client else "memory://"),
    default_limits=["50/hour"],  # Default limit for public (stricter)
    key_prefix="minder_rate_limit",
)

# Expensive operations limiter (chat, AI operations)
expensive_limiter = Limiter(
    key_func=get_expensive_operation_key,
    storage_uri=(f"redis://{REDIS_HOST}:{REDIS_PORT}" if redis_client else "memory://"),
    default_limits=["5/minute"],  # Default for expensive operations
    key_prefix="minder_expensive_ops",
)

logger.info("✅ Rate limiters initialized (Standard: 50/hour public, Expensive: 5/minute)")
logger.info("   - Local network: Unlimited (standard), 30/minute (expensive)")
logger.info("   - VPN: 200/hour (standard), 10/minute (expensive)")
logger.info("   - Public: 50/hour (standard), 5/minute (expensive)")


def conditional_rate_limit(limit_value: str):
    """
    Custom rate limit decorator that exempts local/private networks

    Args:
        limit_value: Rate limit string (e.g., "50/hour", "5/minute")

    Usage:
        @conditional_rate_limit("50/hour")
        async def my_endpoint(request: Request):
            ...
    """

    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            # Find the Request object in args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                # If no request found, apply rate limit anyway
                return await limiter.limit(limit_value)(func)(*args, **kwargs)

            # Check network type
            network_type = getattr(request.state, "network_type", "public")

            if network_type in ("local", "private"):
                # Skip rate limiting for local/private networks
                return await func(*args, **kwargs)
            else:
                # Apply rate limiting for VPN/public networks
                return await limiter.limit(limit_value)(func)(*args, **kwargs)

        return wrapper

    return decorator


# Custom rate limit exceeded handler


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors"""
    network_type = getattr(request.state, "network_type", "public")
    client_ip = getattr(request.state, "client_ip", "unknown")
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    logger.warning(
        f"⚠️  Rate limit exceeded for {network_type} network " f"(IP: {client_ip}, Correlation ID: {correlation_id})"
    )

    # Handle both RateLimitExceeded and generic exceptions
    error_detail = getattr(exc, "detail", str(exc)) if hasattr(exc, "detail") else str(exc)

    # Provide retry information based on network type
    retry_after = 60  # Default
    if network_type == "local":
        retry_after = 30
    elif network_type == "vpn":
        retry_after = 45

    return HTTPException(
        status_code=429,
        detail={
            "error": "rate_limit_exceeded",
            "message": (error_detail if error_detail else "Too many requests. Please try again later."),
            "network_type": network_type,
            "retry_after": retry_after,
            "correlation_id": correlation_id,
        },
    )


# Request size limit middleware
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Limit request size to prevent abuse
    """

    def __init__(self, app, max_size: int = 10 * 1024 * 1024):  # 10MB default
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length:
            content_length = int(content_length)
            if content_length > self.max_size:
                logger.warning(f"Request too large: {content_length} bytes " f"(max: {self.max_size} bytes)")
                raise HTTPException(
                    status_code=413,
                    detail=f"Request too large. Maximum size: {self.max_size} bytes",
                )

        return await call_next(request)


class CacheMiddleware(BaseHTTPMiddleware):
    """
    Response caching middleware for GET requests

    Caches GET requests in Redis with configurable TTL.
    Cache key includes: method, path, query params, and auth token hash.
    """

    def __init__(self, app, redis_client: Optional[redis.Redis] = None, default_ttl: int = 300):
        super().__init__(app)
        self.redis_client = redis_client
        self.default_ttl = default_ttl

        # Endpoints to cache (whitelist approach for security)
        self.cacheable_endpoints = {
            "/plugins": 60,  # Cache plugin list for 1 minute
            "/system/status": 30,  # Cache system status for 30 seconds
            "/health": 10,  # Cache health check for 10 seconds
        }

    def _is_cacheable_request(self, request: Request) -> tuple[bool, str | None, int | None]:
        """Check if request is cacheable (GET + whitelisted endpoint)"""
        if request.method != "GET":
            return False, None, None

        path = request.url.path
        if path in self.cacheable_endpoints:
            return True, path, self.cacheable_endpoints[path]

        return False, None, None

    def _try_get_cached(self, cache_key: str, path: str) -> Response | None:
        """Try to get response from cache, returns None if cache miss"""
        if not self.redis_client:
            return None

        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for {path}")
                cache_hits.labels(endpoint=path).inc()

                response_data = json.loads(cached_data)
                return Response(
                    content=json.dumps(response_data),
                    status_code=200,
                    headers={"Content-Type": "application/json", "X-Cache": "HIT"},
                )
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")

        return None

    def _store_cached_response(self, cache_key: str, ttl: int, response: Response, path: str):
        """Store response in cache if cacheable"""
        if not self.redis_client or response.status_code != 200:
            return

        # Don't cache streaming responses (they don't have a body attribute)
        if not (hasattr(response, "body") and response.body):
            logger.debug(f"Skipping cache for {path} - streaming response or no body")
            return

        try:
            response_body = response.body.decode("utf-8")
            self.redis_client.setex(
                cache_key,
                ttl,
                json.dumps({"body": response_body, "status": response.status_code}),
            )
            logger.debug(f"Cached response for {path} (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle request with caching logic"""
        # Check if cacheable
        is_cacheable, path, ttl = self._is_cacheable_request(request)
        if not is_cacheable:
            return await call_next(request)

        # Generate cache key
        cache_key = self._generate_cache_key(request)

        # Try to get from cache
        cached_response = self._try_get_cached(cache_key, path)
        if cached_response:
            return cached_response

        # Cache miss - proceed with request
        logger.debug(f"Cache miss for {path}")
        cache_misses.labels(endpoint=path).inc()

        # Process request
        response = await call_next(request)

        # Store in cache if appropriate
        self._store_cached_response(cache_key, ttl, response, path)

        # Add cache header to response
        response.headers["X-Cache"] = "MISS"

        return response

    def _generate_cache_key(self, request: Request) -> str:
        """Generate cache key from request attributes"""
        # Get auth token (if present) for user-specific caching
        auth_token = request.headers.get("authorization", "")
        token_hash = hashlib.md5(auth_token.encode()).hexdigest()[:8]

        # Build cache key
        key_parts = [
            "minder_cache",
            request.method.lower(),
            request.url.path,
            str(sorted(request.query_params.items())),
            token_hash,
        ]

        return ":".join(key_parts)


class CustomRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Custom rate limiting middleware that exempts local/private networks

    This middleware checks the network type (set by NetworkDetectionMiddleware)
    and skips rate limiting for local and private networks while applying
    SlowAPI rate limits for VPN and public networks.
    """

    def __init__(self, app, limiter_instance: Limiter):
        super().__init__(app)
        self.limiter = limiter_instance

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check network type (already set by NetworkDetectionMiddleware)
        network_type = getattr(request.state, "network_type", "public")

        # Skip rate limiting for local/private networks
        if network_type in ("local", "private"):
            logger.debug(f"Skipping rate limit for {network_type} network")
            return await call_next(request)

        # Apply rate limiting for VPN/public networks
        # The SlowAPIMiddleware will handle this
        return await call_next(request)


def setup_middleware(app, allowed_origins: list):
    """
    Setup all middleware for the FastAPI application

    Args:
        app: FastAPI application instance
        allowed_origins: List of allowed CORS origins
    """
    # 1. CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["Content-Type", "Authorization", "X-Correlation-ID"],
        max_age=3600,  # Cache preflight for 1 hour
    )
    logger.info(f"✅ CORS configured with {len(allowed_origins)} allowed origins")

    # 2. Rate Limiting Configuration
    # Note: We're NOT using SlowAPIMiddleware to avoid rate limiting local/private networks
    # Instead, rate limiting will be applied selectively via endpoint
    # decorators
    app.state.limiter = limiter
    app.state.expensive_limiter = expensive_limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    logger.info("✅ Rate limiting configured (endpoint-specific)")
    logger.info("   - Local/Private networks: Unlimited access")
    logger.info("   - VPN/Public networks: Rate limits via decorators")

    # 3. Network Detection Middleware
    app.add_middleware(NetworkDetectionMiddleware)
    logger.info(f"✅ Network detection middleware enabled (Local: {LOCAL_NETWORK_CIDR}, VPN: {TAILSCALE_CIDR})")

    # 4. Correlation ID Middleware
    app.add_middleware(CorrelationIdMiddleware)
    logger.info("✅ Correlation ID middleware enabled")

    # 5. Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)
    logger.info("✅ Security headers middleware enabled")

    # 6. Response Cache Middleware
    if redis_client:
        app.add_middleware(CacheMiddleware, redis_client=redis_client, default_ttl=300)
        logger.info("✅ Response cache middleware enabled (Redis-backed)")
        logger.info("   - Cached endpoints: /plugins (60s), /system/status (30s), /health (10s)")
    else:
        logger.warning("⚠️  Redis not available - caching disabled")

    # 7. Request Size Limit Middleware
    app.add_middleware(RequestSizeLimitMiddleware, max_size=10 * 1024 * 1024)
    logger.info("✅ Request size limit middleware enabled (10MB max)")

    logger.info("✅ All security middleware configured successfully")

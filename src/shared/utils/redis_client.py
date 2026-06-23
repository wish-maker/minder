"""
Redis client factory - Centralized Redis initialization
Reduces duplicate code across services
"""

import logging
from typing import Optional

import redis
from redis import Redis

logger = logging.getLogger(__name__)


def create_redis_client(
    host: str = "localhost",
    port: int = 6379,
    password: Optional[str] = None,
    db: int = 0,
    decode_responses: bool = True,
    **kwargs,
) -> Redis:
    """
    Create and configure a Redis client with standard settings

    Args:
        host: Redis host address
        port: Redis port
        password: Optional Redis password
        db: Redis database number (default: 0)
        decode_responses: Whether to decode responses to strings
        **kwargs: Additional redis.Redis parameters

    Returns:
        Configured Redis client instance

    Example:
        >>> redis_client = create_redis_client(
        ...     host=settings.REDIS_HOST,
        ...     port=settings.REDIS_PORT,
        ...     password=settings.REDIS_PASSWORD
        ... )
    """
    try:
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            decode_responses=decode_responses,
            db=db,
            **kwargs,
        )
        # Test connection
        client.ping()
        logger.info(f"✅ Redis client connected to {host}:{port}")
        return client
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis at {host}:{port}: {e}")
        raise


def create_redis_client_from_settings(settings) -> Redis:
    """
    Create Redis client from a settings object with standard attributes
    Expects settings to have: REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

    Args:
        settings: Settings object with Redis configuration

    Returns:
        Configured Redis client instance
    """
    return create_redis_client(
        host=getattr(settings, "REDIS_HOST", "localhost"),
        port=getattr(settings, "REDIS_PORT", 6379),
        password=getattr(settings, "REDIS_PASSWORD", None),
        decode_responses=True,
        db=0,
    )

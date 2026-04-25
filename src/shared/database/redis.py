import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisHelper:
    """Redis helper for caching and pub/sub"""

    def __init__(self, url: str, db: int = 0):
        self.url = url
        self.db = db
        self.client: Optional[aioredis.Redis] = None

    async def connect(self):
        """Connect to Redis"""
        self.client = await aioredis.from_url(f"{self.url}/{self.db}", encoding="utf-8", decode_responses=True)
        logger.info(f"Connected to Redis, db: {self.db}")

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.client:
            await self.client.close()
            logger.info("Disconnected from Redis")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.client:
            raise RuntimeError("Redis not connected. Call connect() first.")

        value = await self.client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = 3600):
        """Set value in cache with TTL"""
        if not self.client:
            raise RuntimeError("Redis not connected. Call connect() first.")

        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await self.client.setex(key, ttl, value)

    async def publish(self, channel: str, message: Dict[str, Any]):
        """Publish message to channel"""
        if not self.client:
            raise RuntimeError("Redis not connected. Call connect() first.")

        await self.client.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str):
        """Subscribe to channel"""
        if not self.client:
            raise RuntimeError("Redis not connected. Call connect() first.")

        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub

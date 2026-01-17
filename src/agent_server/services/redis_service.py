import json
from typing import Any

import structlog
from redis import asyncio as aioredis  # type: ignore

from src.agent_server.settings import settings

logger = structlog.get_logger(__name__)


class RedisService:
    def __init__(self):
        self.redis: aioredis.Redis | None = None
        self.enabled = settings.redis.REDIS_ENABLED
        self.url = settings.redis.REDIS_URL
        self.ttl = settings.redis.REDIS_CACHE_TTL

    async def initialize(self):
        if not self.enabled:
            return

        if not self.url:
            logger.warning(
                "Redis enabled but REDIS_URL not set. Redis will be disabled."
            )
            self.enabled = False
            return

        try:
            self.redis = aioredis.from_url(self.url, decode_responses=False)
            await self.redis.ping()
            logger.info("Connected to Redis", url=self.url)
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            self.enabled = False

    async def close(self):
        if self.redis:
            await self.redis.close()

    async def get(self, key: str) -> Any | None:
        if not self.enabled or not self.redis:
            return None
        try:
            data = await self.redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error("Redis get error", key=key, error=str(e))
        return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        if not self.enabled or not self.redis:
            return False
        try:
            data = json.dumps(value)
            await self.redis.set(key, data, ex=ttl or self.ttl)
            return True
        except Exception as e:
            logger.error("Redis set error", key=key, error=str(e))
            return False

    async def push_stream(self, stream_key: str, data: dict[str, Any]) -> str | None:
        """Push a message to a Redis Stream."""
        if not self.enabled or not self.redis:
            return None
        try:
            # Redis streams require dict with string/bytes keys/values
            # We serialize nested dicts to strings if necessary or just json dump usually
            # But XADD expects fields.
            # Simplified: store payload as one field 'data'
            payload = {"data": json.dumps(data)}
            message_id = await self.redis.xadd(stream_key, payload)
            return message_id
        except Exception as e:
            logger.error("Redis stream push error", stream=stream_key, error=str(e))
            return None


redis_service = RedisService()

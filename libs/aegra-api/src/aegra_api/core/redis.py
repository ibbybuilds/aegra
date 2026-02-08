"""Redis connection management for streaming infrastructure"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import structlog

from aegra_api.settings import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis

try:
    from redis.asyncio import Redis as _Redis
except ImportError:  # pragma: no cover - optional dependency during install
    _Redis: Any = None  # type: ignore[no-redef]


logger = structlog.getLogger(__name__)


class RedisManager:
    """Lazy Redis connection manager.

    The manager reads configuration from the ``REDIS_URL`` environment variable and
    keeps a single shared client for the process.  Redis is optional; if the
    environment variable is missing or the connection fails during startup we
    simply mark the manager as unavailable and downstream code will fall back to
    the in-memory broker.
    """

    def __init__(self) -> None:
        self._redis_url = settings.redis.REDIS_URL
        self._client: Redis | None = None
        self._available = False
        self._init_lock = asyncio.Lock()

    def is_configured(self) -> bool:
        """Return True when a Redis URL has been provided."""

        return bool(self._redis_url)

    def is_available(self) -> bool:
        """Return True when Redis is configured and a client is ready."""

        return self._available and self._client is not None

    async def initialize(self) -> None:
        """Create the Redis client if configuration is present."""

        if not self.is_configured():
            logger.info("Redis URL not configured; using in-memory broker")
            return

        if _Redis is None:
            logger.error("Redis package missing, falling back to in-memory broker")
            return

        async with self._init_lock:
            if self._client is not None:
                return

            try:
                self._client = _Redis.from_url(
                    cast(str, self._redis_url),
                    decode_responses=True,
                    health_check_interval=30,
                )
                await self._client.ping()  # type: ignore[misc]
            except Exception as exc:  # pragma: no cover - network failure path
                logger.error(
                    "Failed to connect to Redis", url=self._redis_url, error=str(exc)
                )
                await self._safe_close()
                self._client = None
                self._available = False
                return

            self._available = True
            logger.info("Connected to Redis for streaming", url=self._redis_url)

    async def close(self) -> None:
        """Cleanly close the Redis client if it exists."""

        await self._safe_close()
        self._client = None
        self._available = False

    async def _safe_close(self) -> None:
        if self._client is None:
            return
        try:
            await self._client.close()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Error closing Redis client", error=str(exc))

    def get_client(self) -> Redis:
        """Return the live Redis client or raise if unavailable."""

        if not self.is_available() or self._client is None:
            raise RuntimeError("Redis client is not available")
        return self._client


redis_manager = RedisManager()

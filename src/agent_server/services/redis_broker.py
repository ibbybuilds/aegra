"""Redis-backed event broker for distributed run management"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import structlog

from src.agent_server.services.base_broker import BaseRunBroker
from src.agent_server.services.redis_service import redis_service
from src.agent_server.settings import settings

logger = structlog.getLogger(__name__)


class RedisRunBroker(BaseRunBroker):
    """Manages event queuing and distribution for a specific run using Redis Streams"""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.stream_key = f"run:{run_id}:stream"
        self.finished_key = f"run:{run_id}:finished"
        self._last_id = "0-0"
        self._finished_local = False
        self._created_at = asyncio.get_event_loop().time()

    async def put(self, event_id: str, payload: Any) -> None:
        """Put an event into the broker queue"""
        try:
            # Serialize payload to JSON
            # payload is typically (event_type, data) or just data
            data_str = json.dumps({"event_id": event_id, "payload": payload})
            # Use 'data' field to store the JSON string
            await redis_service.push_stream(self.stream_key, {"json": data_str})

            # Check if this is an end event
            if (
                isinstance(payload, (tuple, list))
                and len(payload) >= 1
                and payload[0] == "end"
            ):
                self.mark_finished()

        except Exception as e:
            logger.error(
                f"Failed to put event to Redis stream for run {self.run_id}: {e}"
            )

    async def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        """Async iterator yielding (event_id, payload) pairs"""
        while True:
            # Check if we should stop (if redis service is not available)
            if not redis_service.enabled or not redis_service.redis:
                logger.warning("Redis service unavailable, stopping stream")
                break

            try:
                # Read new messages from stream
                # XREAD BLOCK 1000ms STREAMS key ID
                response = await redis_service.redis.xread(
                    {self.stream_key: self._last_id}, count=10, block=1000
                )

                if response:
                    for _, messages in response:
                        for message_id, data in messages:
                            # Update last_id to this message's ID (which is bytes usually, but aioredis handle it)
                            self._last_id = message_id

                            if b"json" in data:
                                try:
                                    entry = json.loads(data[b"json"])
                                    payload = entry.get("payload")
                                    event_id = entry.get("event_id")

                                    # Convert list back to tuple if it looks like a tuple payload
                                    if isinstance(payload, list):
                                        payload = tuple(payload)

                                    yield event_id, payload

                                    # Check locally if this was an end event
                                    if (
                                        isinstance(payload, tuple)
                                        and len(payload) >= 1
                                        and payload[0] == "end"
                                    ):
                                        self._finished_local = True
                                        return
                                except Exception as e:
                                    logger.error(f"Error parsing event data: {e}")
                else:
                    # No new messages. Check if run is finished.
                    if await self._check_finished_remote():
                        # If finished and no new messages, we are done.
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Error reading from Redis stream for run {self.run_id}: {e}"
                )
                await asyncio.sleep(1)

    def mark_finished(self) -> None:
        """Mark this broker as finished"""
        self._finished_local = True
        # Fire and forget async update
        asyncio.create_task(self._mark_finished_remote())
        logger.debug(f"Broker for run {self.run_id} marked as finished (Redis)")

    async def _mark_finished_remote(self) -> None:
        await redis_service.set(
            self.finished_key, "true", ttl=settings.redis.REDIS_CACHE_TTL
        )
        # Also expire the stream
        if redis_service.redis:
            await redis_service.redis.expire(
                self.stream_key, settings.redis.REDIS_CACHE_TTL
            )

    def is_finished(self) -> bool:
        """Check if this broker is finished (local check only)"""
        return self._finished_local

    async def _check_finished_remote(self) -> bool:
        """Check if run is finished in Redis"""
        if self._finished_local:
            return True
        val = await redis_service.get(self.finished_key)
        if val == "true":
            self._finished_local = True
            return True
        return False

    def is_empty(self) -> bool:
        """Check if the queue is empty"""
        # For Redis, return False to let TTL handle cleanup usually,
        # or implement a real check if needed by BrokerManager cleanup logic.
        return False

    def get_age(self) -> float:
        """Get the age of this broker in seconds"""
        return asyncio.get_event_loop().time() - self._created_at

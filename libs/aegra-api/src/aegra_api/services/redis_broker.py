"""Redis-backed broker for multi-instance SSE streaming.

Uses Redis pub/sub for live event broadcast and Redis Lists for replay storage.
The replay buffer (Redis List) stores resumable events with a TTL so they
auto-expire without a cleanup loop. On reconnect, LRANGE fetches missed events.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import structlog
from redis import RedisError

from aegra_api.core.redis_manager import redis_manager
from aegra_api.core.serializers import GeneralSerializer
from aegra_api.services.base_broker import BaseBrokerManager, BaseRunBroker
from aegra_api.settings import settings

logger = structlog.getLogger(__name__)

_serializer = GeneralSerializer()

# TTL for the replay buffer (1 hour)
_REPLAY_TTL_SECONDS = 3600
# Max events in the replay buffer (prevents unbounded growth)
_REPLAY_MAX_EVENTS = 10_000


def _serialize_payload(payload: Any) -> str:
    """Serialize an event payload to a JSON string for Redis transport."""
    return json.dumps(payload, default=_serializer.serialize)


def _deserialize_payload(raw: Any) -> Any:
    """Convert JSON-deserialized data back to expected Python types.

    Event payloads are tuples like ("values", {...}). JSON has no tuple type,
    so they arrive as lists. We convert top-level lists with a string first
    element back to tuples.
    """
    if isinstance(raw, list) and len(raw) >= 1 and isinstance(raw[0], str):
        return tuple(raw)
    return raw


class RedisRunBroker(BaseRunBroker):
    """Broker for a single run backed by Redis pub/sub + Redis Lists.

    Producer: RPUSH to list (replay buffer) + PUBLISH to channel (live).
    Consumer: LRANGE for replay, then SUBSCRIBE for live events.
    """

    def __init__(self, run_id: str, channel: str, cache_key: str) -> None:
        self.run_id = run_id
        self._channel = channel
        self._cache_key = cache_key
        self._finished = False

    async def put(self, event_id: str, payload: Any, *, resumable: bool = True) -> None:
        if self._finished:
            logger.warning(f"Attempted to put event {event_id} into finished broker for run {self.run_id}")
            return

        message = json.dumps(
            {
                "event_id": event_id,
                "payload": json.loads(_serialize_payload(payload)),
            }
        )

        is_end = isinstance(payload, tuple) and len(payload) >= 1 and payload[0] == "end"

        try:
            client = redis_manager.get_client()

            if resumable:
                pipe = client.pipeline()
                pipe.rpush(self._cache_key, message)
                pipe.ltrim(self._cache_key, -_REPLAY_MAX_EVENTS, -1)
                pipe.expire(self._cache_key, _REPLAY_TTL_SECONDS)
                await pipe.execute()  # type: ignore[invalid-await]

            await client.publish(self._channel, message)

            if is_end:
                self._finished = True
        except RedisError as e:
            logger.error(f"Redis publish failed for run {self.run_id}: {e}")
            # Even if Redis fails, mark finished for end events so aiter() can exit
            # rather than looping forever waiting for an end event that won't arrive.
            if is_end:
                self._finished = True

    async def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        client = redis_manager.get_client()
        pubsub = client.pubsub()
        await pubsub.subscribe(self._channel)

        # After subscribing, check if the run already ended (closes the race where
        # the end event was published before we subscribed on this instance).
        end_already_in_buffer = await self._check_end_in_buffer()

        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=0.5,
                )
                if message is None:
                    if self._finished or end_already_in_buffer:
                        break
                    continue

                if message["type"] != "message":
                    continue

                data = json.loads(message["data"])
                event_id: str = data["event_id"]
                payload = _deserialize_payload(data["payload"])

                yield event_id, payload

                if isinstance(payload, tuple) and len(payload) >= 1 and payload[0] == "end":
                    self._finished = True
                    break
        finally:
            await pubsub.unsubscribe(self._channel)
            await pubsub.aclose()

    async def _check_end_in_buffer(self) -> bool:
        """Check if an 'end' event is already in the replay buffer.

        Used after subscribing to detect runs that finished before we subscribed,
        preventing infinite loops in cross-instance consumer scenarios.
        """
        try:
            client = redis_manager.get_client()
            raw_messages = await client.lrange(self._cache_key, -1, -1)  # type: ignore[invalid-await]
            if raw_messages:
                data = json.loads(raw_messages[0])
                payload = _deserialize_payload(data["payload"])
                if isinstance(payload, tuple) and len(payload) >= 1 and payload[0] == "end":
                    self._finished = True
                    return True
        except RedisError as e:
            logger.warning(f"Failed checking replay buffer for end event for run {self.run_id}: {e}")
        return False

    async def replay(self, last_event_id: str | None) -> list[tuple[str, Any]]:
        try:
            client = redis_manager.get_client()
            raw_messages = await client.lrange(self._cache_key, 0, _REPLAY_MAX_EVENTS - 1)  # type: ignore[invalid-await]
        except RedisError as e:
            logger.error(f"Redis replay failed for run {self.run_id}: {e}")
            return []

        if not raw_messages:
            return []

        all_events: list[tuple[str, Any]] = []
        events_after: list[tuple[str, Any]] = []
        found_last = last_event_id is None
        for raw in raw_messages:
            data = json.loads(raw)
            event_id: str = data["event_id"]
            payload = _deserialize_payload(data["payload"])
            all_events.append((event_id, payload))

            if not found_last:
                if event_id == last_event_id:
                    found_last = True
                continue

            events_after.append((event_id, payload))

        # If last_event_id was not found in the buffer, return all events
        if not found_last:
            return all_events

        return events_after

    def mark_finished(self) -> None:
        self._finished = True
        logger.debug(f"Redis broker for run {self.run_id} marked as finished")

    def is_finished(self) -> bool:
        return self._finished


class RedisBrokerManager(BaseBrokerManager):
    """Manages RedisRunBroker instances.

    Brokers are tracked locally for status checks (is_run_streaming).
    Redis handles TTL-based cleanup for the replay buffer — no cleanup task needed.
    """

    def __init__(self) -> None:
        self._brokers: dict[str, RedisRunBroker] = {}
        self._channel_prefix = settings.redis.REDIS_CHANNEL_PREFIX
        self._cache_prefix = f"{self._channel_prefix}cache:"

    def get_or_create_broker(self, run_id: str) -> RedisRunBroker:
        if run_id not in self._brokers:
            channel = f"{self._channel_prefix}{run_id}"
            cache_key = f"{self._cache_prefix}{run_id}"
            self._brokers[run_id] = RedisRunBroker(run_id, channel, cache_key)
            logger.debug(f"Created Redis broker for run {run_id}")
        return self._brokers[run_id]

    def get_broker(self, run_id: str) -> RedisRunBroker | None:
        return self._brokers.get(run_id)

    def cleanup_broker(self, run_id: str) -> None:
        broker = self._brokers.pop(run_id, None)
        if broker:
            broker.mark_finished()
            logger.debug(f"Cleaned up Redis broker for run {run_id}")

    def remove_broker(self, run_id: str) -> None:
        broker = self._brokers.pop(run_id, None)
        if broker:
            broker.mark_finished()
            logger.debug(f"Removed Redis broker for run {run_id}")

    async def start_cleanup_task(self) -> None:
        """No-op. Redis TTL handles replay buffer expiry."""

    async def stop_cleanup_task(self) -> None:
        """No-op."""

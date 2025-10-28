"""Event broker for managing run-specific event queues.

This module now supports two backends:

* An in-memory asyncio queue for local development or single-process usage
* A Redis pub/sub based broker for distributed deployments and remote databases

The :data:`broker_manager` exported at the bottom transparently chooses the
Redis backend when ``REDIS_URL`` is configured and reachable; otherwise it falls
back to the in-memory implementation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Optional

from ..core.redis import redis_manager
from ..core.serializers import GeneralSerializer
from .base_broker import BaseBrokerManager, BaseRunBroker

try:  # pragma: no cover - optional dependency at runtime
    from redis.exceptions import ConnectionError as RedisConnectionError
except Exception:  # pragma: no cover - fallback when redis absent
    RedisConnectionError = ()

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from redis.asyncio import Redis


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helpers for Redis transport
# ---------------------------------------------------------------------------

_serializer = GeneralSerializer()


def _encode_payload(value: Any) -> Any:
    """Convert arbitrary payloads into JSON-safe structures with type tags."""

    if isinstance(value, tuple):
        return {"__type__": "tuple", "items": [_encode_payload(v) for v in value]}
    if isinstance(value, list):
        return {"__type__": "list", "items": [_encode_payload(v) for v in value]}
    if isinstance(value, dict):
        return {
            "__type__": "dict",
            "items": {str(k): _encode_payload(v) for k, v in value.items()},
        }
    if isinstance(value, (str, int, float, bool)) or value is None:
        return {"__type__": "scalar", "value": value}

    serialized = _serializer.serialize(value)
    return _encode_payload(serialized)


def _decode_payload(value: Any) -> Any:
    """Reconstruct original payload structure from encoded JSON."""

    if not isinstance(value, dict):
        return value

    type_marker = value.get("__type__")
    if type_marker == "tuple":
        return tuple(_decode_payload(item) for item in value.get("items", []))
    if type_marker == "list":
        return [_decode_payload(item) for item in value.get("items", [])]
    if type_marker == "dict":
        items = value.get("items", {})
        if isinstance(items, dict):
            return {k: _decode_payload(v) for k, v in items.items()}
        return {}
    if type_marker == "scalar":
        return value.get("value")

    # Fallback: return underlying mapping to avoid data loss
    return {k: _decode_payload(v) for k, v in value.items() if k != "__type__"}


def _is_end_signal(payload: Any) -> bool:
    return isinstance(payload, tuple) and len(payload) >= 1 and payload[0] == "end"


# ---------------------------------------------------------------------------
# In-memory broker (original implementation)
# ---------------------------------------------------------------------------


class InMemoryRunBroker(BaseRunBroker):
    """Manages event queuing and distribution for a specific run (local)."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self.finished = asyncio.Event()
        self._created_at = asyncio.get_event_loop().time()

    async def put(self, event_id: str, payload: Any) -> None:
        if self.finished.is_set():
            logger.debug(
                "Skipping put for finished in-memory broker run_id=%s event_id=%s",
                self.run_id,
                event_id,
            )
            return

        await self.queue.put((event_id, payload))

        if _is_end_signal(payload):
            self.mark_finished()

    async def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        while True:
            try:
                event_id, payload = await asyncio.wait_for(
                    self.queue.get(), timeout=0.1
                )
                yield event_id, payload

                if _is_end_signal(payload):
                    break

            except TimeoutError:
                if self.finished.is_set() and self.queue.empty():
                    break
                continue

    def mark_finished(self) -> None:
        self.finished.set()
        logger.debug("Broker for run %s marked as finished", self.run_id)

    def is_finished(self) -> bool:
        return self.finished.is_set()

    def is_empty(self) -> bool:
        return self.queue.empty()

    def get_age(self) -> float:
        return asyncio.get_event_loop().time() - self._created_at


class InMemoryBrokerManager(BaseBrokerManager):
    def __init__(self) -> None:
        self._brokers: dict[str, InMemoryRunBroker] = {}
        self._cleanup_task: asyncio.Task | None = None

    def get_or_create_broker(self, run_id: str) -> InMemoryRunBroker:
        broker = self._brokers.get(run_id)
        if broker is None:
            broker = InMemoryRunBroker(run_id)
            self._brokers[run_id] = broker
            logger.debug("Created new in-memory broker for run %s", run_id)
        return broker

    def get_broker(self, run_id: str) -> InMemoryRunBroker | None:
        return self._brokers.get(run_id)

    def cleanup_broker(self, run_id: str) -> None:
        broker = self._brokers.get(run_id)
        if broker:
            broker.mark_finished()
            logger.debug("Marked in-memory broker for run %s for cleanup", run_id)

    def remove_broker(self, run_id: str) -> None:
        broker = self._brokers.pop(run_id, None)
        if broker:
            broker.mark_finished()
            logger.debug("Removed in-memory broker for run %s", run_id)

    async def start_cleanup_task(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_old_brokers())

    async def stop_cleanup_task(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

    async def _cleanup_old_brokers(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)
                to_remove: list[str] = []

                for run_id, broker in self._brokers.items():
                    if (
                        broker.is_finished()
                        and broker.is_empty()
                        and broker.get_age() > 3600
                    ):
                        to_remove.append(run_id)

                for run_id in to_remove:
                    self.remove_broker(run_id)
                    logger.info("Cleaned up old in-memory broker for run %s", run_id)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in in-memory broker cleanup task: %s", exc)


# ---------------------------------------------------------------------------
# Redis broker implementation
# ---------------------------------------------------------------------------


class RedisRunBroker(BaseRunBroker):
    """Publish/subscribe broker backed by Redis."""

    def __init__(self, run_id: str, client: Redis) -> None:
        self.run_id = run_id
        self._redis = client
        self._channel = f"aegra:stream:{run_id}"
        self._finished = asyncio.Event()
        self._pubsubs: set[Any] = set()
        self._created_at = asyncio.get_event_loop().time()

    async def put(self, event_id: str, payload: Any) -> None:
        if self._finished.is_set():
            logger.debug(
                "Skipping publish for finished Redis broker run_id=%s event_id=%s",
                self.run_id,
                event_id,
            )
            return

        message = {
            "event_id": event_id,
            "payload": _encode_payload(payload),
        }

        try:
            await self._redis.publish(
                self._channel, json.dumps(message, separators=(",", ":"))
            )
        except Exception as exc:  # pragma: no cover - network failure path
            logger.error(
                "Failed to publish event %s for run %s: %s",
                event_id,
                self.run_id,
                exc,
            )
            raise

        if _is_end_signal(payload):
            self.mark_finished()

    async def aiter(self) -> AsyncIterator[tuple[str, Any]]:
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        await pubsub.subscribe(self._channel)
        self._pubsubs.add(pubsub)

        try:
            while True:
                if self._finished.is_set():
                    break

                try:
                    message = await pubsub.get_message(
                        timeout=1.0, ignore_subscribe_messages=True
                    )
                except asyncio.CancelledError:
                    raise
                except (
                    RedisConnectionError
                ) as exc:  # pragma: no cover - network cleanup
                    logger.debug(
                        "Redis pubsub connection closed for run %s: %s",
                        self.run_id,
                        exc,
                    )
                    self._finished.set()
                    break
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error(
                        "Error receiving Redis message for run %s: %s",
                        self.run_id,
                        exc,
                    )
                    await asyncio.sleep(0.1)
                    continue

                if message is None or message.get("type") != "message":
                    continue

                raw_data = message.get("data")
                if raw_data is None:
                    continue

                try:
                    parsed = json.loads(raw_data)
                    event_id = parsed["event_id"]
                    payload = _decode_payload(parsed["payload"])
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error(
                        "Failed to decode Redis payload for run %s: %s",
                        self.run_id,
                        exc,
                    )
                    continue

                if _is_end_signal(payload):
                    self._finished.set()

                yield event_id, payload

                if _is_end_signal(payload):
                    break

        finally:
            self._pubsubs.discard(pubsub)
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe(self._channel)
                await pubsub.close()

    def mark_finished(self) -> None:
        if not self._finished.is_set():
            self._finished.set()
        for pubsub in list(self._pubsubs):
            asyncio.create_task(self._force_unsubscribe(pubsub))

    async def _force_unsubscribe(self, pubsub: Any) -> None:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(self._channel)
            await pubsub.close()

    def is_finished(self) -> bool:
        return self._finished.is_set()

    def is_empty(self) -> bool:
        # Redis queues are ephemeral; treat as empty once finished.
        return True

    def get_age(self) -> float:
        return asyncio.get_event_loop().time() - self._created_at


class RedisBrokerManager(BaseBrokerManager):
    def __init__(self) -> None:
        self._brokers: dict[str, RedisRunBroker] = {}
        self._cleanup_task: asyncio.Task | None = None

    def _ensure_available(self) -> None:
        if not redis_manager.is_available():
            raise RuntimeError("Redis broker requested but Redis is not available")

    def get_or_create_broker(self, run_id: str) -> RedisRunBroker:
        self._ensure_available()
        broker = self._brokers.get(run_id)
        if broker is None:
            client = redis_manager.get_client()
            broker = RedisRunBroker(run_id, client)
            self._brokers[run_id] = broker
            logger.debug("Created new Redis broker for run %s", run_id)
        return broker

    def get_broker(self, run_id: str) -> RedisRunBroker | None:
        return self._brokers.get(run_id)

    def cleanup_broker(self, run_id: str) -> None:
        broker = self._brokers.get(run_id)
        if broker:
            broker.mark_finished()

    async def start_cleanup_task(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_old_brokers())

    async def stop_cleanup_task(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task

    async def _cleanup_old_brokers(self) -> None:
        while True:
            try:
                await asyncio.sleep(300)
                to_remove: list[str] = []
                for run_id, broker in self._brokers.items():
                    if broker.is_finished() and broker.get_age() > 3600:
                        to_remove.append(run_id)
                for run_id in to_remove:
                    self._brokers.pop(run_id, None)
                    logger.info("Cleaned up Redis broker for run %s", run_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in Redis broker cleanup task: %s", exc)


# ---------------------------------------------------------------------------
# Hybrid manager that chooses Redis when available
# ---------------------------------------------------------------------------


class HybridBrokerManager(BaseBrokerManager):
    def __init__(self) -> None:
        self._memory_backend = InMemoryBrokerManager()
        self._redis_backend: Optional[RedisBrokerManager] = None
        self._redis_enabled_logged = False
        raw_mode = os.getenv("STREAMING_BROKER", "auto")
        mode = raw_mode.strip().lower()
        if mode not in {"auto", "redis", "memory"}:
            logger.warning(
                "Invalid STREAMING_BROKER value '%s'; falling back to auto", raw_mode
            )
            mode = "auto"
        self._mode = mode

    def _redis_backend_ready(self) -> bool:
        if self._mode == "memory":
            return False
        if not redis_manager.is_configured():
            if self._mode == "redis":
                raise RuntimeError(
                    "STREAMING_BROKER=redis requires REDIS_URL to be configured"
                )
            return False
        if not redis_manager.is_available():
            if self._mode == "redis":
                raise RuntimeError("STREAMING_BROKER=redis but Redis is not available")
            return False
        if self._redis_backend is None:
            self._redis_backend = RedisBrokerManager()
            if not self._redis_enabled_logged:
                logger.info("Redis streaming backend enabled")
                self._redis_enabled_logged = True
        return True

    def _active_backend(self) -> BaseBrokerManager:
        if self._redis_backend_ready():
            return self._redis_backend  # type: ignore[return-value]
        return self._memory_backend

    def validate_configuration(self) -> None:
        """Ensure configured backend is ready; raise if enforced backend missing."""

        if self._mode == "redis":
            # _redis_backend_ready will raise if unavailable
            self._redis_backend_ready()
        elif self._mode == "memory":
            logger.info("Streaming backend forced to in-memory via STREAMING_BROKER")

    def get_or_create_broker(self, run_id: str) -> BaseRunBroker:
        if self._redis_backend_ready():
            try:
                return self._redis_backend.get_or_create_broker(run_id)  # type: ignore[union-attr]
            except Exception as exc:
                logger.error(
                    "Redis broker unavailable, falling back to in-memory: %s", exc
                )
                self._redis_backend = None
        return self._memory_backend.get_or_create_broker(run_id)

    def get_broker(self, run_id: str) -> BaseRunBroker | None:
        if self._redis_backend_ready():
            try:
                return self._redis_backend.get_broker(run_id)  # type: ignore[union-attr]
            except Exception as exc:
                logger.error(
                    "Redis broker unavailable during get_broker; using in-memory: %s",
                    exc,
                )
                self._redis_backend = None
        return self._memory_backend.get_broker(run_id)

    def cleanup_broker(self, run_id: str) -> None:
        if self._redis_backend_ready():
            try:
                self._redis_backend.cleanup_broker(run_id)  # type: ignore[union-attr]
                return
            except Exception as exc:
                logger.error(
                    "Redis broker unavailable during cleanup; using in-memory: %s",
                    exc,
                )
                self._redis_backend = None
        self._memory_backend.cleanup_broker(run_id)

    async def start_cleanup_task(self) -> None:
        await self._memory_backend.start_cleanup_task()
        if self._redis_backend_ready():
            try:
                await self._redis_backend.start_cleanup_task()  # type: ignore[union-attr]
            except Exception as exc:
                logger.error(
                    "Redis broker cleanup task failed to start; disabling Redis backend: %s",
                    exc,
                )
                self._redis_backend = None

    async def stop_cleanup_task(self) -> None:
        await self._memory_backend.stop_cleanup_task()
        if self._redis_backend is not None:
            await self._redis_backend.stop_cleanup_task()


# Global broker manager instance used throughout the codebase
broker_manager: HybridBrokerManager = HybridBrokerManager()

# Backwards-compatible exports for existing imports/tests
RunBroker = InMemoryRunBroker
BrokerManager = InMemoryBrokerManager

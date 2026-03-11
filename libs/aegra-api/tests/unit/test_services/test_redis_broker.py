"""Unit tests for RedisRunBroker and RedisBrokerManager"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from aegra_api.services.redis_broker import (
    RedisBrokerManager,
    RedisRunBroker,
    _deserialize_payload,
    _serialize_payload,
)


class TestSerializationHelpers:
    """Test serialization/deserialization helpers"""

    def test_serialize_payload_simple_tuple(self) -> None:
        result = _serialize_payload(("values", {"key": "value"}))
        parsed = json.loads(result)
        assert parsed == ["values", {"key": "value"}]

    def test_serialize_payload_end_event(self) -> None:
        result = _serialize_payload(("end", {"status": "success"}))
        parsed = json.loads(result)
        assert parsed == ["end", {"status": "success"}]

    def test_serialize_payload_dict(self) -> None:
        result = _serialize_payload({"data": "test"})
        parsed = json.loads(result)
        assert parsed == {"data": "test"}

    def test_deserialize_payload_converts_list_to_tuple(self) -> None:
        result = _deserialize_payload(["values", {"key": "value"}])
        assert result == ("values", {"key": "value"})
        assert isinstance(result, tuple)

    def test_deserialize_payload_preserves_dict(self) -> None:
        result = _deserialize_payload({"data": "test"})
        assert result == {"data": "test"}

    def test_deserialize_payload_preserves_non_event_list(self) -> None:
        result = _deserialize_payload([1, 2, 3])
        assert result == [1, 2, 3]
        assert isinstance(result, list)

    def test_deserialize_payload_preserves_empty_list(self) -> None:
        result = _deserialize_payload([])
        assert result == []

    def test_deserialize_end_event(self) -> None:
        result = _deserialize_payload(["end", {"status": "success"}])
        assert result == ("end", {"status": "success"})
        assert isinstance(result, tuple)


class TestRedisRunBroker:
    """Test RedisRunBroker class"""

    def _make_broker(self, run_id: str = "run-123") -> RedisRunBroker:
        return RedisRunBroker(run_id, f"aegra:run:{run_id}", f"aegra:run:cache:{run_id}")

    @pytest.mark.asyncio
    async def test_put_publishes_and_caches(self) -> None:
        """Test that put() publishes to channel and stores in cache list via pipeline"""
        broker = self._make_broker()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock()
        mock_client = MagicMock()
        mock_client.publish = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            await broker.put("evt-1", ("values", {"msg": "hello"}))

            # Should publish to channel
            mock_client.publish.assert_called_once()
            channel, message = mock_client.publish.call_args[0]
            assert channel == "aegra:run:run-123"

            data = json.loads(message)
            assert data["event_id"] == "evt-1"
            assert data["payload"] == ["values", {"msg": "hello"}]

            # Should use pipeline for cache operations
            mock_client.pipeline.assert_called_once()
            mock_pipe.rpush.assert_called_once()
            cache_key, cached_msg = mock_pipe.rpush.call_args[0]
            assert cache_key == "aegra:run:cache:run-123"
            assert json.loads(cached_msg) == data

            # Should trim and set TTL in pipeline
            mock_pipe.ltrim.assert_called_once()
            mock_pipe.expire.assert_called_once()
            mock_pipe.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_put_non_resumable_skips_cache(self) -> None:
        """Test that put() with resumable=False skips the cache pipeline"""
        broker = self._make_broker()
        mock_client = MagicMock()
        mock_client.publish = AsyncMock()

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            await broker.put("evt-1", ("values", {"msg": "hello"}), resumable=False)

            mock_client.publish.assert_called_once()
            mock_client.pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_put_end_event_marks_finished(self) -> None:
        broker = self._make_broker()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock()
        mock_client = MagicMock()
        mock_client.publish = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            await broker.put("evt-end", ("end", {"status": "success"}))

            assert broker.is_finished()

    @pytest.mark.asyncio
    async def test_put_after_finished_skips(self) -> None:
        broker = self._make_broker()
        broker.mark_finished()
        mock_client = MagicMock()
        mock_client.publish = AsyncMock()

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            await broker.put("evt-1", ("values", {"data": "test"}))

            mock_client.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_put_handles_redis_failure_gracefully(self) -> None:
        broker = self._make_broker()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock(side_effect=RedisConnectionError("Redis down"))
        mock_client = MagicMock()
        mock_client.publish = AsyncMock()
        mock_client.pipeline.return_value = mock_pipe

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            # Should not raise
            await broker.put("evt-1", ("values", {"data": "test"}))

    @pytest.mark.asyncio
    async def test_aiter_yields_events(self) -> None:
        broker = self._make_broker()

        messages = [
            {"type": "message", "data": json.dumps({"event_id": "evt-1", "payload": ["values", {"msg": "hi"}]})},
            {"type": "message", "data": json.dumps({"event_id": "evt-2", "payload": ["end", {"status": "success"}]})},
        ]
        call_count = 0

        async def mock_get_message(ignore_subscribe_messages: bool = True, timeout: float = 0.5) -> dict | None:
            nonlocal call_count
            if call_count < len(messages):
                msg = messages[call_count]
                call_count += 1
                return msg
            return None

        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = mock_get_message
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        # _check_end_in_buffer calls lrange — return empty (no end in buffer yet)
        mock_client.lrange = AsyncMock(return_value=[])

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events: list[tuple[str, object]] = []
            async for event_id, payload in broker.aiter():
                events.append((event_id, payload))

        assert len(events) == 2
        assert events[0] == ("evt-1", ("values", {"msg": "hi"}))
        assert events[1] == ("evt-2", ("end", {"status": "success"}))

    @pytest.mark.asyncio
    async def test_aiter_skips_non_message_types(self) -> None:
        broker = self._make_broker()

        messages = [
            {"type": "subscribe", "data": None},
            {"type": "message", "data": json.dumps({"event_id": "evt-1", "payload": ["end", {}]})},
        ]
        call_count = 0

        async def mock_get_message(ignore_subscribe_messages: bool = True, timeout: float = 0.5) -> dict | None:
            nonlocal call_count
            if call_count < len(messages):
                msg = messages[call_count]
                call_count += 1
                return msg
            return None

        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = mock_get_message
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        mock_client.lrange = AsyncMock(return_value=[])

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events: list[tuple[str, object]] = []
            async for event_id, payload in broker.aiter():
                events.append((event_id, payload))

        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_replay_returns_all_when_no_last_event_id(self) -> None:
        """Test replay returns all cached events when last_event_id is None"""
        broker = self._make_broker()
        mock_client = AsyncMock()
        mock_client.lrange.return_value = [
            json.dumps({"event_id": "evt-1", "payload": ["values", {"a": 1}]}),
            json.dumps({"event_id": "evt-2", "payload": ["values", {"a": 2}]}),
        ]

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events = await broker.replay(None)

        assert len(events) == 2
        assert events[0] == ("evt-1", ("values", {"a": 1}))
        assert events[1] == ("evt-2", ("values", {"a": 2}))

    @pytest.mark.asyncio
    async def test_replay_returns_events_after_last_event_id(self) -> None:
        """Test replay returns only events after last_event_id"""
        broker = self._make_broker()
        mock_client = AsyncMock()
        mock_client.lrange.return_value = [
            json.dumps({"event_id": "evt-1", "payload": ["values", {"a": 1}]}),
            json.dumps({"event_id": "evt-2", "payload": ["values", {"a": 2}]}),
            json.dumps({"event_id": "evt-3", "payload": ["end", {}]}),
        ]

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events = await broker.replay("evt-1")

        assert len(events) == 2
        assert events[0] == ("evt-2", ("values", {"a": 2}))
        assert events[1] == ("evt-3", ("end", {}))

    @pytest.mark.asyncio
    async def test_replay_returns_all_when_last_event_id_not_found(self) -> None:
        """Test replay returns all events when last_event_id is not in cache"""
        broker = self._make_broker()
        mock_client = AsyncMock()
        mock_client.lrange.return_value = [
            json.dumps({"event_id": "evt-1", "payload": ["values", {"a": 1}]}),
        ]

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events = await broker.replay("evt-999")

        assert len(events) == 1
        assert events[0] == ("evt-1", ("values", {"a": 1}))

    @pytest.mark.asyncio
    async def test_replay_returns_empty_when_no_cache(self) -> None:
        broker = self._make_broker()
        mock_client = AsyncMock()
        mock_client.lrange.return_value = []

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events = await broker.replay(None)

        assert events == []

    @pytest.mark.asyncio
    async def test_replay_handles_redis_failure(self) -> None:
        broker = self._make_broker()
        mock_client = AsyncMock()
        mock_client.lrange.side_effect = RedisConnectionError("Redis down")

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events = await broker.replay(None)

        assert events == []

    @pytest.mark.asyncio
    async def test_check_end_in_buffer_returns_true_when_end_present(self) -> None:
        """Test that _check_end_in_buffer detects end events in replay buffer"""
        broker = self._make_broker()
        mock_client = AsyncMock()
        mock_client.lrange.return_value = [
            json.dumps({"event_id": "evt-end", "payload": ["end", {"status": "success"}]})
        ]

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client
            result = await broker._check_end_in_buffer()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_end_in_buffer_returns_false_when_no_end(self) -> None:
        """Test that _check_end_in_buffer returns False when no end event"""
        broker = self._make_broker()
        mock_client = AsyncMock()
        mock_client.lrange.return_value = [json.dumps({"event_id": "evt-1", "payload": ["values", {"a": 1}]})]

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client
            result = await broker._check_end_in_buffer()

        assert result is False

    @pytest.mark.asyncio
    async def test_aiter_exits_when_end_already_in_buffer(self) -> None:
        """Test that aiter() exits immediately when end event is already in replay buffer"""
        broker = self._make_broker()

        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.aclose = AsyncMock()
        # Return None (no live messages) — should exit because end is in buffer
        mock_pubsub.get_message = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.pubsub.return_value = mock_pubsub
        # _check_end_in_buffer sees end event in last position
        mock_client.lrange = AsyncMock(
            return_value=[json.dumps({"event_id": "evt-end", "payload": ["end", {"status": "success"}]})]
        )

        with patch("aegra_api.services.redis_broker.redis_manager") as mock_rm:
            mock_rm.get_client.return_value = mock_client

            events: list[tuple[str, object]] = []
            async for event_id, payload in broker.aiter():
                events.append((event_id, payload))

        # Should exit with no live events since end was already in buffer
        assert len(events) == 0

    def test_mark_finished(self) -> None:
        broker = self._make_broker()
        broker.mark_finished()
        assert broker.is_finished()

    def test_is_finished_default_false(self) -> None:
        broker = self._make_broker()
        assert not broker.is_finished()


class TestRedisBrokerManager:
    """Test RedisBrokerManager class"""

    def _make_manager(self) -> RedisBrokerManager:
        return RedisBrokerManager()

    def test_get_or_create_broker_creates_new(self) -> None:
        manager = self._make_manager()
        broker = manager.get_or_create_broker("run-123")

        assert broker is not None
        assert broker.run_id == "run-123"

    def test_get_or_create_broker_returns_existing(self) -> None:
        manager = self._make_manager()
        broker1 = manager.get_or_create_broker("run-123")
        broker2 = manager.get_or_create_broker("run-123")

        assert broker1 is broker2

    def test_get_or_create_different_runs(self) -> None:
        manager = self._make_manager()
        broker1 = manager.get_or_create_broker("run-123")
        broker2 = manager.get_or_create_broker("run-456")

        assert broker1 is not broker2

    def test_get_existing_broker(self) -> None:
        manager = self._make_manager()
        created = manager.get_or_create_broker("run-123")
        retrieved = manager.get_broker("run-123")

        assert retrieved is created

    def test_get_nonexistent_broker(self) -> None:
        manager = self._make_manager()
        broker = manager.get_broker("nonexistent")

        assert broker is None

    def test_cleanup_broker(self) -> None:
        manager = self._make_manager()
        broker = manager.get_or_create_broker("run-123")
        manager.cleanup_broker("run-123")

        assert broker.is_finished()
        # Broker should be removed from the manager after cleanup
        assert manager.get_broker("run-123") is None

    def test_remove_broker(self) -> None:
        manager = self._make_manager()
        manager.get_or_create_broker("run-123")
        manager.remove_broker("run-123")

        assert manager.get_broker("run-123") is None

    def test_remove_nonexistent_broker(self) -> None:
        manager = self._make_manager()
        manager.remove_broker("nonexistent")

    @pytest.mark.asyncio
    async def test_cleanup_task_is_noop(self) -> None:
        manager = self._make_manager()
        await manager.start_cleanup_task()
        await manager.stop_cleanup_task()

    def test_broker_has_cache_key(self) -> None:
        """Test that created brokers have correct cache key"""
        manager = self._make_manager()
        broker = manager.get_or_create_broker("run-123")

        assert broker._cache_key == "aegra:run:cache:run-123"
        assert broker._channel == "aegra:run:run-123"

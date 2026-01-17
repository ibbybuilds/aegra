"""Unit tests for RedisRunBroker"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agent_server.services.redis_broker import RedisRunBroker


class TestRedisRunBroker:
    @pytest.fixture
    def mock_redis_service(self):
        with patch("src.agent_server.services.redis_broker.redis_service") as mock:
            mock.enabled = True
            mock.redis = AsyncMock()
            # Mark async methods as AsyncMock
            mock.set = AsyncMock()
            mock.get = AsyncMock()
            mock.push_stream = AsyncMock()
            yield mock

    @pytest.mark.asyncio
    async def test_initialization(self):
        broker = RedisRunBroker("run-1")
        assert broker.run_id == "run-1"
        assert broker.stream_key == "run:run-1:stream"
        assert broker.finished_key == "run:run-1:finished"
        assert broker._last_id == "0-0"
        assert not broker._finished_local

    @pytest.mark.asyncio
    async def test_put_event(self, mock_redis_service):
        broker = RedisRunBroker("run-1")

        await broker.put("evt-1", {"data": "test"})

        mock_redis_service.push_stream.assert_called_with(
            "run:run-1:stream",
            {"json": '{"event_id": "evt-1", "payload": {"data": "test"}}'},
        )

    @pytest.mark.asyncio
    async def test_put_end_event(self, mock_redis_service):
        broker = RedisRunBroker("run-1")

        await broker.put("evt-2", ("end", {}))

        assert broker.is_finished()
        # Since mark_finished runs in a background task, we check local state only

    @pytest.mark.asyncio
    async def test_aiter_yields_events(self, mock_redis_service):
        broker = RedisRunBroker("run-1")

        # Mock xread response
        # Structure: list of [stream_name, list of [message_id, {b'json': b'JSON_STRING'}]]
        mock_redis_service.redis.xread.side_effect = [
            [
                [
                    b"run:run-1:stream",
                    [
                        (
                            b"1-0",
                            {
                                b"json": b'{"event_id": "evt-1", "payload": {"data": "test"}}'
                            },
                        ),
                    ],
                ]
            ],
            [
                [
                    b"run:run-1:stream",
                    [
                        (
                            b"1-1",
                            {
                                b"json": b'{"event_id": "evt-end", "payload": ["end", {}]}'
                            },
                        ),
                    ],
                ]
            ],
            None,  # Finish iteration
        ]

        # We need mock_redis_service to check finished remote to exit loop if we simulate empty xread
        mock_redis_service.get.return_value = "true"

        events = []
        async for event in broker.aiter():
            events.append(event)

        assert len(events) == 2
        assert events[0] == ("evt-1", {"data": "test"})
        assert events[1] == ("evt-end", ("end", {}))
        assert broker.is_finished()  # Because end event was received

    @pytest.mark.asyncio
    async def test_aiter_stops_remotely_finished(self, mock_redis_service):
        broker = RedisRunBroker("run-1")

        # Empty read then finished check
        mock_redis_service.redis.xread.return_value = []
        mock_redis_service.get.return_value = "true"

        events = []
        async for _ in broker.aiter():
            events.append(_)

        assert len(events) == 0
        assert broker.is_finished()

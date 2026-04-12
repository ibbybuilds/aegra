"""Unit tests for in-memory broker replay functionality"""

import pytest

from aegra_api.services.broker import RunBroker


class TestRunBrokerReplay:
    """Test RunBroker replay buffer"""

    def _make_broker(self, run_id: str = "run-123") -> RunBroker:
        return RunBroker(run_id)

    @pytest.mark.asyncio
    async def test_put_stores_in_replay_buffer(self) -> None:
        """Test that put() stores events in the replay buffer by default"""
        broker = self._make_broker()

        await broker.put("evt-1", ("values", {"a": 1}))
        await broker.put("evt-2", ("values", {"a": 2}))

        events = await broker.replay(None)
        assert len(events) == 2
        assert events[0] == ("evt-1", ("values", {"a": 1}))
        assert events[1] == ("evt-2", ("values", {"a": 2}))

    @pytest.mark.asyncio
    async def test_put_non_resumable_skips_buffer(self) -> None:
        """Test that put() with resumable=False skips the replay buffer"""
        broker = self._make_broker()

        await broker.put("evt-1", ("values", {"a": 1}), resumable=True)
        await broker.put("evt-2", ("values", {"a": 2}), resumable=False)
        await broker.put("evt-3", ("values", {"a": 3}), resumable=True)

        events = await broker.replay(None)
        assert len(events) == 2
        assert events[0] == ("evt-1", ("values", {"a": 1}))
        assert events[1] == ("evt-3", ("values", {"a": 3}))

    @pytest.mark.asyncio
    async def test_replay_all_when_no_last_event_id(self) -> None:
        broker = self._make_broker()

        await broker.put("evt-1", ("values", {"a": 1}))
        await broker.put("evt-2", ("values", {"a": 2}))

        events = await broker.replay(None)
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_replay_after_last_event_id(self) -> None:
        broker = self._make_broker()

        await broker.put("evt-1", ("values", {"a": 1}))
        await broker.put("evt-2", ("values", {"a": 2}))
        await broker.put("evt-3", ("values", {"a": 3}))

        events = await broker.replay("evt-1")
        assert len(events) == 2
        assert events[0] == ("evt-2", ("values", {"a": 2}))
        assert events[1] == ("evt-3", ("values", {"a": 3}))

    @pytest.mark.asyncio
    async def test_replay_from_last_event_returns_empty(self) -> None:
        """Test replay returns empty when last_event_id is the final event"""
        broker = self._make_broker()

        await broker.put("evt-1", ("values", {"a": 1}))
        await broker.put("evt-2", ("values", {"a": 2}))

        events = await broker.replay("evt-2")
        assert events == []

    @pytest.mark.asyncio
    async def test_replay_unknown_last_event_id_returns_all(self) -> None:
        """Test replay returns all events when last_event_id is not found"""
        broker = self._make_broker()

        await broker.put("evt-1", ("values", {"a": 1}))

        events = await broker.replay("evt-999")
        assert len(events) == 1
        assert events[0] == ("evt-1", ("values", {"a": 1}))

    @pytest.mark.asyncio
    async def test_replay_empty_buffer(self) -> None:
        broker = self._make_broker()

        events = await broker.replay(None)
        assert events == []

    @pytest.mark.asyncio
    async def test_replay_empty_buffer_with_last_event_id(self) -> None:
        broker = self._make_broker()

        events = await broker.replay("evt-1")
        assert events == []

    @pytest.mark.asyncio
    async def test_end_event_stored_in_replay_buffer(self) -> None:
        """Test that end events are also stored for replay"""
        broker = self._make_broker()

        await broker.put("evt-1", ("values", {"a": 1}))
        await broker.put("evt-2", ("end", {"status": "success"}))

        events = await broker.replay(None)
        assert len(events) == 2
        assert events[1] == ("evt-2", ("end", {"status": "success"}))

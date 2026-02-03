"""Unit tests for RunBroker and BrokerManager"""

import asyncio

import pytest

from aegra_api.services.broker import BrokerManager, RunBroker


class TestRunBroker:
    """Test RunBroker class"""

    @pytest.mark.asyncio
    async def test_run_broker_initialization(self):
        """Test RunBroker initialization"""
        broker = RunBroker("run-123")

        assert broker.run_id == "run-123"
        assert broker.queue is not None
        assert not broker.finished.is_set()

    @pytest.mark.asyncio
    async def test_put_event(self):
        """Test putting an event into broker"""
        broker = RunBroker("run-123")

        await broker.put("evt-1", {"data": "test"})

        # Event should be in queue
        event_id, payload = await asyncio.wait_for(broker.queue.get(), timeout=1.0)
        assert event_id == "evt-1"
        assert payload == {"data": "test"}

    @pytest.mark.asyncio
    async def test_put_end_event_marks_finished(self):
        """Test that end event marks broker as finished"""
        broker = RunBroker("run-123")

        # Put end event (format: tuple with 'end' as first element)
        await broker.put("evt-end", ("end", {}))

        # Broker should be marked as finished
        assert broker.finished.is_set()

    @pytest.mark.asyncio
    async def test_put_after_finished_warns(self):
        """Test that putting after finished logs warning"""
        broker = RunBroker("run-123")
        broker.mark_finished()

        # Should not raise, just log warning
        await broker.put("evt-1", {"data": "test"})

        # Queue should be empty
        assert broker.queue.empty()

    @pytest.mark.asyncio
    async def test_mark_finished(self):
        """Test marking broker as finished"""
        broker = RunBroker("run-123")

        broker.mark_finished()

        assert broker.finished.is_set()

    @pytest.mark.asyncio
    async def test_aiter_yields_events(self):
        """Test async iteration over broker events"""
        broker = RunBroker("run-123")

        # Put some events
        await broker.put("evt-1", {"data": "first"})
        await broker.put("evt-2", {"data": "second"})
        await broker.put("evt-end", ("end", {}))

        # Collect events
        events = []
        async for event_id, payload in broker.aiter():
            events.append((event_id, payload))
            if event_id == "evt-end":
                break

        assert len(events) == 3
        assert events[0] == ("evt-1", {"data": "first"})
        assert events[1] == ("evt-2", {"data": "second"})
        assert events[2] == ("evt-end", ("end", {}))

    @pytest.mark.asyncio
    async def test_aiter_stops_on_end_event(self):
        """Test that iteration stops on end event"""
        broker = RunBroker("run-123")

        await broker.put("evt-1", {"data": "test"})
        await broker.put("evt-end", ("end", {}))

        events = []
        async for event_id, payload in broker.aiter():
            events.append((event_id, payload))

        # Should get both events including end
        assert len(events) == 2


class TestBrokerManager:
    """Test BrokerManager class"""

    @pytest.mark.asyncio
    async def test_broker_manager_initialization(self):
        """Test BrokerManager initialization"""
        manager = BrokerManager()

        assert manager._brokers == {}

    @pytest.mark.asyncio
    async def test_get_or_create_broker(self):
        """Test getting or creating a broker"""
        manager = BrokerManager()

        broker1 = manager.get_or_create_broker("run-123")
        broker2 = manager.get_or_create_broker("run-123")

        # Should return the same broker instance
        assert broker1 is broker2
        assert broker1.run_id == "run-123"

    @pytest.mark.asyncio
    async def test_get_or_create_different_runs(self):
        """Test creating brokers for different runs"""
        manager = BrokerManager()

        broker1 = manager.get_or_create_broker("run-123")
        broker2 = manager.get_or_create_broker("run-456")

        # Should be different brokers
        assert broker1 is not broker2
        assert broker1.run_id == "run-123"
        assert broker2.run_id == "run-456"

    @pytest.mark.asyncio
    async def test_get_existing_broker(self):
        """Test getting an existing broker"""
        manager = BrokerManager()

        # Create a broker
        created = manager.get_or_create_broker("run-123")

        # Get it
        retrieved = manager.get_broker("run-123")

        assert retrieved is created

    @pytest.mark.asyncio
    async def test_get_nonexistent_broker(self):
        """Test getting a nonexistent broker returns None"""
        manager = BrokerManager()

        broker = manager.get_broker("nonexistent")

        assert broker is None

    @pytest.mark.asyncio
    async def test_cleanup_broker(self):
        """Test cleanup_broker marks broker as finished"""
        manager = BrokerManager()

        # Create a broker
        broker = manager.get_or_create_broker("run-123")

        # Cleanup it (marks finished but doesn't remove)
        manager.cleanup_broker("run-123")

        # Should still exist but be marked finished
        assert manager.get_broker("run-123") is broker
        assert broker.is_finished()

    @pytest.mark.asyncio
    async def test_remove_broker(self):
        """Test removing a broker"""
        manager = BrokerManager()

        # Create a broker
        manager.get_or_create_broker("run-123")

        # Remove it
        manager.remove_broker("run-123")

        # Should no longer exist
        assert manager.get_broker("run-123") is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_broker(self):
        """Test removing a nonexistent broker doesn't error"""
        manager = BrokerManager()

        # Should not raise
        manager.remove_broker("nonexistent")

    @pytest.mark.asyncio
    async def test_start_and_stop_cleanup_task(self):
        """Test starting and stopping cleanup task"""
        manager = BrokerManager()

        # Start cleanup task
        await manager.start_cleanup_task()

        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        # Stop cleanup task
        await manager.stop_cleanup_task()

        assert manager._cleanup_task.cancelled() or manager._cleanup_task.done()

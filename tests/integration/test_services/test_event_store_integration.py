"""Integration tests for EventStore service with real database"""

import asyncio
from datetime import UTC, datetime

import pytest

from src.agent_server.core.sse import SSEEvent
from src.agent_server.services.event_store import EventStore


@pytest.fixture(scope="session")
def database_available():
    """Check if database is available for integration tests"""
    import os

    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        yield False
        return

    # Use psycopg2 for Supabase/pgbouncer compatibility
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        engine = create_engine(sync_url, echo=False)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        yield True
    except Exception:
        yield False
    finally:
        if "engine" in locals():
            engine.dispose()


@pytest.fixture
def clean_event_store_tables(database_available):
    """Clean up event store tables before and after tests"""
    import os

    from dotenv import load_dotenv
    from sqlalchemy import create_engine, text

    if not database_available:
        pytest.skip("Database not available for integration tests")

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    engine = create_engine(sync_url, echo=False)

    # Clean up before test
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM run_events"))
        conn.commit()

    yield

    # Clean up after test
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM run_events"))
        conn.commit()

    engine.dispose()


@pytest.fixture
def event_store(clean_event_store_tables):
    """Create EventStore instance with real database"""
    import os
    from unittest.mock import patch

    from dotenv import load_dotenv
    from sqlalchemy import create_engine

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    # Create a sync engine for testing
    sync_engine = create_engine(sync_url, echo=False)

    # Patch db_manager.get_engine to return our sync engine wrapped for async
    class AsyncEngineWrapper:
        def __init__(self, sync_engine):
            self.sync_engine = sync_engine

        def begin(self):
            return AsyncConnectionWrapper(self.sync_engine.connect())

    class AsyncConnectionWrapper:
        def __init__(self, sync_conn):
            self.sync_conn = sync_conn

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                # Commit on successful exit
                self.sync_conn.commit()
            else:
                # Rollback on error
                self.sync_conn.rollback()
            self.sync_conn.close()

        async def execute(self, stmt, params=None):
            # Run sync execute in thread pool
            import asyncio

            loop = asyncio.get_event_loop()
            if params:
                result = await loop.run_in_executor(
                    None, lambda: self.sync_conn.execute(stmt, params)
                )
            else:
                result = await loop.run_in_executor(
                    None, lambda: self.sync_conn.execute(stmt)
                )
            return result

    with patch(
        "src.agent_server.services.event_store.db_manager.get_engine",
        return_value=AsyncEngineWrapper(sync_engine),
    ):
        yield EventStore()

    sync_engine.dispose()


class TestEventStoreIntegration:
    """Integration tests using real PostgreSQL database"""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_single_event(self, event_store):
        """Test storing and retrieving a single event"""
        run_id = "integration-test-run-001"
        event = SSEEvent(
            id=f"{run_id}_event_1",
            event="test_start",
            data={"type": "run_start", "message": "Integration test started"},
            timestamp=datetime.now(UTC),
        )

        # Store event
        await event_store.store_event(run_id, event)

        # Retrieve all events
        events = await event_store.get_all_events(run_id)

        assert len(events) == 1
        assert events[0].id == event.id
        assert events[0].event == event.event
        assert events[0].data == event.data

    @pytest.mark.asyncio
    async def test_store_multiple_events_sequence(self, event_store):
        """Test storing multiple events with proper sequencing"""
        run_id = "integration-test-run-002"

        events_data = [
            ("start", {"type": "run_start"}),
            ("chunk", {"data": "processing step 1"}),
            ("chunk", {"data": "processing step 2"}),
            ("complete", {"type": "run_complete", "result": "success"}),
        ]

        # Store events
        stored_events = []
        for i, (event_type, data) in enumerate(events_data, 1):
            event = SSEEvent(
                id=f"{run_id}_event_{i}",
                event=event_type,
                data=data,
                timestamp=datetime.now(UTC),
            )
            await event_store.store_event(run_id, event)
            stored_events.append(event)

        # Retrieve all events
        retrieved_events = await event_store.get_all_events(run_id)

        assert len(retrieved_events) == 4

        # Verify events are ordered by sequence
        for i, event in enumerate(retrieved_events):
            assert event.id == stored_events[i].id
            assert event.event == stored_events[i].event
            assert event.data == stored_events[i].data

    @pytest.mark.asyncio
    async def test_get_events_since_functionality(self, event_store):
        """Test get_events_since retrieves correct subset of events"""
        run_id = "integration-test-run-003"

        # Store 5 events
        for i in range(1, 6):
            event = SSEEvent(
                id=f"{run_id}_event_{i}",
                event=f"event_{i}",
                data={"sequence": i},
                timestamp=datetime.now(UTC),
            )
            await event_store.store_event(run_id, event)

        # Get events since sequence 3 (should get events 4 and 5)
        last_event_id = f"{run_id}_event_3"
        events_since = await event_store.get_events_since(run_id, last_event_id)

        assert len(events_since) == 2
        assert events_since[0].data["sequence"] == 4
        assert events_since[1].data["sequence"] == 5

    @pytest.mark.asyncio
    async def test_get_events_since_empty_result(self, event_store):
        """Test get_events_since when no events exist after last_event_id"""
        run_id = "integration-test-run-004"

        # Store only 2 events
        for i in range(1, 3):
            event = SSEEvent(
                id=f"{run_id}_event_{i}",
                event=f"event_{i}",
                data={"sequence": i},
                timestamp=datetime.now(UTC),
            )
            await event_store.store_event(run_id, event)

        # Try to get events after the last one
        last_event_id = f"{run_id}_event_2"
        events_since = await event_store.get_events_since(run_id, last_event_id)

        assert events_since == []

    @pytest.mark.asyncio
    async def test_cleanup_events_removes_specific_run(self, event_store):
        """Test that cleanup removes only events for specified run"""
        run_id_1 = "integration-test-run-005"
        run_id_2 = "integration-test-run-006"

        # Store events for both runs
        for run_id in [run_id_1, run_id_2]:
            for i in range(1, 3):
                event = SSEEvent(
                    id=f"{run_id}_event_{i}",
                    event=f"event_{i}",
                    data={"run": run_id, "sequence": i},
                    timestamp=datetime.now(UTC),
                )
                await event_store.store_event(run_id, event)

        # Verify both runs have events
        events_1_before = await event_store.get_all_events(run_id_1)
        events_2_before = await event_store.get_all_events(run_id_2)
        assert len(events_1_before) == 2
        assert len(events_2_before) == 2

        # Cleanup run 1
        await event_store.cleanup_events(run_id_1)

        # Verify only run 1 events are removed
        events_1_after = await event_store.get_all_events(run_id_1)
        events_2_after = await event_store.get_all_events(run_id_2)
        assert len(events_1_after) == 0
        assert len(events_2_after) == 2

    @pytest.mark.asyncio
    async def test_get_run_info_complete_run(self, event_store):
        """Test get_run_info for a complete run with multiple events"""
        run_id = "integration-test-run-007"

        # Store 5 events (sequences 1-5)
        for i in range(1, 6):
            event = SSEEvent(
                id=f"{run_id}_event_{i}",
                event=f"event_{i}",
                data={"sequence": i},
                timestamp=datetime.now(UTC),
            )
            await event_store.store_event(run_id, event)

        info = await event_store.get_run_info(run_id)

        assert info is not None
        assert info["run_id"] == run_id
        assert info["event_count"] == 5  # 5 - 1 + 1
        assert info["last_event_id"] == f"{run_id}_event_5"
        assert "last_event_time" in info

    @pytest.mark.asyncio
    async def test_get_run_info_single_event(self, event_store):
        """Test get_run_info for run with single event"""
        run_id = "integration-test-run-008"

        # Store single event with sequence 1
        event = SSEEvent(
            id=f"{run_id}_event_1",
            event="single_event",
            data={"type": "single"},
            timestamp=datetime.now(UTC),
        )
        await event_store.store_event(run_id, event)

        info = await event_store.get_run_info(run_id)

        assert info is not None
        assert info["run_id"] == run_id
        assert info["event_count"] == 1  # Expect event_count to be 1 for a single event
        assert info["last_event_id"] == f"{run_id}_event_1"

    @pytest.mark.asyncio
    async def test_get_run_info_no_events(self, event_store):
        """Test get_run_info when no events exist"""
        run_id = "nonexistent-run"

        info = await event_store.get_run_info(run_id)

        assert info is None

    @pytest.mark.asyncio
    async def test_concurrent_event_storage(self, event_store):
        """Test concurrent storage of events from multiple runs"""
        run_ids = [f"concurrent-run-{i}" for i in range(5)]

        async def store_events_for_run(run_id):
            """Store 3 events for a given run"""
            for i in range(1, 4):
                event = SSEEvent(
                    id=f"{run_id}_event_{i}",
                    event=f"concurrent_event_{i}",
                    data={"run": run_id, "seq": i},
                    timestamp=datetime.now(UTC),
                )
                await event_store.store_event(run_id, event)

        # Store events concurrently for all runs
        tasks = [store_events_for_run(run_id) for run_id in run_ids]
        await asyncio.gather(*tasks)

        # Verify all events were stored correctly
        for run_id in run_ids:
            events = await event_store.get_all_events(run_id)
            assert len(events) == 3

            # Verify sequences are correct
            for i, event in enumerate(events, 1):
                assert event.data["run"] == run_id
                assert event.data["seq"] == i

    @pytest.mark.asyncio
    async def test_event_persistence_across_instances(self, event_store):
        """Test that events persist across different EventStore instances"""
        run_id = "persistence-test-run"

        # Store events with first instance
        for i in range(1, 4):
            event = SSEEvent(
                id=f"{run_id}_event_{i}",
                event=f"persistence_event_{i}",
                data={"persistent": True, "seq": i},
                timestamp=datetime.now(UTC),
            )
            await event_store.store_event(run_id, event)

        # Create new instance and verify it can read the same events
        new_event_store = EventStore()
        events = await new_event_store.get_all_events(run_id)

        assert len(events) == 3
        for i, event in enumerate(events, 1):
            assert event.data["persistent"] is True
            assert event.data["seq"] == i

    @pytest.mark.asyncio
    async def test_complex_data_storage_and_retrieval(self, event_store):
        """Test storage and retrieval of complex JSON data"""
        run_id = "complex-data-run"

        complex_data = {
            "nested": {
                "array": [1, 2, {"deep": "value"}],
                "boolean": True,
                "null": None,
                "number": 42.5,
            },
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": {"version": "1.0", "tags": ["test", "complex", "json"]},
        }

        event = SSEEvent(
            id=f"{run_id}_event_1",
            event="complex_data",
            data=complex_data,
            timestamp=datetime.now(UTC),
        )

        # Store complex event
        await event_store.store_event(run_id, event)

        # Retrieve and verify
        events = await event_store.get_all_events(run_id)
        assert len(events) == 1

        retrieved_data = events[0].data

        # Verify complex structure is preserved
        assert retrieved_data["nested"]["array"] == [1, 2, {"deep": "value"}]
        assert retrieved_data["nested"]["boolean"] is True
        assert retrieved_data["nested"]["null"] is None
        assert retrieved_data["nested"]["number"] == 42.5
        assert retrieved_data["metadata"]["tags"] == ["test", "complex", "json"]

"""Integration tests for EventStore service with real database"""

import asyncio
import sys
from datetime import UTC, datetime

import pytest

from aegra_api.core.sse import SSEEvent
from aegra_api.services.event_store import EventStore
from aegra_api.settings import settings

# Fix Windows event loop policy for psycopg3 compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def database_available():
    """Check if database is available for integration tests"""
    import structlog

    logger = structlog.get_logger(__name__)

    try:
        # Use psycopg (psycopg3) directly instead of SQLAlchemy sync engine
        # This matches what the application actually uses
        import psycopg

        # Parse the database URL to get connection parameters
        db_url = settings.db.database_url_sync
        # Remove postgresql:// prefix and parse
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "", 1)

        # Extract connection parts
        parts = db_url.split("@")
        if len(parts) != 2:
            raise ValueError(f"Invalid database URL format: {db_url}")

        auth, host_db = parts
        user, password = auth.split(":")
        host_port, database = host_db.split("/")
        if ":" in host_port:
            host, port = host_port.split(":")
        else:
            host = host_port
            port = "5432"

        # Test connection with psycopg3
        with (
            psycopg.connect(
                host=host,
                port=int(port),
                user=user,
                password=password,
                dbname=database,
                connect_timeout=5,
            ) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT 1")
            cur.fetchone()

        logger.info("Database connection successful for integration tests")
        yield True
    except Exception as e:
        logger.warning(
            f"Database not available for integration tests: {e}. "
            "These tests require a running PostgreSQL database. "
            "Set POSTGRES_* environment variables or ensure database is running."
        )
        yield False


@pytest.fixture
def clean_event_store_tables(database_available):
    """Clean up event store tables before and after tests"""
    import psycopg

    if not database_available:
        pytest.skip("Database not available for integration tests")

    # Parse database URL
    db_url = settings.db.database_url_sync
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "", 1)

    parts = db_url.split("@")
    auth, host_db = parts
    user, password = auth.split(":")
    host_port, database = host_db.split("/")
    if ":" in host_port:
        host, port = host_port.split(":")
    else:
        host = host_port
        port = "5432"

    # Clean up before test
    with psycopg.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        dbname=database,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM run_events")
        conn.commit()

    yield

    # Clean up after test
    with psycopg.connect(
        host=host,
        port=int(port),
        user=user,
        password=password,
        dbname=database,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM run_events")
        conn.commit()


@pytest.fixture
async def event_store(clean_event_store_tables):
    """Create EventStore instance with real database"""
    from unittest.mock import patch

    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    # Create a real async connection pool for testing
    # EventStore uses db_manager.lg_pool which is an AsyncConnectionPool
    # Use open=False and open explicitly to avoid RuntimeError
    # Set row_factory=dict_row to match db_manager configuration
    test_pool = AsyncConnectionPool(
        conninfo=settings.db.database_url_sync,
        min_size=1,
        max_size=2,
        open=False,
        kwargs={"row_factory": dict_row},  # Return dicts instead of tuples
    )

    # Open the pool explicitly
    await test_pool.open()

    # Patch db_manager.lg_pool to use our test pool
    with patch(
        "aegra_api.services.event_store.db_manager.lg_pool",
        test_pool,
    ):
        yield EventStore()

    # Cleanup: close the test pool
    from contextlib import suppress

    with suppress(Exception):
        await test_pool.close()  # Ignore cleanup errors


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

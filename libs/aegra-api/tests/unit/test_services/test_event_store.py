"""Unit tests for EventStore service"""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from aegra_api.core.sse import SSEEvent
from aegra_api.services.event_store import EventStore, store_sse_event


class TestEventStore:
    """Unit tests for EventStore class (Database interactions)"""

    @pytest.fixture
    def mock_cursor(self):
        """Mock database cursor"""
        cursor = AsyncMock()
        return cursor

    @pytest.fixture
    def mock_conn(self, mock_cursor):
        """Mock database connection"""
        # IMPORTANT: mock_conn must be a Mock (not AsyncMock) because .cursor()
        # is a synchronous method that returns an asynchronous context manager.
        conn = Mock()

        # Configure .cursor() to return an object with __aenter__
        cursor_ctx = Mock()
        cursor_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
        cursor_ctx.__aexit__ = AsyncMock(return_value=None)

        conn.cursor.return_value = cursor_ctx
        return conn

    @pytest.fixture
    def mock_pool(self, mock_conn):
        """Mock Psycopg Connection Pool"""
        # IMPORTANT: mock_pool must be a Mock (not AsyncMock) because .connection()
        # is a synchronous method that returns an asynchronous context manager.
        pool = Mock()

        # Configure .connection() to return an object with __aenter__
        connection_ctx = Mock()
        connection_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        connection_ctx.__aexit__ = AsyncMock(return_value=None)

        pool.connection.return_value = connection_ctx
        return pool

    @pytest.fixture
    def event_store(self):
        """Create EventStore instance"""
        return EventStore()

    @pytest.mark.asyncio
    async def test_store_event_success(self, event_store, mock_pool, mock_cursor):
        """Test successful event storage"""
        # Setup
        run_id = "test-run-123"
        event = SSEEvent(
            id=f"{run_id}_event_1",
            event="test_event",
            data={"key": "value"},
            timestamp=datetime.now(UTC),
        )

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            # Patch the shared lg_pool with our correctly configured mock
            mock_db_manager.lg_pool = mock_pool

            # Execute
            await event_store.store_event(run_id, event)

            # Assert
            mock_cursor.execute.assert_called_once()

            # Verify the SQL call
            call_args = mock_cursor.execute.call_args
            assert len(call_args[0]) == 2  # statement and params
            stmt, params = call_args[0]

            # Check parameters
            assert params["id"] == event.id
            assert params["run_id"] == run_id
            assert params["seq"] == 1
            assert params["event"] == event.event

            # Verify data adaptation for Jsonb (Psycopg 3 uses .obj attribute)
            assert params["data"].obj == event.data

    @pytest.mark.asyncio
    async def test_store_event_sequence_extraction_edge_cases(self, event_store, mock_pool, mock_cursor):
        """Test sequence extraction from various event ID formats"""
        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool

            test_cases = [
                ("run_123_event_42", 42),
                ("simple_event_0", 0),
                ("run_event_999", 999),
                ("broken_format", 0),
                ("run_event_", 0),
            ]

            for event_id, expected_seq in test_cases:
                event = SSEEvent(id=event_id, event="test", data={})
                await event_store.store_event("test-run", event)

                call_args = mock_cursor.execute.call_args
                params = call_args[0][1]
                assert params["seq"] == expected_seq, f"Failed for event_id: {event_id}"

    @pytest.mark.asyncio
    async def test_store_event_database_error(self, event_store, mock_pool, mock_cursor):
        """Test handling of database errors during event storage"""
        event = SSEEvent(id="test_event_1", event="test", data={})

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            mock_cursor.execute.side_effect = RuntimeError("Database connection failed")

            with pytest.raises(RuntimeError):
                await event_store.store_event("test-run", event)

    @pytest.mark.asyncio
    async def test_get_events_since_success(self, event_store, mock_pool, mock_cursor):
        """Test successful event retrieval with last_event_id"""
        run_id = "test-run-123"
        last_event_id = f"{run_id}_event_5"

        # Mock result rows (as dicts because row_factory=dict_row)
        mock_rows = [
            {
                "id": f"{run_id}_event_6",
                "event": "event6",
                "data": {"seq": 6},
                "created_at": datetime.now(UTC),
            },
            {
                "id": f"{run_id}_event_7",
                "event": "event7",
                "data": {"seq": 7},
                "created_at": datetime.now(UTC),
            },
        ]
        mock_cursor.fetchall.return_value = mock_rows

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool

            events = await event_store.get_events_since(run_id, last_event_id)

            assert len(events) == 2
            assert events[0].id == f"{run_id}_event_6"

            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            assert params["run_id"] == run_id
            assert params["last_seq"] == 5

    @pytest.mark.asyncio
    async def test_get_events_since_no_events(self, event_store, mock_pool, mock_cursor):
        """Test retrieval when no events exist after last_event_id"""
        mock_cursor.fetchall.return_value = []

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            events = await event_store.get_events_since("test-run", "test_event_1")
            assert events == []

    @pytest.mark.asyncio
    async def test_get_events_since_invalid_last_event_id(self, event_store, mock_pool, mock_cursor):
        """Test handling of malformed last_event_id"""
        mock_cursor.fetchall.return_value = []

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            await event_store.get_events_since("test-run", "malformed_id")

            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            assert params["last_seq"] == -1

    @pytest.mark.asyncio
    async def test_get_all_events_success(self, event_store, mock_pool, mock_cursor):
        """Test successful retrieval of all events for a run"""
        run_id = "test-run-123"
        mock_rows = [
            {
                "id": f"{run_id}_event_1",
                "event": "start",
                "data": {"type": "start"},
                "created_at": datetime.now(UTC),
            },
        ]
        mock_cursor.fetchall.return_value = mock_rows

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            events = await event_store.get_all_events(run_id)
            assert len(events) == 1
            assert events[0].event == "start"

    @pytest.mark.asyncio
    async def test_cleanup_events_success(self, event_store, mock_pool, mock_cursor):
        """Test successful event cleanup for a specific run"""
        run_id = "test-run-123"
        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            await event_store.cleanup_events(run_id)

            call_args = mock_cursor.execute.call_args
            params = call_args[0][1]
            assert params["run_id"] == run_id

    @pytest.mark.asyncio
    async def test_get_run_info_success(self, event_store, mock_pool, mock_cursor):
        """Test successful retrieval of run information"""
        run_id = "test-run-123"
        # Mock sequence range query
        mock_range_result = {"last_seq": 5, "first_seq": 1}
        # Mock last event query
        mock_last_result = {"id": f"{run_id}_event_5", "created_at": datetime.now(UTC)}

        mock_cursor.fetchone.side_effect = [mock_range_result, mock_last_result]

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            info = await event_store.get_run_info(run_id)

            assert info is not None
            assert info["event_count"] == 5

    @pytest.mark.asyncio
    async def test_get_run_info_no_events(self, event_store, mock_pool, mock_cursor):
        """Test run info when no events exist"""
        mock_cursor.fetchone.return_value = None
        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            info = await event_store.get_run_info("empty-run")
            assert info is None

    @pytest.mark.asyncio
    async def test_get_run_info_single_event(self, event_store, mock_pool, mock_cursor):
        """Test run info with single event"""
        mock_range_result = {"last_seq": 1, "first_seq": None}
        mock_last_result = {"id": "run_event_1", "created_at": datetime.now(UTC)}
        mock_cursor.fetchone.side_effect = [mock_range_result, mock_last_result]

        with patch("aegra_api.services.event_store.db_manager") as mock_db_manager:
            mock_db_manager.lg_pool = mock_pool
            info = await event_store.get_run_info("single-event-run")
            assert info is not None
            assert info["event_count"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_task_management(self, event_store):
        """Test cleanup task start and stop functionality"""
        assert event_store._cleanup_task is None
        await event_store.start_cleanup_task()
        assert event_store._cleanup_task is not None
        await event_store.stop_cleanup_task()
        assert event_store._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_cleanup_loop_functionality(self, event_store, mock_pool, mock_cursor):
        """Test the cleanup loop functionality"""
        with (
            patch.object(event_store, "CLEANUP_INTERVAL", 0.01),
            patch("aegra_api.services.event_store.db_manager") as mock_db_manager,
        ):
            mock_db_manager.lg_pool = mock_pool

            # Start and then wait a bit to allow the loop to run
            await event_store.start_cleanup_task()
            await asyncio.sleep(0.05)
            await event_store.stop_cleanup_task()

        assert mock_cursor.execute.called, "Cleanup loop did not execute SQL"


class TestStoreSSEEvent:
    """Unit tests for store_sse_event helper function"""

    @pytest.fixture
    def mock_event_store(self):
        """Mock EventStore instance"""
        return Mock()

    @pytest.mark.asyncio
    async def test_store_sse_event_success(self, mock_event_store):
        """Test successful SSE event storage"""
        mock_event_store.store_event = AsyncMock()

        with patch("aegra_api.services.event_store.event_store", mock_event_store):
            run_id = "test-run-123"
            event_id = f"{run_id}_event_1"
            event_type = "test_event"
            data = {"key": "value", "complex": datetime.now(UTC)}

            result = await store_sse_event(run_id, event_id, event_type, data)

            # Verify event_store.store_event was called
            mock_event_store.store_event.assert_called_once()
            call_args = mock_event_store.store_event.call_args
            stored_run_id, stored_event = call_args[0]

            assert stored_run_id == run_id
            assert isinstance(stored_event, SSEEvent)
            assert stored_event.id == event_id
            assert stored_event.event == event_type
            # Data should be JSON-serializable (datetime converted to string)
            json_str = json.dumps(stored_event.data)
            parsed_back = json.loads(json_str)
            assert parsed_back["key"] == "value"
            assert "complex" in parsed_back  # datetime should be serialized

            # Verify return value
            assert result == stored_event

    @pytest.mark.asyncio
    async def test_store_sse_event_json_serialization(self):
        """Test that complex objects are properly JSON serialized"""
        with patch("aegra_api.services.event_store.event_store") as mock_event_store:
            mock_event_store.store_event = AsyncMock()

            # Data with non-JSON serializable object
            data = {
                "datetime": datetime.now(UTC),
                "nested": {"complex": datetime(2023, 1, 1, tzinfo=UTC)},
                "normal": "string",
            }

            await store_sse_event("run-123", "event-1", "test", data)

            # Verify the event was stored with serialized data
            call_args = mock_event_store.store_event.call_args
            _, stored_event = call_args[0]

            # Data should be JSON serializable (datetime converted to string)
            json_str = json.dumps(stored_event.data)
            parsed_back = json.loads(json_str)
            assert "datetime" in parsed_back
            assert "nested" in parsed_back
            assert parsed_back["normal"] == "string"

    @pytest.mark.asyncio
    async def test_store_sse_event_serialization_fallback(self):
        """Test fallback behavior when JSON serialization fails"""
        with patch("aegra_api.services.event_store.event_store") as mock_event_store:
            mock_event_store.store_event = AsyncMock()

            # Create an object that can't be serialized even with custom serializer
            # by making the serializer itself fail
            class UnserializableClass:
                def __str__(self):
                    # Make str() fail to force the fallback
                    raise RuntimeError("Cannot stringify")

            data = {"unserializable": UnserializableClass()}

            await store_sse_event("run-123", "event-1", "test", data)

            # Should fallback to string representation
            call_args = mock_event_store.store_event.call_args
            _, stored_event = call_args[0]

            # The stored event should have fallback data format
            assert "raw" in stored_event.data
            assert isinstance(stored_event.data["raw"], str)
            # The raw string should contain some representation of the data
            assert len(stored_event.data["raw"]) > 0

"""Unit tests for EventStore service"""

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.agent_server.core.sse import SSEEvent
from src.agent_server.services.event_store import EventStore, store_sse_event


class TestEventStore:
    """Unit tests for EventStore class"""

    @pytest.fixture
    def mock_engine(self):
        """Mock SQLAlchemy engine"""
        return Mock()

    @pytest.fixture
    def mock_conn(self):
        """Mock database connection"""
        return AsyncMock()

    @pytest.fixture
    def event_store(self):
        """Create EventStore instance"""
        return EventStore()

    @pytest.mark.asyncio
    async def test_store_event_success(self, event_store, mock_conn):
        """Test successful event storage"""
        # Setup
        run_id = "test-run-123"
        event = SSEEvent(
            id=f"{run_id}_event_1",
            event="test_event",
            data={"key": "value"},
            timestamp=datetime.now(UTC),
        )

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )
            mock_conn.execute = AsyncMock()

            # Execute
            await event_store.store_event(run_id, event)

            # Assert
            mock_conn.execute.assert_called_once()

            # Verify the SQL call
            call_args = mock_conn.execute.call_args
            assert len(call_args[0]) == 2  # statement and params
            stmt, params = call_args[0]

            # Check parameters
            assert params["id"] == event.id
            assert params["run_id"] == run_id
            assert params["seq"] == 1  # extracted from event ID
            assert params["event"] == event.event
            assert params["data"] == event.data

    @pytest.mark.asyncio
    async def test_store_event_sequence_extraction_edge_cases(
        self, event_store, mock_conn
    ):
        """Test sequence extraction from various event ID formats"""
        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )
            mock_conn.execute = AsyncMock()

            test_cases = [
                ("run_123_event_42", 42),  # Normal case
                ("simple_event_0", 0),  # Zero sequence
                ("run_event_999", 999),  # Large sequence
                ("broken_format", 0),  # No sequence found, defaults to 0
                ("run_event_", 0),  # Empty sequence, defaults to 0
            ]

            for event_id, expected_seq in test_cases:
                event = SSEEvent(id=event_id, event="test", data={})
                await event_store.store_event("test-run", event)

                # Check that the correct sequence was extracted
                call_args = mock_conn.execute.call_args
                params = call_args[0][1]  # Get params dict
                assert params["seq"] == expected_seq, f"Failed for event_id: {event_id}"

    @pytest.mark.asyncio
    async def test_store_event_database_error(self, event_store):
        """Test handling of database errors during event storage"""
        event = SSEEvent(id="test_event_1", event="test", data={})

        # Simulate database error
        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.side_effect = SQLAlchemyError(
                "Database connection failed"
            )

            # Execute and assert
            with pytest.raises(SQLAlchemyError):
                await event_store.store_event("test-run", event)

    @pytest.mark.asyncio
    async def test_get_events_since_success(self, event_store, mock_conn):
        """Test successful event retrieval with last_event_id"""
        run_id = "test-run-123"
        last_event_id = f"{run_id}_event_5"

        # Mock the result rows
        mock_rows = [
            Mock(
                id=f"{run_id}_event_6",
                event="event6",
                data={"seq": 6},
                created_at=datetime.now(UTC),
            ),
            Mock(
                id=f"{run_id}_event_7",
                event="event7",
                data={"seq": 7},
                created_at=datetime.now(UTC),
            ),
        ]
        mock_result = Mock()
        mock_result.fetchall.return_value = mock_rows
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )

            # Execute
            events = await event_store.get_events_since(run_id, last_event_id)

            # Assert
            assert len(events) == 2
            assert all(isinstance(event, SSEEvent) for event in events)
            assert events[0].id == f"{run_id}_event_6"
            assert events[1].id == f"{run_id}_event_7"

            # Verify query parameters
            call_args = mock_conn.execute.call_args
            params = call_args[0][1]
            assert params["run_id"] == run_id
            assert params["last_seq"] == 5  # extracted from last_event_id

    @pytest.mark.asyncio
    async def test_get_events_since_no_events(self, event_store, mock_conn):
        """Test retrieval when no events exist after last_event_id"""
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )

            events = await event_store.get_events_since("test-run", "test_event_1")

            assert events == []

    @pytest.mark.asyncio
    async def test_get_events_since_invalid_last_event_id(self, event_store, mock_conn):
        """Test handling of malformed last_event_id"""
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )

            # Should default to last_seq = -1 for malformed IDs
            await event_store.get_events_since("test-run", "malformed_id")

            call_args = mock_conn.execute.call_args
            params = call_args[0][1]
            assert params["last_seq"] == -1

    @pytest.mark.asyncio
    async def test_get_all_events_success(self, event_store, mock_conn):
        """Test successful retrieval of all events for a run"""
        run_id = "test-run-123"

        mock_rows = [
            Mock(
                id=f"{run_id}_event_1",
                event="start",
                data={"type": "start"},
                created_at=datetime.now(UTC),
            ),
            Mock(
                id=f"{run_id}_event_2",
                event="chunk",
                data={"data": "chunk1"},
                created_at=datetime.now(UTC),
            ),
            Mock(
                id=f"{run_id}_event_3",
                event="end",
                data={"type": "end"},
                created_at=datetime.now(UTC),
            ),
        ]
        mock_result = Mock()
        mock_result.fetchall.return_value = mock_rows
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )

            events = await event_store.get_all_events(run_id)

            assert len(events) == 3
            assert events[0].event == "start"
            assert events[1].event == "chunk"
            assert events[2].event == "end"

            # Verify events are ordered by sequence
            call_args = mock_conn.execute.call_args
            sql_query = call_args[0][0]
            assert "ORDER BY seq ASC" in str(sql_query)

    @pytest.mark.asyncio
    async def test_cleanup_events_success(self, event_store, mock_conn):
        """Test successful event cleanup for a specific run"""
        run_id = "test-run-123"

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )
            mock_conn.execute = AsyncMock()

            await event_store.cleanup_events(run_id)

            # Verify the delete query was executed
            call_args = mock_conn.execute.call_args
            params = call_args[0][1]
            assert params["run_id"] == run_id

    @pytest.mark.asyncio
    async def test_get_run_info_success(self, event_store, mock_conn):
        """Test successful retrieval of run information"""
        run_id = "test-run-123"

        # Mock the sequence range query
        mock_range_result = Mock()
        mock_range_result.fetchone.return_value = Mock(last_seq=5, first_seq=1)

        # Mock the last event query
        mock_last_result = Mock()
        mock_last_result.fetchone.return_value = Mock(
            id=f"{run_id}_event_5", created_at=datetime.now(UTC)
        )

        mock_conn.execute = AsyncMock(side_effect=[mock_range_result, mock_last_result])

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )

            info = await event_store.get_run_info(run_id)

            assert info is not None
            assert info["run_id"] == run_id
            assert info["event_count"] == 5  # 5 - 1 + 1
            assert info["last_event_id"] == f"{run_id}_event_5"
            assert "last_event_time" in info

    @pytest.mark.asyncio
    async def test_get_run_info_no_events(self, event_store, mock_conn):
        """Test run info when no events exist"""
        mock_result = Mock()
        mock_result.fetchone.return_value = None  # No events
        mock_conn.execute = AsyncMock(return_value=mock_result)

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )

            info = await event_store.get_run_info("empty-run")

            assert info is None

    @pytest.mark.asyncio
    async def test_get_run_info_single_event(self, event_store, mock_conn):
        """Test run info with single event (first_seq is None)"""
        # Mock range query returning single event
        mock_range_result = Mock()
        mock_range_result.fetchone.return_value = Mock(last_seq=1, first_seq=None)

        # Mock last event query
        mock_last_result = Mock()
        mock_last_result.fetchone.return_value = Mock(
            id="run_event_1", created_at=datetime.now(UTC)
        )

        mock_conn.execute = AsyncMock(side_effect=[mock_range_result, mock_last_result])

        with patch(
            "src.agent_server.services.event_store.db_manager"
        ) as mock_db_manager:
            mock_db_manager.get_engine.return_value.begin.return_value.__aenter__ = (
                AsyncMock(return_value=mock_conn)
            )
            mock_db_manager.get_engine.return_value.begin.return_value.__aexit__ = (
                AsyncMock(return_value=None)
            )

            info = await event_store.get_run_info("single-event-run")

            assert info is not None
            assert info["event_count"] == 0  # When first_seq is None, event_count is 0

    @pytest.mark.asyncio
    async def test_cleanup_task_management(self, event_store):
        """Test cleanup task start and stop functionality"""
        # Initially no task
        assert event_store._cleanup_task is None

        # Start task
        await event_store.start_cleanup_task()
        assert event_store._cleanup_task is not None
        assert not event_store._cleanup_task.done()

        # Stop task
        await event_store.stop_cleanup_task()
        assert event_store._cleanup_task.done()

        # Starting again should work
        await event_store.start_cleanup_task()
        assert event_store._cleanup_task is not None
        assert not event_store._cleanup_task.done()

        # Stop again
        await event_store.stop_cleanup_task()
        assert event_store._cleanup_task.done()

    @pytest.mark.asyncio
    async def test_cleanup_loop_functionality(
        self, event_store, mock_engine, mock_conn
    ):
        """Test the cleanup loop functionality"""
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_conn.execute = AsyncMock()

        with (
            patch.object(event_store, "CLEANUP_INTERVAL", 0.01),
            patch(
                "src.agent_server.services.event_store.db_manager"
            ) as mock_db_manager,
        ):
            mock_db_manager.get_engine.return_value = mock_engine

            # Start the cleanup task
            await event_store.start_cleanup_task()

            # Wait for the loop to run at least once
            await asyncio.sleep(0.05)

            # Stop the task
            await event_store.stop_cleanup_task()

        # Verify cleanup was attempted (connection was used)
        assert mock_conn.execute.called, (
            "Cleanup loop did not attempt to execute cleanup SQL"
        )


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

        with patch(
            "src.agent_server.services.event_store.event_store", mock_event_store
        ):
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
        with patch(
            "src.agent_server.services.event_store.event_store"
        ) as mock_event_store:
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
        with patch(
            "src.agent_server.services.event_store.event_store"
        ) as mock_event_store:
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

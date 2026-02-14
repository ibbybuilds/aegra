"""Integration tests for streaming error handling.

Tests verify that errors during graph execution are properly caught,
sent to frontend via SSE, and stored for replay.
"""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from aegra_api.api.runs import execute_run_async
from aegra_api.models import User
from aegra_api.services.broker import RunBroker


@pytest.mark.asyncio
class TestStreamingErrorHandling:
    """Test error handling during streaming execution"""

    @pytest.fixture
    def mock_user(self) -> User:
        return User(identity="test-user", scopes=[])

    @pytest.fixture
    def run_id(self) -> str:
        return str(uuid4())

    @pytest.fixture
    def thread_id(self) -> str:
        return str(uuid4())

    async def test_error_during_event_processing_sent_to_frontend(self, mock_user: User, run_id: str, thread_id: str):
        """Test that errors during event processing are caught and sent immediately"""
        graph_id = "test-graph"

        # Create a broker to capture events
        broker = RunBroker(run_id)
        from aegra_api.services.broker import broker_manager

        # Store broker directly for testing
        if not hasattr(broker_manager, "_brokers"):
            broker_manager._brokers = {}
        broker_manager._brokers[run_id] = broker

        # Mock graph that yields events, then fails during processing
        mock_graph = MagicMock()
        mock_graph.__aenter__ = AsyncMock(return_value=mock_graph)
        mock_graph.__aexit__ = AsyncMock(return_value=None)

        async def failing_stream() -> AsyncIterator:
            """Stream that yields one event then raises error"""
            yield ("values", {"step": 1})
            # Simulate error during event processing
            raise ValueError("Graph execution failed")

        with (
            patch("aegra_api.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=failing_stream(),
            ),
            patch("aegra_api.api.runs.update_run_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs._get_session_maker") as mock_session_maker,
        ):
            mock_lg_service.return_value.get_graph.return_value.__aenter__ = AsyncMock(return_value=mock_graph)
            mock_lg_service.return_value.get_graph.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session_maker.return_value = lambda: mock_session

            # Execute run - error is handled internally (no re-raise from background tasks)
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
                config={},
                context={},
                stream_mode=["values"],
            )

            # Verify error event was sent to broker
            events_received = []
            try:
                async for event_id, raw_event in broker.aiter():
                    events_received.append((event_id, raw_event))
                    # Stop after a few events
                    if len(events_received) >= 5:
                        break
            except Exception:
                pass

            # Should have received:
            # 1. The values event
            # 2. An error event
            # 3. An end event
            assert len(events_received) >= 1, "Should receive at least one event"

            # Check for error event
            error_events = [evt for _, evt in events_received if isinstance(evt, tuple) and evt[0] == "error"]
            assert len(error_events) > 0, "Error event should be sent to broker"

            error_event = error_events[0]
            assert error_event[0] == "error"
            assert "error" in error_event[1]
            assert "message" in error_event[1]
            assert "Graph execution failed" in str(error_event[1]["message"])

    async def test_error_stored_for_replay(self, mock_user: User, run_id: str, thread_id: str):
        """Test that error events are stored for replay support"""
        graph_id = "test-graph"

        async def failing_stream() -> AsyncIterator:
            yield ("values", {"step": 1})
            raise RuntimeError("Storage test error")

        # Mock store_sse_event to capture calls
        stored_error_events = []

        async def mock_store_sse_event(run_id_param, event_id, event_type, data):
            if event_type == "error":
                stored_error_events.append(
                    {
                        "run_id": run_id_param,
                        "event_id": event_id,
                        "event_type": event_type,
                        "data": data,
                    }
                )

        with (
            patch("aegra_api.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=failing_stream(),
            ),
            patch("aegra_api.api.runs.update_run_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs._get_session_maker") as mock_session_maker,
            patch(
                "aegra_api.services.streaming_service.store_sse_event",
                side_effect=mock_store_sse_event,
            ),
        ):
            mock_graph = MagicMock()
            mock_lg_service.return_value.get_graph.return_value.__aenter__ = AsyncMock(return_value=mock_graph)
            mock_lg_service.return_value.get_graph.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session_maker.return_value = lambda: mock_session

            # Execute run - error is handled internally (no re-raise from background tasks)
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
                config={},
                context={},
                stream_mode=["values"],
            )

            # Wait a bit for async operations to complete
            await asyncio.sleep(0.2)

            # Verify error was stored
            assert len(stored_error_events) > 0, "Error event should be stored for replay"
            error_event = stored_error_events[0]
            assert error_event["event_type"] == "error"
            assert error_event["data"]["error"] == "RuntimeError"
            assert "Storage test error" in error_event["data"]["message"]

    async def test_error_type_preserved(self, mock_user: User, run_id: str, thread_id: str):
        """Test that error type is correctly preserved and sent"""
        graph_id = "test-graph"

        async def failing_stream():
            """Async generator that raises ValueError"""
            raise ValueError("Type preservation test")
            yield  # This will never be reached but makes it an async generator

        broker = RunBroker(run_id)
        from aegra_api.services.broker import broker_manager

        # Store broker directly for testing
        if not hasattr(broker_manager, "_brokers"):
            broker_manager._brokers = {}
        broker_manager._brokers[run_id] = broker

        with (
            patch("aegra_api.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.api.runs.stream_graph_events",
            ) as mock_stream_graph,
            patch("aegra_api.api.runs.update_run_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs._get_session_maker") as mock_session_maker,
        ):
            # Set up the mock to return the async generator
            mock_stream_graph.return_value = failing_stream()

            mock_graph = MagicMock()
            mock_lg_service.return_value.get_graph.return_value.__aenter__ = AsyncMock(return_value=mock_graph)
            mock_lg_service.return_value.get_graph.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session_maker.return_value = lambda: mock_session

            # Error is handled internally (no re-raise from background tasks)
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
                config={},
                context={},
                stream_mode=["values"],
            )

            # Check error event has correct type
            events_received = []
            try:
                async for event_id, raw_event in broker.aiter():
                    events_received.append((event_id, raw_event))
                    if len(events_received) >= 3:
                        break
            except Exception:
                pass

            error_events = [evt for _, evt in events_received if isinstance(evt, tuple) and evt[0] == "error"]
            assert len(error_events) > 0, "Should receive error event"

            error_event = error_events[0]
            assert error_event[1]["error"] == "ValueError"
            assert error_event[1]["message"] == "Type preservation test"

    async def test_multiple_errors_only_send_once(self, mock_user: User, run_id: str, thread_id: str):
        """Test that if error is caught in inner handler, outer handler doesn't duplicate"""
        graph_id = "test-graph"

        async def failing_stream() -> AsyncIterator:
            yield ("values", {"step": 1})
            raise KeyError("Single error test")

        broker = RunBroker(run_id)
        from aegra_api.services.broker import broker_manager

        # Store broker directly for testing
        if not hasattr(broker_manager, "_brokers"):
            broker_manager._brokers = {}
        broker_manager._brokers[run_id] = broker

        with (
            patch("aegra_api.api.runs.get_langgraph_service") as mock_lg_service,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=failing_stream(),
            ),
            patch("aegra_api.api.runs.update_run_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
            patch("aegra_api.api.runs._get_session_maker") as mock_session_maker,
        ):
            mock_graph = MagicMock()
            mock_lg_service.return_value.get_graph.return_value.__aenter__ = AsyncMock(return_value=mock_graph)
            mock_lg_service.return_value.get_graph.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session_maker.return_value = lambda: mock_session

            # Error is handled internally (no re-raise from background tasks)
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
                config={},
                context={},
                stream_mode=["values"],
            )

            # Count error events - should only be one
            events_received = []
            try:
                async for event_id, raw_event in broker.aiter():
                    events_received.append((event_id, raw_event))
                    if len(events_received) >= 5:
                        break
            except Exception:
                pass

            error_events = [evt for _, evt in events_received if isinstance(evt, tuple) and evt[0] == "error"]
            # Should have exactly one error event (not duplicated)
            assert len(error_events) == 1, f"Expected 1 error event, got {len(error_events)}"

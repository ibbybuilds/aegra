"""Unit tests for streaming_service module"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegra_api.models import Run
from aegra_api.services.streaming_service import StreamingService


@pytest.mark.asyncio
class TestStreamingService:
    """Test StreamingService class"""

    async def test_next_event_counter(self) -> None:
        """Test event counter update logic"""
        service = StreamingService()
        run_id = "run-123"

        # Initial counter
        count = service._next_event_counter(run_id, "run-123_event_5")
        assert count == 5
        assert service.event_counters[run_id] == 5

        # Lower counter should be ignored
        count = service._next_event_counter(run_id, "run-123_event_3")
        assert count == 5
        assert service.event_counters[run_id] == 5

        # Higher counter should update
        count = service._next_event_counter(run_id, "run-123_event_10")
        assert count == 10
        assert service.event_counters[run_id] == 10

        # Malformed event id should handle gracefully
        count = service._next_event_counter(run_id, "invalid")
        assert count == 10  # Should remain unchanged

    async def test_put_to_broker(self) -> None:
        """Test putting event to broker"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "run-123_event_1"
        raw_event = {"data": "test"}

        mock_broker = AsyncMock()

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_or_create_broker.return_value = mock_broker

            await service.put_to_broker(run_id, event_id, raw_event)

            mock_manager.get_or_create_broker.assert_called_with(run_id)
            mock_broker.put.assert_awaited_with(event_id, raw_event)
            assert service.event_counters[run_id] == 1

    async def test_signal_run_cancelled(self) -> None:
        """Test signalling run cancellation"""
        service = StreamingService()
        run_id = "run-123"

        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False
        mock_broker.put = AsyncMock()

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_broker.return_value = mock_broker

            await service.signal_run_cancelled(run_id)

            # Should put end event
            mock_broker.put.assert_awaited()
            args = mock_broker.put.call_args
            assert args[0][1] == ("end", {"status": "interrupted"})

            # Should cleanup broker
            mock_manager.cleanup_broker.assert_called_with(run_id)

    async def test_signal_run_cancelled_skips_when_no_broker(self) -> None:
        """Test that signal_run_cancelled is a no-op when broker doesn't exist"""
        service = StreamingService()

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_broker.return_value = None

            await service.signal_run_cancelled("run-123")

            mock_manager.cleanup_broker.assert_not_called()

    async def test_signal_run_error(self) -> None:
        """Test signalling run error sends error event then end event"""
        service = StreamingService()
        run_id = "run-123"
        error_msg = "Something went wrong"
        error_type = "ValueError"

        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False
        mock_broker.put = AsyncMock()

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_broker.return_value = mock_broker

            await service.signal_run_error(run_id, error_msg, error_type)

            # Should put error event first, then end event
            assert mock_broker.put.await_count == 2
            call_args_list = mock_broker.put.call_args_list

            # First call should be error event
            first_call = call_args_list[0]
            event_type_val, event_data = first_call[0][1]
            assert event_type_val == "error"
            assert event_data["error"] == error_type
            assert event_data["message"] == error_msg

            # Second call should be end event
            second_call = call_args_list[1]
            end_type, end_data = second_call[0][1]
            assert end_type == "end"
            assert end_data["status"] == "error"

            # Should cleanup broker
            mock_manager.cleanup_broker.assert_called_with(run_id)

    async def test_signal_run_error_skips_when_no_broker(self) -> None:
        """Test that signal_run_error is a no-op when broker doesn't exist"""
        service = StreamingService()

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_broker.return_value = None

            await service.signal_run_error("run-123", "error msg")

            mock_manager.cleanup_broker.assert_not_called()

    async def test_signal_run_error_default_type(self) -> None:
        """Test signal_run_error with default error type"""
        service = StreamingService()
        run_id = "run-123"
        error_msg = "Generic error"

        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False
        mock_broker.put = AsyncMock()

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_broker.return_value = mock_broker

            await service.signal_run_error(run_id, error_msg)

            call_args = mock_broker.put.call_args_list[0]
            event_type_val, event_data = call_args[0][1]
            assert event_type_val == "error"
            assert event_data["error"] == "Error"
            assert event_data["message"] == error_msg

    async def test_stream_run_execution(self) -> None:
        """Test overall streaming execution with replay + live"""
        service = StreamingService()
        run = Run(
            run_id="run-123",
            status="running",
            user_id="user-1",
            thread_id="thread-1",
            assistant_id="agent",
            input={"message": "hello"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False
        # Replay returns 2 stored events
        mock_broker.replay = AsyncMock(
            return_value=[
                ("run-123_event_1", ("values", {"a": 1})),
                ("run-123_event_2", ("values", {"a": 2})),
            ]
        )

        async def mock_aiter() -> AsyncGenerator[tuple[str, Any], None]:
            yield "run-123_event_3", ("values", {"a": 3})
            yield "run-123_event_4", ("end", {"status": "success"})

        mock_broker.aiter = mock_aiter

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_or_create_broker.return_value = mock_broker
            mock_manager.get_broker.return_value = mock_broker
            service._convert_raw_to_sse = AsyncMock(side_effect=["sse1", "sse2", "sse3", "sse4"])  # type: ignore[assignment]

            events: list[str] = []
            async for event in service.stream_run_execution(run):
                events.append(event)

            assert len(events) == 4
            assert events == ["sse1", "sse2", "sse3", "sse4"]
            mock_broker.replay.assert_awaited_with(None)

    async def test_stream_run_execution_with_last_id(self) -> None:
        """Test streaming with last_event_id resume"""
        service = StreamingService()
        run = Run(
            run_id="run-123",
            status="running",
            user_id="user-1",
            thread_id="thread-1",
            assistant_id="agent",
            input={"message": "hello"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        last_id = "run-123_event_5"

        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False
        mock_broker.replay = AsyncMock(return_value=[])

        async def mock_aiter() -> AsyncGenerator[tuple[str, Any], None]:
            if False:
                yield

        mock_broker.aiter = mock_aiter

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_or_create_broker.return_value = mock_broker
            mock_manager.get_broker.return_value = mock_broker

            async for _ in service.stream_run_execution(run, last_event_id=last_id):
                pass

            # Should replay from last_id
            mock_broker.replay.assert_awaited_with(last_id)

    async def test_stream_skips_already_replayed_events(self) -> None:
        """Test that live events with sequence <= last replayed are skipped"""
        service = StreamingService()
        run = Run(
            run_id="run-123",
            status="running",
            user_id="user-1",
            thread_id="thread-1",
            assistant_id="agent",
            input={"message": "hello"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False
        mock_broker.replay = AsyncMock(return_value=[])

        async def mock_aiter() -> AsyncGenerator[tuple[str, Any], None]:
            # Event with sequence 3 should be skipped (last_event_id was event_5)
            yield "run-123_event_3", ("values", {"should": "skip"})
            yield "run-123_event_6", ("values", {"should": "include"})
            yield "run-123_event_7", ("end", {"status": "success"})

        mock_broker.aiter = mock_aiter

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_or_create_broker.return_value = mock_broker
            mock_manager.get_broker.return_value = mock_broker
            service._convert_raw_to_sse = AsyncMock(side_effect=["sse6", "sse7"])  # type: ignore[assignment]

            events: list[str] = []
            async for event in service.stream_run_execution(run, last_event_id="run-123_event_5"):
                events.append(event)

            # Only events after sequence 5 should be included
            assert len(events) == 2
            assert events == ["sse6", "sse7"]

    async def test_cancel_background_task(self) -> None:
        """Test cancelling background task"""
        service = StreamingService()
        run_id = "run-123"

        mock_task = MagicMock()
        mock_task.done.return_value = False

        with patch.dict("aegra_api.api.runs.active_runs", {run_id: mock_task}, clear=True):
            service._cancel_background_task(run_id)
            mock_task.cancel.assert_called_once()

    async def test_interrupt_run(self) -> None:
        """Test run interruption cancels task and signals to broker"""
        service = StreamingService()
        run_id = "run-123"

        with (
            patch.object(service, "_cancel_background_task") as mock_cancel,
            patch.object(service, "signal_run_error") as mock_signal,
        ):
            success = await service.interrupt_run(run_id)

            assert success is True
            mock_cancel.assert_called_once_with(run_id)
            mock_signal.assert_awaited_with(run_id, "Run was interrupted")

    async def test_cancel_run(self) -> None:
        """Test run cancellation cancels task and signals to broker"""
        service = StreamingService()
        run_id = "run-123"

        with (
            patch.object(service, "_cancel_background_task") as mock_cancel,
            patch.object(service, "signal_run_cancelled") as mock_signal,
        ):
            success = await service.cancel_run(run_id)

            assert success is True
            mock_cancel.assert_called_once_with(run_id)
            mock_signal.assert_awaited_with(run_id)

    async def test_is_run_streaming(self) -> None:
        """Test fetching if run is streaming"""
        service = StreamingService()

        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_broker.return_value = mock_broker
            assert service.is_run_streaming("run-1") is True

            mock_broker.is_finished.return_value = True
            assert service.is_run_streaming("run-1") is False

            mock_manager.get_broker.return_value = None
            assert service.is_run_streaming("run-1") is False

    @pytest.mark.asyncio
    async def test_cleanup_run(self) -> None:
        """Test run cleanup"""
        service = StreamingService()
        run_id = "run-123"

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            await service.cleanup_run(run_id)
            mock_manager.cleanup_broker.assert_called_with(run_id)

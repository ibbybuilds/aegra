"""Unit tests for streaming_service module"""

from collections.abc import AsyncGenerator
from datetime import datetime
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

    async def test_store_event_from_raw_messages(self) -> None:
        """Test storing message events"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "evt-1"

        # Test messages (tuple with 2 items)
        with patch(
            "aegra_api.services.streaming_service.store_sse_event",
            new_callable=AsyncMock,
        ) as mock_store:
            raw_event = ("messages", {"content": "hello"})
            await service.store_event_from_raw(run_id, event_id, raw_event)

            mock_store.assert_awaited_with(
                run_id,
                event_id,
                "messages",
                {
                    "type": "messages_stream",
                    "message_chunk": {"content": "hello"},
                    "metadata": None,
                    "node_path": None,
                },
            )

    async def test_store_event_from_raw_partial(self) -> None:
        """Test storing partial message events"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "evt-1"

        with patch(
            "aegra_api.services.streaming_service.store_sse_event",
            new_callable=AsyncMock,
        ) as mock_store:
            raw_event = ("messages/partial", ["chunk"])
            await service.store_event_from_raw(run_id, event_id, raw_event)

            mock_store.assert_awaited_with(
                run_id,
                event_id,
                "messages/partial",
                {"type": "messages_partial", "messages": ["chunk"], "node_path": None},
            )

    async def test_store_event_from_raw_complete(self) -> None:
        """Test storing complete message events"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "evt-1"

        with patch(
            "aegra_api.services.streaming_service.store_sse_event",
            new_callable=AsyncMock,
        ) as mock_store:
            raw_event = ("messages/complete", ["msg"])
            await service.store_event_from_raw(run_id, event_id, raw_event)

            mock_store.assert_awaited_with(
                run_id,
                event_id,
                "messages/complete",
                {"type": "messages_complete", "messages": ["msg"], "node_path": None},
            )

    async def test_store_event_from_raw_metadata(self) -> None:
        """Test storing metadata events"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "evt-1"

        with patch(
            "aegra_api.services.streaming_service.store_sse_event",
            new_callable=AsyncMock,
        ) as mock_store:
            raw_event = ("messages/metadata", {"meta": "data"})
            await service.store_event_from_raw(run_id, event_id, raw_event)

            mock_store.assert_awaited_with(
                run_id,
                event_id,
                "messages/metadata",
                {
                    "type": "messages_metadata",
                    "metadata": {"meta": "data"},
                    "node_path": None,
                },
            )

    async def test_store_event_from_raw_events(self) -> None:
        """Test storing langchain events"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "evt-1"

        with patch(
            "aegra_api.services.streaming_service.store_sse_event",
            new_callable=AsyncMock,
        ) as mock_store:
            raw_event = ("events", {"event": "data"})
            await service.store_event_from_raw(run_id, event_id, raw_event)

            mock_store.assert_awaited_with(
                run_id,
                event_id,
                "events",
                {"type": "langchain_event", "event": {"event": "data"}},
            )

    async def test_store_event_from_raw_values(self) -> None:
        """Test storing values events"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "evt-1"

        with patch(
            "aegra_api.services.streaming_service.store_sse_event",
            new_callable=AsyncMock,
        ) as mock_store:
            raw_event = ("values", {"val": 1})
            await service.store_event_from_raw(run_id, event_id, raw_event)

            mock_store.assert_awaited_with(
                run_id,
                event_id,
                "values",
                {"type": "execution_values", "chunk": {"val": 1}},
            )

    async def test_store_event_from_raw_end(self) -> None:
        """Test storing end events"""
        service = StreamingService()
        run_id = "run-123"
        event_id = "evt-1"

        with patch(
            "aegra_api.services.streaming_service.store_sse_event",
            new_callable=AsyncMock,
        ) as mock_store:
            raw_event = ("end", {"status": "success", "final_output": "done"})
            await service.store_event_from_raw(run_id, event_id, raw_event)

            mock_store.assert_awaited_with(
                run_id,
                event_id,
                "end",
                {"type": "run_complete", "status": "success", "final_output": "done"},
            )

    async def test_signal_run_cancelled(self) -> None:
        """Test signalling run cancellation"""
        service = StreamingService()
        run_id = "run-123"

        mock_broker = AsyncMock()

        with patch("aegra_api.services.streaming_service.broker_manager") as mock_manager:
            mock_manager.get_or_create_broker.return_value = mock_broker

            await service.signal_run_cancelled(run_id)

            # Should put end event
            mock_broker.put.assert_awaited()
            args = mock_broker.put.call_args
            assert args[0][1] == ("end", {"status": "interrupted"})

            # Should cleanup broker
            mock_manager.cleanup_broker.assert_called_with(run_id)

    async def test_signal_run_error(self) -> None:
        """Test signalling run error sends proper error event and stores it"""
        service = StreamingService()
        run_id = "run-123"
        error_msg = "Something went wrong"
        error_type = "ValueError"

        mock_broker = AsyncMock()

        with (
            patch("aegra_api.services.streaming_service.broker_manager") as mock_manager,
            patch(
                "aegra_api.services.streaming_service.store_sse_event",
                new_callable=AsyncMock,
            ) as mock_store,
        ):
            mock_manager.get_or_create_broker.return_value = mock_broker

            await service.signal_run_error(run_id, error_msg, error_type)

            # Should put error event first (not end event)
            assert mock_broker.put.await_count >= 1
            call_args_list = mock_broker.put.call_args_list

            # First call should be error event
            first_call = call_args_list[0]
            event_type, event_data = first_call[0][1]
            assert event_type == "error"
            assert event_data["error"] == error_type
            assert event_data["message"] == error_msg

            # Should store error event for replay
            mock_store.assert_awaited_once()
            store_call = mock_store.call_args
            assert store_call[0][0] == run_id  # run_id
            assert store_call[0][2] == "error"  # event_type
            assert store_call[0][3]["error"] == error_type
            assert store_call[0][3]["message"] == error_msg

            # Should also send end event
            assert mock_broker.put.await_count >= 2
            second_call = call_args_list[1]
            end_event_type, end_event_data = second_call[0][1]
            assert end_event_type == "end"
            assert end_event_data["status"] == "error"

            # Should cleanup broker
            mock_manager.cleanup_broker.assert_called_with(run_id)

    async def test_signal_run_error_default_type(self) -> None:
        """Test signal_run_error with default error type"""
        service = StreamingService()
        run_id = "run-123"
        error_msg = "Generic error"

        mock_broker = AsyncMock()

        with (
            patch("aegra_api.services.streaming_service.broker_manager") as mock_manager,
            patch(
                "aegra_api.services.streaming_service.store_sse_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_manager.get_or_create_broker.return_value = mock_broker

            await service.signal_run_error(run_id, error_msg)

            # Should use default error type "Error"
            call_args = mock_broker.put.call_args_list[0]
            event_type, event_data = call_args[0][1]
            assert event_type == "error"
            assert event_data["error"] == "Error"
            assert event_data["message"] == error_msg

    async def test_stream_run_execution(self) -> None:
        """Test overall streaming execution"""
        service = StreamingService()
        run = Run(
            run_id="run-123",
            status="running",
            user_id="user-1",
            thread_id="thread-1",
            assistant_id="agent",
            input={"message": "hello"},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Mock live events
        mock_broker = MagicMock()
        mock_broker.is_finished.return_value = False

        async def mock_aiter() -> AsyncGenerator:
            yield "run-123_event_3", "raw3"
            yield "run-123_event_4", "raw4"

        mock_broker.aiter = mock_aiter

        with (
            patch("aegra_api.services.streaming_service.event_store") as mock_store,
            patch("aegra_api.services.streaming_service.broker_manager") as mock_manager,
        ):
            mock_store.get_all_events = AsyncMock(return_value=["stored_ev1", "stored_ev2"])
            service._stored_event_to_sse = MagicMock(side_effect=["sse1", "sse2"])
            service._convert_raw_to_sse = AsyncMock(side_effect=["sse3", "sse4"])

            mock_manager.get_or_create_broker.return_value = mock_broker

            # Execute
            events = []
            async for event in service.stream_run_execution(run):
                events.append(event)

            # Verification
            assert len(events) == 4
            assert events == ["sse1", "sse2", "sse3", "sse4"]

            # Should have fetched stored events
            mock_store.get_all_events.assert_awaited_with("run-123")

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
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        last_id = "run-123_event_5"

        with (
            patch("aegra_api.services.streaming_service.event_store") as mock_store,
            patch("aegra_api.services.streaming_service.broker_manager") as mock_manager,
        ):
            mock_store.get_events_since = AsyncMock(return_value=[])

            mock_broker = MagicMock()

            async def mock_aiter() -> AsyncGenerator:
                if False:
                    yield  # Force async generator

            mock_broker.aiter = mock_aiter
            mock_broker.is_finished.return_value = False

            mock_manager.get_or_create_broker.return_value = mock_broker

            async for _ in service.stream_run_execution(run, last_event_id=last_id):
                pass

            # Should fetch events since last_id
            mock_store.get_events_since.assert_awaited_with("run-123", last_id)

    async def test_cancel_background_task(self) -> None:
        """Test cancelling background task"""
        service = StreamingService()
        run_id = "run-123"

        mock_task = MagicMock()
        mock_task.done.return_value = False

        # Mock active_runs
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
            # Task should be cancelled first
            mock_cancel.assert_called_once_with(run_id)
            # Then signal interruption to broker
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
            # Task should be cancelled first
            mock_cancel.assert_called_once_with(run_id)
            # Then signal cancellation to broker
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

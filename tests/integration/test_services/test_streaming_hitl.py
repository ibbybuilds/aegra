"""
Unit tests for human-in-the-loop functionality in streaming services.
Tests interrupt processing and event conversion.
"""

from unittest.mock import Mock

import pytest

from aegra.agent_server.services.event_converter import EventConverter
from aegra.agent_server.services.streaming_service import StreamingService


class TestStreamingInterruptProcessing:
    """Test interrupt processing in streaming service."""

    @pytest.fixture
    def streaming_service(self):
        """Create streaming service instance."""
        return StreamingService()

    def test_process_interrupt_updates_with_interrupt(self, streaming_service):
        """Test processing updates event that contains interrupt."""
        # Mock event with interrupt
        raw_event = ("updates", {"__interrupt__": [{"value": "test", "id": "123"}]})
        only_interrupt_updates = True

        processed_event, should_skip = streaming_service._process_interrupt_updates(
            raw_event, only_interrupt_updates
        )

        # Should convert to values event
        assert processed_event[0] == "values"
        assert processed_event[1] == {"__interrupt__": [{"value": "test", "id": "123"}]}
        assert should_skip is False

    def test_process_interrupt_updates_without_interrupt(self, streaming_service):
        """Test processing updates event without interrupt (should skip)."""
        # Mock event without interrupt
        raw_event = ("updates", {"messages": [{"role": "ai", "content": "test"}]})
        only_interrupt_updates = True

        processed_event, should_skip = streaming_service._process_interrupt_updates(
            raw_event, only_interrupt_updates
        )

        # Should skip non-interrupt updates
        assert processed_event == raw_event
        assert should_skip is True

    def test_process_interrupt_updates_not_only_interrupt_mode(self, streaming_service):
        """Test processing when not in only_interrupt_updates mode."""
        # Mock event with interrupt
        raw_event = ("updates", {"__interrupt__": [{"value": "test", "id": "123"}]})
        only_interrupt_updates = False

        processed_event, should_skip = streaming_service._process_interrupt_updates(
            raw_event, only_interrupt_updates
        )

        # Should not modify event when not in only_interrupt_updates mode
        assert processed_event == raw_event
        assert should_skip is False

    def test_process_interrupt_updates_non_updates_event(self, streaming_service):
        """Test processing non-updates event (should pass through)."""
        # Mock non-updates event
        raw_event = ("values", {"messages": [{"role": "ai", "content": "test"}]})
        only_interrupt_updates = True

        processed_event, should_skip = streaming_service._process_interrupt_updates(
            raw_event, only_interrupt_updates
        )

        # Should pass through unchanged
        assert processed_event == raw_event
        assert should_skip is False


class TestEventConverter:
    """Test event converter for SSE formatting."""

    @pytest.fixture
    def event_converter(self):
        """Create event converter instance."""
        return EventConverter()

    def test_convert_interrupt_values_event(self, event_converter):
        """Test converting values event with interrupt to SSE."""
        event_id = "test-123"
        raw_event = (
            "values",
            {"__interrupt__": [{"value": "approve?", "id": "int-1"}]},
        )

        sse_event = event_converter.convert_raw_to_sse(event_id, raw_event)

        assert sse_event is not None
        assert "event: values" in sse_event
        assert "data: " in sse_event
        assert "__interrupt__" in sse_event

    def test_convert_stored_interrupt_event(self, event_converter):
        """Test converting stored values event with interrupt to SSE."""
        # Mock stored event object (stored as values, not updates)
        stored_event = Mock()
        stored_event.event = "values"
        stored_event.data = {
            "chunk": {"__interrupt__": [{"value": "test", "id": "123"}]}
        }
        stored_event.id = "event-456"

        sse_event = event_converter.convert_stored_to_sse(stored_event, "run-123")

        assert sse_event is not None
        # Should create values event
        assert "event: values" in sse_event

    def test_convert_non_interrupt_updates_event(self, event_converter):
        """Test converting stored values event without interrupt to SSE."""
        # Mock stored event without interrupt (stored as values)
        stored_event = Mock()
        stored_event.event = "values"
        stored_event.data = {"chunk": {"messages": [{"role": "ai", "content": "test"}]}}
        stored_event.id = "event-789"

        sse_event = event_converter.convert_stored_to_sse(stored_event, "run-123")

        assert sse_event is not None
        # Should create values event
        assert "event: values" in sse_event

    def test_parse_raw_event_tuple_formats(self, event_converter):
        """Test parsing different tuple formats from LangGraph."""
        # Test 2-tuple format
        raw_event = ("values", {"test": "data"})
        stream_mode, payload = event_converter._parse_raw_event(raw_event)
        assert stream_mode == "values"
        assert payload == {"test": "data"}

        # Test 3-tuple format (with node_path)
        raw_event = ("node_path", "values", {"test": "data"})
        stream_mode, payload = event_converter._parse_raw_event(raw_event)
        assert stream_mode == "values"
        assert payload == {"test": "data"}

        # Test non-tuple format
        raw_event = {"test": "data"}
        stream_mode, payload = event_converter._parse_raw_event(raw_event)
        assert stream_mode == "values"  # Default
        assert payload == {"test": "data"}


class TestInterruptEventFlow:
    """Integration test for interrupt event flow through streaming."""

    @pytest.fixture
    def streaming_service(self):
        return StreamingService()

    @pytest.fixture
    def event_converter(self):
        return EventConverter()

    def test_interrupt_event_end_to_end(self, streaming_service, event_converter):
        """Test complete interrupt event processing flow."""
        # 1. Raw interrupt event from LangGraph
        raw_interrupt_event = (
            "updates",
            {
                "__interrupt__": [
                    {"value": {"message": "Approve tool?", "tools": []}, "id": "int-1"}
                ]
            },
        )

        # 2. Process through streaming service (only_interrupt_updates=True)
        processed_event, should_skip = streaming_service._process_interrupt_updates(
            raw_interrupt_event, only_interrupt_updates=True
        )

        # Should convert to values event
        assert processed_event[0] == "values"
        assert should_skip is False

        # 3. Convert to SSE format
        event_id = "stream-123"
        sse_event = event_converter.convert_raw_to_sse(event_id, processed_event)

        # Should produce valid SSE event
        assert sse_event is not None
        assert "event: values" in sse_event
        assert "id: stream-123" in sse_event
        assert "__interrupt__" in sse_event
        assert "Approve tool?" in sse_event

    def test_non_interrupt_event_filtering(self, streaming_service, event_converter):
        """Test that non-interrupt events are filtered when only_interrupt_updates=True."""
        # 1. Regular updates event (no interrupt)
        raw_regular_event = (
            "updates",
            {"messages": [{"role": "ai", "content": "Regular response"}]},
        )

        # 2. Process through streaming service (only_interrupt_updates=True)
        processed_event, should_skip = streaming_service._process_interrupt_updates(
            raw_regular_event, only_interrupt_updates=True
        )

        # Should be marked for skipping
        assert should_skip is True
        assert processed_event == raw_regular_event  # Unchanged

        # 3. If not skipped, would convert normally
        if not should_skip:
            event_id = "stream-456"
            sse_event = event_converter.convert_raw_to_sse(event_id, processed_event)
            assert sse_event is not None
        # But in this case, it should be skipped in the actual streaming flow

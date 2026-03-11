"""
Unit tests for human-in-the-loop functionality in streaming services.
Tests interrupt processing and event conversion.
"""

import pytest

from aegra_api.services.event_converter import EventConverter

# Interrupt updates filtering is handled in graph_streaming.py's _process_stream_event
# function, not in StreamingService. Tests for this functionality should be in
# test_graph_streaming or e2e tests.


class TestEventConverter:
    """Test event converter for SSE formatting."""

    @pytest.fixture
    def event_converter(self) -> EventConverter:
        """Create event converter instance."""
        return EventConverter()

    def test_convert_interrupt_values_event(self, event_converter: EventConverter) -> None:
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

    def test_convert_updates_event(self, event_converter: EventConverter) -> None:
        """Test converting updates event to SSE preserves stream mode."""
        event_id = "test-456"
        raw_event = ("updates", {"status": "waiting"})

        sse_event = event_converter.convert_raw_to_sse(event_id, raw_event)

        assert sse_event is not None
        assert "event: updates" in sse_event
        assert "data: " in sse_event
        assert "waiting" in sse_event

    def test_parse_raw_event_tuple_formats(self, event_converter: EventConverter) -> None:
        """Test parsing different tuple formats."""
        # Test 2-tuple format
        raw_event = ("values", {"test": "data"})
        stream_mode, payload, namespace = event_converter._parse_raw_event(raw_event)
        assert stream_mode == "values"
        assert payload == {"test": "data"}
        assert namespace is None

        # Test 3-tuple format (legacy node_path)
        event_converter.set_subgraphs(False)
        raw_event = ("node_path", "values", {"test": "data"})
        stream_mode, payload, namespace = event_converter._parse_raw_event(raw_event)
        assert stream_mode == "values"
        assert payload == {"test": "data"}
        assert namespace is None

        # Test 3-tuple format (subgraphs with namespace)
        event_converter.set_subgraphs(True)
        raw_event = (["subagent"], "messages", {"test": "data"})
        stream_mode, payload, namespace = event_converter._parse_raw_event(raw_event)
        assert stream_mode == "messages"
        assert payload == {"test": "data"}
        assert namespace == ["subagent"]

        # Test non-tuple format
        raw_event = {"test": "data"}
        stream_mode, payload, namespace = event_converter._parse_raw_event(raw_event)
        assert stream_mode == "values"  # Default
        assert payload == {"test": "data"}


# Interrupt event flow tests removed - functionality is tested through graph_streaming flow

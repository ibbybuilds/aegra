"""Unit tests for EventConverter"""

from unittest.mock import Mock

from aegra_api.services.event_converter import EventConverter


class TestEventConverter:
    """Test EventConverter class"""

    def setup_method(self):
        """Setup test fixtures"""
        self.converter = EventConverter()

    def test_parse_raw_event_tuple_2_elements(self):
        """Test parsing raw event with 2-element tuple"""
        raw_event = ("values", {"key": "value"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "values"
        assert payload == {"key": "value"}
        assert namespace is None

    def test_parse_raw_event_tuple_3_elements_legacy(self):
        """Test parsing raw event with 3-element tuple (legacy node_path format)"""
        self.converter.set_subgraphs(False)  # Legacy mode
        raw_event = ("node_path", "updates", {"data": "test"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "updates"
        assert payload == {"data": "test"}
        assert namespace is None

    def test_parse_raw_event_tuple_3_elements_subgraphs(self):
        """Test parsing raw event with 3-element tuple (subgraphs format)"""
        self.converter.set_subgraphs(True)  # Subgraphs mode
        raw_event = (["subagent"], "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["subagent"]

    def test_parse_raw_event_tuple_3_elements_subgraphs_string_namespace(self):
        """Test parsing raw event with string namespace (converted to list)"""
        self.converter.set_subgraphs(True)
        raw_event = ("subagent", "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["subagent"]

    def test_parse_raw_event_non_tuple(self):
        """Test parsing raw event that's not a tuple"""
        raw_event = {"direct": "payload"}
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "values"
        assert payload == {"direct": "payload"}
        assert namespace is None

    def test_create_sse_event_messages(self):
        """Test creating messages SSE event"""
        result = self.converter._create_sse_event("messages", {"content": "hello"}, "evt-1", None)

        assert "event: messages\n" in result
        assert "hello" in result

    def test_create_sse_event_messages_with_namespace(self):
        """Test creating messages SSE event with namespace prefix"""
        self.converter.set_subgraphs(True)
        result = self.converter._create_sse_event("messages", {"content": "hello"}, "evt-1", ["subagent"])

        assert "event: messages|subagent\n" in result
        assert "hello" in result

    def test_create_sse_event_values(self):
        """Test creating values SSE event"""
        result = self.converter._create_sse_event("values", {"state": "data"}, "evt-1", None)

        assert "event: values\n" in result

    def test_create_sse_event_updates(self):
        """Test creating updates SSE event"""
        result = self.converter._create_sse_event("updates", {"node": "agent"}, "evt-1", None)

        assert "event: updates\n" in result

    def test_create_sse_event_updates_with_interrupt(self):
        """Test that interrupt updates in explicit updates mode remain as updates.

        When the user explicitly requested stream_mode=["updates"], interrupt events
        arrive here as "updates" and must NOT be remapped to "values". The remapping
        only happens in graph_streaming for non-explicitly-requested updates, so by
        the time an event reaches the converter it is already correctly labelled.
        """
        payload = {"__interrupt__": [{"node": "test"}], "data": "test"}
        result = self.converter._create_sse_event("updates", payload, "evt-1", None)

        assert "event: updates\n" in result

    def test_create_sse_event_state(self):
        """Test creating state SSE event"""
        result = self.converter._create_sse_event("state", {"values": {}}, "evt-1", None)

        assert "event: state\n" in result

    def test_create_sse_event_logs(self):
        """Test creating logs SSE event"""
        result = self.converter._create_sse_event("logs", {"level": "info"}, "evt-1", None)

        assert "event: logs\n" in result

    def test_create_sse_event_tasks(self):
        """Test creating tasks SSE event"""
        result = self.converter._create_sse_event("tasks", {"tasks": []}, "evt-1", None)

        assert "event: tasks\n" in result

    def test_create_sse_event_subgraphs(self):
        """Test creating subgraphs SSE event"""
        result = self.converter._create_sse_event("subgraphs", {"id": "sg-1"}, "evt-1", None)

        assert "event: subgraphs\n" in result

    def test_create_sse_event_debug(self):
        """Test creating debug SSE event"""
        result = self.converter._create_sse_event("debug", {"type": "test"}, "evt-1", None)

        assert "event: debug\n" in result

    def test_create_sse_event_events(self):
        """Test creating events SSE event"""
        result = self.converter._create_sse_event("events", {"event": "test"}, "evt-1", None)

        assert "event: events\n" in result

    def test_create_sse_event_checkpoints(self):
        """Test creating checkpoints SSE event"""
        result = self.converter._create_sse_event("checkpoints", {"cp": "1"}, "evt-1", None)

        assert "event: checkpoints\n" in result

    def test_create_sse_event_custom(self):
        """Test creating custom SSE event"""
        result = self.converter._create_sse_event("custom", {"custom": "data"}, "evt-1", None)

        assert "event: custom\n" in result

    def test_create_sse_event_end(self):
        """Test creating end SSE event"""
        result = self.converter._create_sse_event("end", None, "evt-1", None)

        assert "event: end\n" in result

    def test_create_sse_event_unknown_mode(self):
        """Test creating SSE event with unknown mode uses generic handler"""
        result = self.converter._create_sse_event("unknown_mode", {"data": "test"}, "evt-1", None)

        # Unknown modes are handled generically and return formatted event
        assert result is not None
        assert "event: unknown_mode\n" in result
        assert "data: " in result

    def test_convert_raw_to_sse_tuple_format(self):
        """Test converting raw event in tuple format"""
        raw_event = ("values", {"key": "value"})
        result = self.converter.convert_raw_to_sse("evt-1", raw_event)

        assert result is not None
        assert "event: values\n" in result
        assert "key" in result

    def test_convert_raw_to_sse_direct_payload(self):
        """Test converting raw event with direct payload"""
        raw_event = {"direct": "data"}
        result = self.converter.convert_raw_to_sse("evt-1", raw_event)

        assert result is not None
        assert "event: values\n" in result

    def test_convert_stored_to_sse_messages(self):
        """Test converting stored messages event"""
        stored_event = Mock()
        stored_event.event = "messages"
        stored_event.data = {
            "message_chunk": {"content": "hello"},
            "metadata": {"model": "gpt-4"},
        }
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: messages\n" in result

    def test_convert_stored_to_sse_messages_without_metadata(self):
        """Test converting stored messages event without metadata"""
        stored_event = Mock()
        stored_event.event = "messages"
        stored_event.data = {"message_chunk": {"content": "hello"}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: messages\n" in result

    def test_convert_stored_to_sse_messages_none_chunk(self):
        """Test converting stored messages event with None chunk returns None"""
        stored_event = Mock()
        stored_event.event = "messages"
        stored_event.data = {"message_chunk": None}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is None

    def test_convert_stored_to_sse_values(self):
        """Test converting stored values event"""
        stored_event = Mock()
        stored_event.event = "values"
        stored_event.data = {"chunk": {"state": "data"}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: values\n" in result

    def test_convert_stored_to_sse_metadata(self):
        """Test converting stored metadata event uses the stored payload directly."""
        stored_event = Mock()
        stored_event.event = "metadata"
        stored_event.data = {"run_id": "run-123", "attempt": 1}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: metadata\n" in result
        assert "run-123" in result

    def test_convert_stored_to_sse_state(self):
        """Test converting stored state event"""
        stored_event = Mock()
        stored_event.event = "state"
        stored_event.data = {"state": {"values": {}}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: state\n" in result

    def test_convert_stored_to_sse_logs(self):
        """Test converting stored logs event"""
        stored_event = Mock()
        stored_event.event = "logs"
        stored_event.data = {"logs": {"level": "info"}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: logs\n" in result

    def test_convert_stored_to_sse_tasks(self):
        """Test converting stored tasks event"""
        stored_event = Mock()
        stored_event.event = "tasks"
        stored_event.data = {"tasks": [{"id": "task-1"}]}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: tasks\n" in result

    def test_convert_stored_to_sse_subgraphs(self):
        """Test converting stored subgraphs event"""
        stored_event = Mock()
        stored_event.event = "subgraphs"
        stored_event.data = {"subgraphs": {"id": "sg-1"}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: subgraphs\n" in result

    def test_convert_stored_to_sse_debug(self):
        """Test converting stored debug event"""
        stored_event = Mock()
        stored_event.event = "debug"
        stored_event.data = {"debug": {"type": "test"}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: debug\n" in result

    def test_convert_stored_to_sse_events(self):
        """Test converting stored events event"""
        stored_event = Mock()
        stored_event.event = "events"
        stored_event.data = {"event": {"type": "test"}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: events\n" in result

    def test_convert_stored_to_sse_end(self):
        """Test converting stored end event"""
        stored_event = Mock()
        stored_event.event = "end"
        stored_event.data = {}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: end\n" in result

    def test_convert_stored_to_sse_error(self):
        """Test converting stored error event"""
        stored_event = Mock()
        stored_event.event = "error"
        stored_event.data = {"error": "Something went wrong"}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: error\n" in result
        assert "Something went wrong" in result

    def test_convert_stored_to_sse_messages_partial(self):
        """Test converting stored messages/partial event extracts messages list directly."""
        stored_event = Mock()
        stored_event.event = "messages/partial"
        stored_event.data = {"type": "messages_partial", "messages": [{"content": "hello"}], "node_path": None}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: messages/partial\n" in result
        # Payload should be the messages list, not the whole stored dict
        assert "messages_partial" not in result

    def test_convert_stored_to_sse_messages_partial_missing_key_returns_none(self):
        """Test that a malformed messages/partial event without 'messages' key returns None."""
        stored_event = Mock()
        stored_event.event = "messages/partial"
        stored_event.data = {"type": "messages_partial"}  # no "messages" key
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is None

    def test_convert_stored_to_sse_messages_complete(self):
        """Test converting stored messages/complete event extracts messages list directly."""
        stored_event = Mock()
        stored_event.event = "messages/complete"
        stored_event.data = {"type": "messages_complete", "messages": [{"content": "hello"}], "node_path": None}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: messages/complete\n" in result
        assert "messages_complete" not in result

    def test_convert_stored_to_sse_messages_complete_missing_key_returns_none(self):
        """Test that a malformed messages/complete event without 'messages' key returns None."""
        stored_event = Mock()
        stored_event.event = "messages/complete"
        stored_event.data = {}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is None

    def test_convert_stored_to_sse_messages_metadata(self):
        """Test converting stored messages/metadata event extracts metadata directly."""
        stored_event = Mock()
        stored_event.event = "messages/metadata"
        stored_event.data = {"type": "messages_metadata", "metadata": {"msg-1": {"model": "gpt-4"}}, "node_path": None}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: messages/metadata\n" in result
        assert "messages_metadata" not in result
        assert "gpt-4" in result

    def test_convert_stored_to_sse_messages_metadata_missing_key_returns_none(self):
        """Test that a malformed messages/metadata event without 'metadata' key returns None."""
        stored_event = Mock()
        stored_event.event = "messages/metadata"
        stored_event.data = {"type": "messages_metadata"}  # no "metadata" key
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is None

    def test_convert_stored_to_sse_updates(self):
        """Test converting stored updates event produces updates SSE type via explicit branch."""
        stored_event = Mock()
        stored_event.event = "updates"
        stored_event.data = {"type": "execution_updates", "chunk": {"my_node": {"key": "val"}}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        # Must be "updates", not "values"
        assert "event: updates\n" in result
        assert "my_node" in result

    def test_convert_stored_to_sse_custom(self):
        """Test converting stored custom event via explicit branch (not generic fallback)."""
        stored_event = Mock()
        stored_event.event = "custom"
        stored_event.data = {"chunk": {"my_key": "my_value"}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: custom\n" in result
        assert "my_value" in result

    def test_convert_stored_to_sse_custom_empty_chunk_not_replaced_by_envelope(self):
        """Regression: falsy chunk ({}) must be used as-is, not replaced by the envelope dict."""
        stored_event = Mock()
        stored_event.event = "custom"
        stored_event.data = {"chunk": {}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: custom\n" in result
        # The payload must be the empty dict, not the envelope {"chunk": {}}
        assert "chunk" not in result

    def test_convert_stored_to_sse_updates_empty_chunk_not_replaced_by_envelope(self):
        """Regression: falsy chunk ({}) in updates must be used as-is, not replaced by the envelope dict."""
        stored_event = Mock()
        stored_event.event = "updates"
        stored_event.data = {"type": "execution_updates", "chunk": {}}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: updates\n" in result
        # The payload must be the empty dict, not the envelope {"type": ..., "chunk": {}}
        assert "execution_updates" not in result

    def test_convert_stored_to_sse_metadata_uses_stored_payload(self):
        """Test that metadata replay uses the stored payload, not a reconstructed one.

        create_metadata_event always hardcodes attempt=1 and only uses run_id.
        The stored data may have a different attempt value or additional fields,
        so faithful replay must use the stored dict directly.
        """
        stored_event = Mock()
        stored_event.event = "metadata"
        stored_event.data = {"run_id": "run-abc", "attempt": 3}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        assert result is not None
        assert "event: metadata\n" in result
        assert "attempt" in result
        assert "3" in result

    def test_convert_stored_to_sse_unknown_event(self):
        """Test converting stored event with unknown type uses generic handler"""
        stored_event = Mock()
        stored_event.event = "unknown_event_type"
        stored_event.data = {}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event)

        # Unknown event types are handled generically and return formatted event
        assert result is not None
        assert "event: unknown_event_type\n" in result
        assert "id: evt-1\n" in result

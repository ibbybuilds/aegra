"""Unit tests for EventConverter"""

from unittest.mock import Mock

from src.agent_server.services.event_converter import EventConverter


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
        result = self.converter._create_sse_event(
            "messages", {"content": "hello"}, "evt-1", None
        )

        assert "event: messages\n" in result
        assert "hello" in result

    def test_create_sse_event_messages_with_namespace(self):
        """Test creating messages SSE event with namespace prefix"""
        self.converter.set_subgraphs(True)
        result = self.converter._create_sse_event(
            "messages", {"content": "hello"}, "evt-1", ["subagent"]
        )

        assert "event: messages|subagent\n" in result
        assert "hello" in result

    def test_create_sse_event_values(self):
        """Test creating values SSE event"""
        result = self.converter._create_sse_event(
            "values", {"state": "data"}, "evt-1", None
        )

        assert "event: values\n" in result

    def test_create_sse_event_updates(self):
        """Test creating updates SSE event"""
        result = self.converter._create_sse_event(
            "updates", {"node": "agent"}, "evt-1", None
        )

        assert "event: updates\n" in result

    def test_create_sse_event_updates_with_interrupt(self):
        """Test that interrupt updates are converted to values"""
        # Use a list for __interrupt__ to match the actual condition check
        payload = {"__interrupt__": [{"node": "test"}], "data": "test"}
        result = self.converter._create_sse_event("updates", payload, "evt-1", None)

        # Should be converted to values event
        assert "event: values\n" in result

    def test_create_sse_event_state(self):
        """Test creating state SSE event"""
        result = self.converter._create_sse_event(
            "state", {"values": {}}, "evt-1", None
        )

        assert "event: state\n" in result

    def test_create_sse_event_logs(self):
        """Test creating logs SSE event"""
        result = self.converter._create_sse_event(
            "logs", {"level": "info"}, "evt-1", None
        )

        assert "event: logs\n" in result

    def test_create_sse_event_tasks(self):
        """Test creating tasks SSE event"""
        result = self.converter._create_sse_event("tasks", {"tasks": []}, "evt-1", None)

        assert "event: tasks\n" in result

    def test_create_sse_event_subgraphs(self):
        """Test creating subgraphs SSE event"""
        result = self.converter._create_sse_event(
            "subgraphs", {"id": "sg-1"}, "evt-1", None
        )

        assert "event: subgraphs\n" in result

    def test_create_sse_event_debug(self):
        """Test creating debug SSE event"""
        result = self.converter._create_sse_event(
            "debug", {"type": "test"}, "evt-1", None
        )

        assert "event: debug\n" in result

    def test_create_sse_event_events(self):
        """Test creating events SSE event"""
        result = self.converter._create_sse_event(
            "events", {"event": "test"}, "evt-1", None
        )

        assert "event: events\n" in result

    def test_create_sse_event_checkpoints(self):
        """Test creating checkpoints SSE event"""
        result = self.converter._create_sse_event(
            "checkpoints", {"cp": "1"}, "evt-1", None
        )

        assert "event: checkpoints\n" in result

    def test_create_sse_event_custom(self):
        """Test creating custom SSE event"""
        result = self.converter._create_sse_event(
            "custom", {"custom": "data"}, "evt-1", None
        )

        assert "event: custom\n" in result

    def test_create_sse_event_end(self):
        """Test creating end SSE event"""
        result = self.converter._create_sse_event("end", None, "evt-1", None)

        assert "event: end\n" in result

    def test_create_sse_event_unknown_mode(self):
        """Test creating SSE event with unknown mode uses generic handler"""
        result = self.converter._create_sse_event(
            "unknown_mode", {"data": "test"}, "evt-1", None
        )

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
        """Test converting stored metadata event"""
        stored_event = Mock()
        stored_event.event = "metadata"
        stored_event.data = {}
        stored_event.id = "evt-1"

        result = self.converter.convert_stored_to_sse(stored_event, run_id="run-123")

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

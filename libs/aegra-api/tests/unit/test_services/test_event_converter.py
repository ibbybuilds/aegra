"""Unit tests for EventConverter"""

from aegra_api.services.event_converter import EventConverter


class TestEventConverter:
    """Test EventConverter class"""

    def setup_method(self) -> None:
        """Setup test fixtures"""
        self.converter = EventConverter()

    def test_parse_raw_event_tuple_2_elements(self) -> None:
        """Test parsing raw event with 2-element tuple"""
        raw_event = ("values", {"key": "value"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "values"
        assert payload == {"key": "value"}
        assert namespace is None

    def test_parse_raw_event_tuple_3_elements_legacy(self) -> None:
        """Test parsing raw event with 3-element tuple (legacy node_path format)"""
        self.converter.set_subgraphs(False)  # Legacy mode
        raw_event = ("node_path", "updates", {"data": "test"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "updates"
        assert payload == {"data": "test"}
        assert namespace is None

    def test_parse_raw_event_tuple_3_elements_subgraphs(self) -> None:
        """Test parsing raw event with 3-element tuple (subgraphs format)"""
        self.converter.set_subgraphs(True)  # Subgraphs mode
        raw_event = (["subagent"], "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["subagent"]

    def test_parse_raw_event_tuple_3_elements_subgraphs_string_namespace(self) -> None:
        """Test parsing raw event with string namespace (converted to list)"""
        self.converter.set_subgraphs(True)
        raw_event = ("subagent", "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["subagent"]

    def test_parse_raw_event_non_tuple(self) -> None:
        """Test parsing raw event that's not a tuple"""
        raw_event = {"direct": "payload"}
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "values"
        assert payload == {"direct": "payload"}
        assert namespace is None

    def test_create_sse_event_messages(self) -> None:
        """Test creating messages SSE event"""
        result = self.converter._create_sse_event("messages", {"content": "hello"}, "evt-1", None)

        assert result is not None
        assert "event: messages\n" in result
        assert "hello" in result

    def test_create_sse_event_messages_with_namespace(self) -> None:
        """Test creating messages SSE event with namespace prefix"""
        self.converter.set_subgraphs(True)
        result = self.converter._create_sse_event("messages", {"content": "hello"}, "evt-1", ["subagent"])

        assert result is not None
        assert "event: messages|subagent\n" in result
        assert "hello" in result

    def test_create_sse_event_values(self) -> None:
        """Test creating values SSE event"""
        result = self.converter._create_sse_event("values", {"state": "data"}, "evt-1", None)

        assert result is not None
        assert "event: values\n" in result

    def test_create_sse_event_updates(self) -> None:
        """Test creating updates SSE event"""
        result = self.converter._create_sse_event("updates", {"node": "agent"}, "evt-1", None)

        assert result is not None
        assert "event: updates\n" in result

    def test_create_sse_event_updates_with_interrupt(self) -> None:
        """Test that interrupt updates in explicit updates mode remain as updates.

        When the user explicitly requested stream_mode=["updates"], interrupt events
        arrive here as "updates" and must NOT be remapped to "values". The remapping
        only happens in graph_streaming for non-explicitly-requested updates, so by
        the time an event reaches the converter it is already correctly labelled.
        """
        payload = {"__interrupt__": [{"node": "test"}], "data": "test"}
        result = self.converter._create_sse_event("updates", payload, "evt-1", None)

        assert result is not None
        assert "event: updates\n" in result

    def test_create_sse_event_state(self) -> None:
        """Test creating state SSE event"""
        result = self.converter._create_sse_event("state", {"values": {}}, "evt-1", None)

        assert result is not None
        assert "event: state\n" in result

    def test_create_sse_event_logs(self) -> None:
        """Test creating logs SSE event"""
        result = self.converter._create_sse_event("logs", {"level": "info"}, "evt-1", None)

        assert result is not None
        assert "event: logs\n" in result

    def test_create_sse_event_tasks(self) -> None:
        """Test creating tasks SSE event"""
        result = self.converter._create_sse_event("tasks", {"tasks": []}, "evt-1", None)

        assert result is not None
        assert "event: tasks\n" in result

    def test_create_sse_event_subgraphs(self) -> None:
        """Test creating subgraphs SSE event"""
        result = self.converter._create_sse_event("subgraphs", {"id": "sg-1"}, "evt-1", None)

        assert result is not None
        assert "event: subgraphs\n" in result

    def test_create_sse_event_debug(self) -> None:
        """Test creating debug SSE event"""
        result = self.converter._create_sse_event("debug", {"type": "test"}, "evt-1", None)

        assert result is not None
        assert "event: debug\n" in result

    def test_create_sse_event_events(self) -> None:
        """Test creating events SSE event"""
        result = self.converter._create_sse_event("events", {"event": "test"}, "evt-1", None)

        assert result is not None
        assert "event: events\n" in result

    def test_create_sse_event_checkpoints(self) -> None:
        """Test creating checkpoints SSE event"""
        result = self.converter._create_sse_event("checkpoints", {"cp": "1"}, "evt-1", None)

        assert result is not None
        assert "event: checkpoints\n" in result

    def test_create_sse_event_custom(self) -> None:
        """Test creating custom SSE event"""
        result = self.converter._create_sse_event("custom", {"custom": "data"}, "evt-1", None)

        assert result is not None
        assert "event: custom\n" in result

    def test_create_sse_event_end(self) -> None:
        """Test creating end SSE event"""
        result = self.converter._create_sse_event("end", None, "evt-1", None)

        assert result is not None
        assert "event: end\n" in result

    def test_create_sse_event_unknown_mode(self) -> None:
        """Test creating SSE event with unknown mode uses generic handler"""
        result = self.converter._create_sse_event("unknown_mode", {"data": "test"}, "evt-1", None)

        # Unknown modes are handled generically and return formatted event
        assert result is not None
        assert "event: unknown_mode\n" in result
        assert "data: " in result

    def test_convert_raw_to_sse_tuple_format(self) -> None:
        """Test converting raw event in tuple format"""
        raw_event = ("values", {"key": "value"})
        result = self.converter.convert_raw_to_sse("evt-1", raw_event)

        assert result is not None
        assert "event: values\n" in result
        assert "key" in result

    def test_convert_raw_to_sse_direct_payload(self) -> None:
        """Test converting raw event with direct payload"""
        raw_event = {"direct": "data"}
        result = self.converter.convert_raw_to_sse("evt-1", raw_event)

        assert result is not None
        assert "event: values\n" in result

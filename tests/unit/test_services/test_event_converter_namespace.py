"""Unit tests for namespace handling in EventConverter"""

from src.agent_server.services.event_converter import EventConverter


class TestEventConverterNamespace:
    """Test namespace extraction and prefixing"""

    def setup_method(self):
        """Setup test fixtures"""
        self.converter = EventConverter()

    def test_parse_raw_event_3_tuple_none_namespace(self):
        """Test parsing 3-tuple with None namespace"""
        self.converter.set_subgraphs(True)
        raw_event = (None, "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace is None

    def test_parse_raw_event_3_tuple_list_namespace(self):
        """Test parsing 3-tuple with list namespace"""
        self.converter.set_subgraphs(True)
        raw_event = (["agent1", "agent2"], "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["agent1", "agent2"]

    def test_parse_raw_event_3_tuple_string_namespace(self):
        """Test parsing 3-tuple with string namespace (converted to list)"""
        self.converter.set_subgraphs(True)
        raw_event = ("agent1", "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["agent1"]

    def test_parse_raw_event_3_tuple_tuple_namespace(self):
        """Test parsing 3-tuple with tuple namespace (converted to list)"""
        self.converter.set_subgraphs(True)
        raw_event = (("subgraph_agent:uuid",), "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["subgraph_agent:uuid"]

    def test_parse_raw_event_3_tuple_empty_tuple_namespace(self):
        """Test parsing 3-tuple with empty tuple namespace"""
        self.converter.set_subgraphs(True)
        raw_event = ((), "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace is None

    def test_parse_raw_event_3_tuple_non_string_namespace(self):
        """Test parsing 3-tuple with non-string namespace (converted to list)"""
        self.converter.set_subgraphs(True)
        raw_event = (123, "messages", {"content": "hello"})
        stream_mode, payload, namespace = self.converter._parse_raw_event(raw_event)

        assert stream_mode == "messages"
        assert payload == {"content": "hello"}
        assert namespace == ["123"]

    def test_create_sse_event_with_namespace_prefix(self):
        """Test creating SSE event with namespace prefix"""
        self.converter.set_subgraphs(True)
        result = self.converter._create_sse_event(
            "messages", {"content": "hello"}, "evt-1", ["subagent"]
        )

        assert "event: messages|subagent\n" in result
        assert "hello" in result

    def test_create_sse_event_with_multiple_namespace_levels(self):
        """Test creating SSE event with multiple namespace levels"""
        self.converter.set_subgraphs(True)
        result = self.converter._create_sse_event(
            "values", {"data": "test"}, "evt-1", ["agent1", "agent2"]
        )

        assert "event: values|agent1|agent2\n" in result
        assert "test" in result

    def test_create_sse_event_without_namespace(self):
        """Test creating SSE event without namespace (no prefix)"""
        self.converter.set_subgraphs(True)
        result = self.converter._create_sse_event(
            "messages", {"content": "hello"}, "evt-1", None
        )

        assert "event: messages\n" in result
        assert "messages|" not in result

    def test_create_sse_event_namespace_disabled(self):
        """Test that namespace prefixing is disabled when subgraphs=False"""
        self.converter.set_subgraphs(False)
        result = self.converter._create_sse_event(
            "messages", {"content": "hello"}, "evt-1", ["subagent"]
        )

        assert "event: messages\n" in result
        assert "messages|subagent" not in result

    def test_create_sse_event_values_with_namespace(self):
        """Test creating values event with namespace"""
        self.converter.set_subgraphs(True)
        result = self.converter._create_sse_event(
            "values", {"state": "data"}, "evt-1", ["subagent"]
        )

        assert "event: values|subagent\n" in result
        assert "state" in result

    def test_create_sse_event_updates_converted_to_values_with_namespace(self):
        """Test that interrupt updates converted to values preserve namespace"""
        self.converter.set_subgraphs(True)
        payload = {"__interrupt__": [{"node": "test"}]}
        result = self.converter._create_sse_event(
            "updates", payload, "evt-1", ["subagent"]
        )

        assert "event: values|subagent\n" in result
        assert "__interrupt__" in result

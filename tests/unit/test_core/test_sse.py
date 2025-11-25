"""Unit tests for SSE utilities"""

import json
from datetime import datetime

from src.agent_server.core.sse import (
    SSEEvent,
    create_debug_event,
    create_end_event,
    create_error_event,
    create_messages_event,
    create_metadata_event,
    format_sse_event,
    format_sse_message,
    get_sse_headers,
)


class TestGetSSEHeaders:
    """Test get_sse_headers function"""

    def test_get_sse_headers(self):
        """Test SSE headers are correct"""
        headers = get_sse_headers()

        assert headers["Cache-Control"] == "no-cache"
        assert headers["Connection"] == "keep-alive"
        assert headers["Content-Type"] == "text/event-stream"
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert headers["Access-Control-Allow-Headers"] == "Last-Event-ID"


class TestFormatSSEMessage:
    """Test format_sse_message function"""

    def test_format_basic_message(self):
        """Test basic SSE message formatting"""
        result = format_sse_message("test_event", {"key": "value"})

        assert "event: test_event\n" in result
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_format_message_with_event_id(self):
        """Test SSE message with event ID"""
        result = format_sse_message("test_event", {"key": "value"}, event_id="evt-123")

        assert "event: test_event\n" in result
        assert "id: evt-123\n" in result
        assert "data: " in result

    def test_format_message_with_none_data(self):
        """Test SSE message with None data"""
        result = format_sse_message("test_event", None)

        assert "event: test_event\n" in result
        assert "data: \n" in result

    def test_format_message_with_nested_data(self):
        """Test SSE message with nested data"""
        data = {"outer": {"inner": {"deep": "value"}}}
        result = format_sse_message("test_event", data)

        assert "event: test_event\n" in result
        data_line = [line for line in result.split("\n") if line.startswith("data: ")][
            0
        ]
        parsed_data = json.loads(data_line.replace("data: ", ""))
        assert parsed_data == data

    def test_format_message_with_custom_serializer(self):
        """Test SSE message with custom serializer"""

        def custom_serializer(obj):
            if isinstance(obj, datetime):
                return "custom_date"
            return str(obj)

        data = {"date": datetime.now()}
        result = format_sse_message("test_event", data, serializer=custom_serializer)

        assert "custom_date" in result


class TestCreateMetadataEvent:
    """Test create_metadata_event function"""

    def test_create_metadata_event(self):
        """Test metadata event creation"""
        result = create_metadata_event("run-123")

        assert "event: metadata\n" in result
        assert "run-123" in result
        assert '"attempt":1' in result

    def test_create_metadata_event_with_event_id(self):
        """Test metadata event with event ID"""
        result = create_metadata_event("run-123", event_id="evt-1")

        assert "event: metadata\n" in result
        assert "id: evt-1\n" in result

    def test_create_metadata_event_with_custom_attempt(self):
        """Test metadata event with custom attempt"""
        result = create_metadata_event("run-123", attempt=3)

        assert '"attempt":3' in result


class TestCreateDebugEvent:
    """Test create_debug_event function"""

    def test_create_debug_event_basic(self):
        """Test basic debug event"""
        data = {"type": "task_result", "payload": {"result": "success"}}
        result = create_debug_event(data)

        assert "event: debug\n" in result
        assert "task_result" in result

    def test_create_debug_event_with_checkpoint_extraction(self):
        """Test debug event with checkpoint extraction"""
        data = {
            "type": "task_result",
            "payload": {
                "config": {
                    "configurable": {
                        "thread_id": "thread-123",
                        "checkpoint_id": "cp-456",
                        "checkpoint_ns": "ns",
                    }
                }
            },
        }
        result = create_debug_event(data)

        assert "thread-123" in result
        assert "cp-456" in result
        assert "checkpoint" in result

    def test_create_debug_event_with_parent_checkpoint_extraction(self):
        """Test debug event with parent checkpoint extraction"""
        data = {
            "type": "task_result",
            "payload": {
                "parent_config": {
                    "configurable": {
                        "thread_id": "thread-123",
                        "checkpoint_id": "cp-parent",
                    }
                }
            },
        }
        result = create_debug_event(data)

        assert "thread-123" in result
        assert "cp-parent" in result
        assert "parent_checkpoint" in result

    def test_create_debug_event_with_null_parent_config(self):
        """Test debug event with null parent config"""
        data = {"type": "task_result", "payload": {"parent_config": None}}
        result = create_debug_event(data)

        assert "event: debug\n" in result


class TestCreateEndEvent:
    """Test create_end_event function"""

    def test_create_end_event(self):
        """Test end event creation"""
        result = create_end_event()

        assert "event: end\n" in result
        assert "success" in result


class TestCreateErrorEvent:
    """Test create_error_event function"""

    def test_create_error_event(self):
        """Test error event creation"""
        result = create_error_event("Something went wrong")

        assert "event: error\n" in result
        assert "Something went wrong" in result
        assert "timestamp" in result


class TestCreateMessagesEvent:
    """Test create_messages_event function"""

    def test_create_messages_event_with_list(self):
        """Test messages event with list data"""
        messages = [{"role": "user", "content": "hello"}]
        result = create_messages_event(messages)

        assert "event: messages\n" in result
        assert "hello" in result

    def test_create_messages_event_with_tuple(self):
        """Test messages event with tuple (streaming format)"""
        message_chunk = {"content": "hello"}
        metadata = {"model": "gpt-4"}
        messages_data = (message_chunk, metadata)

        result = create_messages_event(messages_data)

        assert "event: messages\n" in result
        assert "hello" in result
        assert "gpt-4" in result

    def test_create_messages_event_with_custom_event_type(self):
        """Test messages event with custom event type"""
        messages = [{"role": "assistant", "content": "hi"}]
        result = create_messages_event(messages, event_type="messages/partial")

        assert "event: messages/partial\n" in result


class TestSSEEvent:
    """Test SSEEvent dataclass"""

    def test_sse_event_creation(self):
        """Test SSEEvent creation"""
        event = SSEEvent(id="evt-1", event="test", data={"key": "value"})

        assert event.id == "evt-1"
        assert event.event == "test"
        assert event.data == {"key": "value"}
        assert event.timestamp is not None

    def test_sse_event_format(self):
        """Test SSEEvent formatting"""
        event = SSEEvent(id="evt-1", event="test", data={"key": "value"})
        result = event.format()

        assert "id: evt-1\n" in result
        assert "event: test\n" in result
        assert "data: " in result
        assert result.endswith("\n\n")


class TestFormatSSEEvent:
    """Test format_sse_event legacy function"""

    def test_format_sse_event(self):
        """Test legacy format_sse_event"""
        result = format_sse_event("evt-1", "test", {"key": "value"})

        assert "id: evt-1\n" in result
        assert "event: test\n" in result
        assert "data: " in result

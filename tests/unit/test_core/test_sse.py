"""Unit tests for SSE utilities"""

import json
from datetime import datetime

from aegra.agent_server.core.sse import (
    SSEEvent,
    create_cancelled_event,
    create_checkpoints_event,
    create_chunk_event,
    create_complete_event,
    create_custom_event,
    create_debug_event,
    create_end_event,
    create_error_event,
    create_events_event,
    create_interrupted_event,
    create_logs_event,
    create_messages_event,
    create_metadata_event,
    create_start_event,
    create_state_event,
    create_subgraphs_event,
    create_tasks_event,
    create_updates_event,
    create_values_event,
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


class TestCreateValuesEvent:
    """Test create_values_event function"""

    def test_create_values_event(self):
        """Test values event creation"""
        data = {"messages": ["hello"], "context": {}}
        result = create_values_event(data)

        assert "event: values\n" in result
        assert "messages" in result


class TestCreateUpdatesEvent:
    """Test create_updates_event function"""

    def test_create_updates_event(self):
        """Test updates event creation"""
        data = {"node": "agent", "updates": {"key": "value"}}
        result = create_updates_event(data)

        assert "event: updates\n" in result
        assert "agent" in result


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
        assert "completed" in result


class TestCreateErrorEvent:
    """Test create_error_event function"""

    def test_create_error_event(self):
        """Test error event creation"""
        result = create_error_event("Something went wrong")

        assert "event: error\n" in result
        assert "Something went wrong" in result
        assert "timestamp" in result


class TestCreateEventsEvent:
    """Test create_events_event function"""

    def test_create_events_event(self):
        """Test events event creation"""
        data = {"event_type": "on_chat_model_stream"}
        result = create_events_event(data)

        assert "event: events\n" in result
        assert "on_chat_model_stream" in result


class TestCreateStateEvent:
    """Test create_state_event function"""

    def test_create_state_event(self):
        """Test state event creation"""
        data = {"messages": [], "next": ["node1"]}
        result = create_state_event(data)

        assert "event: state\n" in result


class TestCreateLogsEvent:
    """Test create_logs_event function"""

    def test_create_logs_event(self):
        """Test logs event creation"""
        data = {"log_level": "info", "message": "test"}
        result = create_logs_event(data)

        assert "event: logs\n" in result


class TestCreateTasksEvent:
    """Test create_tasks_event function"""

    def test_create_tasks_event(self):
        """Test tasks event creation"""
        data = {"tasks": [{"id": "task-1"}]}
        result = create_tasks_event(data)

        assert "event: tasks\n" in result


class TestCreateSubgraphsEvent:
    """Test create_subgraphs_event function"""

    def test_create_subgraphs_event(self):
        """Test subgraphs event creation"""
        data = {"subgraph_id": "sg-1"}
        result = create_subgraphs_event(data)

        assert "event: subgraphs\n" in result


class TestCreateCheckpointsEvent:
    """Test create_checkpoints_event function"""

    def test_create_checkpoints_event(self):
        """Test checkpoints event creation"""
        data = {"checkpoint_id": "cp-1"}
        result = create_checkpoints_event(data)

        assert "event: checkpoints\n" in result


class TestCreateCustomEvent:
    """Test create_custom_event function"""

    def test_create_custom_event(self):
        """Test custom event creation"""
        data = {"custom_field": "value"}
        result = create_custom_event(data)

        assert "event: custom\n" in result


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


class TestLegacyEventFunctions:
    """Test legacy event creation functions"""

    def test_create_start_event(self):
        """Test legacy start event"""
        result = create_start_event("run-123", 1)

        assert "event: start\n" in result
        assert "run-123" in result

    def test_create_chunk_event(self):
        """Test legacy chunk event"""
        result = create_chunk_event("run-123", 2, {"chunk": "data"})

        assert "event: chunk\n" in result
        assert "chunk" in result

    def test_create_complete_event(self):
        """Test legacy complete event"""
        result = create_complete_event("run-123", 3, {"result": "success"})

        assert "event: complete\n" in result
        assert "completed" in result

    def test_create_cancelled_event(self):
        """Test legacy cancelled event"""
        result = create_cancelled_event("run-123", 4)

        assert "event: cancelled\n" in result
        assert "cancelled" in result

    def test_create_interrupted_event(self):
        """Test legacy interrupted event"""
        result = create_interrupted_event("run-123", 5)

        assert "event: interrupted\n" in result
        assert "interrupted" in result

"""Unit tests for graph_streaming module.

Tests message accumulation, interrupt filtering, subgraph handling,
and event processing logic.
"""

import pytest
from langchain_core.messages import AIMessageChunk, BaseMessageChunk, HumanMessage

from agent_server.services.graph_streaming import (
    _normalize_checkpoint_payload,
    _normalize_checkpoint_task,
    _process_stream_event,
)


class TestNormalizeCheckpointTask:
    """Test checkpoint task normalization."""

    def test_normalize_task_with_configurable(self):
        """Test normalizing task with configurable state."""
        task = {
            "state": {
                "configurable": {
                    "checkpoint_id": "ckpt-123",
                    "thread_id": "thread-456",
                }
            },
            "other": "data",
        }

        result = _normalize_checkpoint_task(task)

        assert "checkpoint" in result
        assert result["checkpoint"] == {
            "checkpoint_id": "ckpt-123",
            "thread_id": "thread-456",
        }
        assert "state" not in result
        assert result["other"] == "data"

    def test_normalize_task_without_configurable(self):
        """Test normalizing task without configurable state."""
        task = {"state": {"other": "data"}, "other": "data"}

        result = _normalize_checkpoint_task(task)

        assert result == task  # Unchanged

    def test_normalize_task_without_state(self):
        """Test normalizing task without state."""
        task = {"other": "data"}

        result = _normalize_checkpoint_task(task)

        assert result == task  # Unchanged

    def test_normalize_task_with_empty_configurable(self):
        """Test normalizing task with empty configurable."""
        task = {"state": {"configurable": {}}, "other": "data"}

        result = _normalize_checkpoint_task(task)

        assert result == task  # Unchanged (empty configurable)


class TestNormalizeCheckpointPayload:
    """Test checkpoint payload normalization."""

    def test_normalize_payload_with_tasks(self):
        """Test normalizing payload with tasks."""
        payload = {
            "tasks": [
                {
                    "state": {
                        "configurable": {"checkpoint_id": "ckpt-1", "thread_id": "t1"}
                    }
                },
                {
                    "state": {
                        "configurable": {"checkpoint_id": "ckpt-2", "thread_id": "t2"}
                    }
                },
            ],
            "other": "data",
        }

        result = _normalize_checkpoint_payload(payload)

        assert result is not None
        assert len(result["tasks"]) == 2
        assert "checkpoint" in result["tasks"][0]
        assert "checkpoint" in result["tasks"][1]
        assert "state" not in result["tasks"][0]
        assert "state" not in result["tasks"][1]
        assert result["other"] == "data"

    def test_normalize_payload_none(self):
        """Test normalizing None payload."""
        result = _normalize_checkpoint_payload(None)
        assert result is None

    def test_normalize_payload_without_tasks(self):
        """Test normalizing payload without tasks."""
        payload = {"other": "data"}

        # Function expects "tasks" key, so this should raise KeyError
        # In practice, payloads should always have "tasks" key
        with pytest.raises(KeyError):
            _normalize_checkpoint_payload(payload)


class TestProcessStreamEvent:
    """Test _process_stream_event function."""

    def test_messages_mode_partial_chunk(self):
        """Test processing partial message chunk."""
        messages = {}
        chunk = (AIMessageChunk(id="msg-1", content="Hello"), {"metadata": "test"})

        results = _process_stream_event(
            mode="messages",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages"],
            messages=messages,
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert len(results) == 2
        # First event should be metadata
        assert results[0][0] == "messages/metadata"
        # Second event should be partial
        assert results[1][0] == "messages/partial"
        assert "msg-1" in messages

    def test_messages_mode_complete_message(self):
        """Test processing complete message."""
        messages = {}
        chunk = (HumanMessage(id="msg-1", content="Hello"), {"metadata": "test"})

        results = _process_stream_event(
            mode="messages",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages"],
            messages=messages,
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert len(results) == 2
        assert results[0][0] == "messages/metadata"
        assert results[1][0] == "messages/complete"

    def test_messages_mode_accumulation(self):
        """Test message chunk accumulation."""
        messages = {}
        chunk1 = (AIMessageChunk(id="msg-1", content="Hello"), {})
        chunk2 = (AIMessageChunk(id="msg-1", content=" World"), {})

        # First chunk
        results1 = _process_stream_event(
            mode="messages",
            chunk=chunk1,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages"],
            messages=messages,
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        # Second chunk (same message ID)
        results2 = _process_stream_event(
            mode="messages",
            chunk=chunk2,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages"],
            messages=messages,
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results1 is not None
        assert results2 is not None
        # First chunk should have metadata + partial
        assert len(results1) == 2
        # Second chunk should only have partial (no metadata)
        assert len(results2) == 1
        assert results2[0][0] == "messages/partial"
        # Accumulated message should have both chunks
        assert messages["msg-1"].content == "Hello World"

    def test_messages_tuple_mode(self):
        """Test messages-tuple mode passes through raw format."""
        chunk = ("messages", {"content": "test"})

        results = _process_stream_event(
            mode="messages",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages-tuple"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert len(results) == 1
        assert results[0][0] == "messages"
        assert results[0][1] == chunk

    def test_messages_tuple_mode_with_subgraphs(self):
        """Test messages-tuple mode with subgraph namespace."""
        chunk = ("messages", {"content": "test"})

        results = _process_stream_event(
            mode="messages",
            chunk=chunk,
            namespace=["subagent"],
            subgraphs=True,
            stream_mode=["messages-tuple"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert len(results) == 1
        assert results[0][0] == "messages|subagent"

    def test_values_mode(self):
        """Test values mode processing."""
        chunk = {"key": "value"}

        results = _process_stream_event(
            mode="values",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["values"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert len(results) == 1
        assert results[0][0] == "values"
        assert results[0][1] == chunk

    def test_values_mode_with_subgraphs(self):
        """Test values mode with subgraph namespace."""
        chunk = {"key": "value"}

        results = _process_stream_event(
            mode="values",
            chunk=chunk,
            namespace=["subagent"],
            subgraphs=True,
            stream_mode=["values"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert len(results) == 1
        assert results[0][0] == "values|subagent"

    def test_subgraph_namespace_list(self):
        """Test subgraph namespace as list."""
        chunk = {"data": "test"}

        results = _process_stream_event(
            mode="values",
            chunk=chunk,
            namespace=["agent", "subagent"],
            subgraphs=True,
            stream_mode=["values"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert results[0][0] == "values|agent|subagent"

    def test_subgraph_namespace_string(self):
        """Test subgraph namespace as string."""
        chunk = {"data": "test"}

        results = _process_stream_event(
            mode="values",
            chunk=chunk,
            namespace="subagent",
            subgraphs=True,
            stream_mode=["values"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert results[0][0] == "values|subagent"

    def test_interrupt_updates_conversion(self):
        """Test interrupt updates are converted to values events."""
        chunk = {"__interrupt__": [{"node": "test"}]}

        results = _process_stream_event(
            mode="updates",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["values"],  # updates not explicitly requested
            messages={},
            only_interrupt_updates=True,  # Only interrupt updates
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert len(results) == 1
        assert results[0][0] == "values"
        assert results[0][1] == chunk

    def test_interrupt_updates_with_subgraphs(self):
        """Test interrupt updates with subgraph namespace."""
        chunk = {"__interrupt__": [{"node": "test"}]}

        results = _process_stream_event(
            mode="updates",
            chunk=chunk,
            namespace=["subagent"],
            subgraphs=True,
            stream_mode=["values"],
            messages={},
            only_interrupt_updates=True,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert results[0][0] == "values|subagent"

    def test_non_interrupt_updates_filtered(self):
        """Test non-interrupt updates are filtered when only_interrupt_updates=True."""
        chunk = {"messages": [{"role": "ai", "content": "test"}]}

        results = _process_stream_event(
            mode="updates",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["values"],
            messages={},
            only_interrupt_updates=True,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        # Should return None (filtered out)
        assert results is None

    def test_empty_interrupt_list_filtered(self):
        """Test updates with empty interrupt list are filtered."""
        chunk = {"__interrupt__": []}

        results = _process_stream_event(
            mode="updates",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["values"],
            messages={},
            only_interrupt_updates=True,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is None

    def test_updates_mode_explicitly_requested(self):
        """Test updates mode when explicitly requested."""
        chunk = {"messages": [{"role": "ai", "content": "test"}]}

        results = _process_stream_event(
            mode="updates",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["updates"],  # Explicitly requested
            messages={},
            only_interrupt_updates=False,  # Not filtering
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert results[0][0] == "updates"

    def test_debug_checkpoint_event(self):
        """Test debug checkpoint event processing."""
        checkpoint_called = []
        chunk = {
            "type": "checkpoint",
            "payload": {
                "tasks": [
                    {
                        "state": {
                            "configurable": {
                                "checkpoint_id": "ckpt-1",
                                "thread_id": "t1",
                            }
                        }
                    }
                ]
            },
        }

        def on_checkpoint(payload):
            checkpoint_called.append(payload)

        _process_stream_event(
            mode="debug",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["debug"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=on_checkpoint,
            on_task_result=lambda _: None,
        )

        # Checkpoint callback should be called
        assert len(checkpoint_called) == 1
        assert checkpoint_called[0] is not None
        # Normalized payload should have checkpoint instead of state
        assert "checkpoint" in checkpoint_called[0]["tasks"][0]

    def test_debug_task_result_event(self):
        """Test debug task result event processing."""
        task_result_called = []
        chunk = {
            "type": "task_result",
            "payload": {"result": "test"},
        }

        def on_task_result(payload):
            task_result_called.append(payload)

        _process_stream_event(
            mode="debug",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["debug"],
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=on_task_result,
        )

        # Task result callback should be called
        assert len(task_result_called) == 1
        assert task_result_called[0] == {"result": "test"}

    def test_dict_message_chunk_detection(self):
        """Test detecting chunk type from dict message."""
        messages = {}
        # Dict with chunk indicator in role (not type field)
        chunk = (
            {
                "id": "msg-1",
                "content": "Hello",
                "role": "ai_chunk",  # Has chunk indicator
            },
            {},
        )

        results = _process_stream_event(
            mode="messages",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages"],
            messages=messages,
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert results[1][0] == "messages/partial"
        assert isinstance(messages["msg-1"], BaseMessageChunk)

    def test_dict_complete_message_conversion(self):
        """Test converting dict to complete message."""
        messages = {}
        # Dict without chunk indicator
        chunk = (
            {
                "id": "msg-1",
                "type": "human",
                "content": "Hello",
            },
            {},
        )

        results = _process_stream_event(
            mode="messages",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages"],
            messages=messages,
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert results[1][0] == "messages/complete"

    def test_mode_not_in_stream_mode(self):
        """Test event with mode not in requested stream_mode."""
        chunk = {"data": "test"}

        results = _process_stream_event(
            mode="custom_mode",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["values", "messages"],  # custom_mode not requested
            messages={},
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        # Should return None if mode not in stream_mode and not updates
        assert results is None

    def test_messages_mode_dict_with_role(self):
        """Test message dict with role field."""
        messages = {}
        chunk = (
            {
                "id": "msg-1",
                "role": "ai_chunk",  # Has chunk in role
                "content": "Hello",
            },
            {},
        )

        results = _process_stream_event(
            mode="messages",
            chunk=chunk,
            namespace=None,
            subgraphs=False,
            stream_mode=["messages"],
            messages=messages,
            only_interrupt_updates=False,
            on_checkpoint=lambda _: None,
            on_task_result=lambda _: None,
        )

        assert results is not None
        assert results[1][0] == "messages/partial"

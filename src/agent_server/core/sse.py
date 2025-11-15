"""Server-Sent Events utilities and formatting"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Import our serializer for handling complex objects
from .serializers import GeneralSerializer

# Global serializer instance
_serializer = GeneralSerializer()


def get_sse_headers() -> dict[str, str]:
    """Get standard SSE headers"""
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Last-Event-ID",
    }


def format_sse_message(
    event: str,
    data: Any,
    event_id: str | None = None,
    serializer: Callable[[Any], Any] | None = None,
) -> str:
    """Format a message as Server-Sent Event following SSE standard

    Args:
        event: SSE event type
        data: Data to serialize and send
        event_id: Optional event ID
        serializer: Optional custom serializer function
    """
    lines = []

    lines.append(f"event: {event}")

    # Convert data to JSON string
    if data is None:
        data_str = ""
    else:
        # Use our general serializer by default to handle complex objects
        default_serializer = serializer or _serializer.serialize
        data_str = json.dumps(data, default=default_serializer, separators=(",", ":"))

    lines.append(f"data: {data_str}")

    if event_id:
        lines.append(f"id: {event_id}")

    lines.append("")  # Empty line to end the event

    return "\n".join(lines) + "\n"


def create_metadata_event(
    run_id: str, event_id: str | None = None, attempt: int = 1
) -> str:
    """Create metadata event for LangSmith Studio compatibility"""
    data = {"run_id": run_id, "attempt": attempt}
    return format_sse_message("metadata", data, event_id)


def create_values_event(chunk_data: dict[str, Any], event_id: str | None = None) -> str:
    """Create values event"""
    return format_sse_message("values", chunk_data, event_id)


def create_updates_event(
    updates_data: dict[str, Any], event_id: str | None = None
) -> str:
    """Create updates event"""
    return format_sse_message("updates", updates_data, event_id)


def create_debug_event(debug_data: dict[str, Any], event_id: str | None = None) -> str:
    """Create debug event with checkpoint fields for LangSmith Studio compatibility"""

    # Add checkpoint and parent_checkpoint fields if not present
    if "payload" in debug_data and isinstance(debug_data["payload"], dict):
        payload = debug_data["payload"]

        # Extract checkpoint from config.configurable
        if "checkpoint" not in payload and "config" in payload:
            config = payload.get("config", {})
            if isinstance(config, dict) and "configurable" in config:
                configurable = config["configurable"]
                if isinstance(configurable, dict):
                    payload["checkpoint"] = {
                        "thread_id": configurable.get("thread_id"),
                        "checkpoint_id": configurable.get("checkpoint_id"),
                        "checkpoint_ns": configurable.get("checkpoint_ns", ""),
                    }

        # Extract parent_checkpoint from parent_config.configurable
        if "parent_checkpoint" not in payload and "parent_config" in payload:
            parent_config = payload.get("parent_config")
            if isinstance(parent_config, dict) and "configurable" in parent_config:
                configurable = parent_config["configurable"]
                if isinstance(configurable, dict):
                    payload["parent_checkpoint"] = {
                        "thread_id": configurable.get("thread_id"),
                        "checkpoint_id": configurable.get("checkpoint_id"),
                        "checkpoint_ns": configurable.get("checkpoint_ns", ""),
                    }
            elif parent_config is None:
                payload["parent_checkpoint"] = None

    return format_sse_message("debug", debug_data, event_id)


def create_end_event(event_id: str | None = None) -> str:
    """Create end event - signals completion of stream

    Uses standard status: "success" instead of "completed"
    """
    return format_sse_message("end", {"status": "success"}, event_id)


def create_error_event(error: str, event_id: str | None = None) -> str:
    """Create error event"""
    data = {"error": error, "timestamp": datetime.now(UTC).isoformat()}
    return format_sse_message("error", data, event_id)


def create_events_event(event_data: dict[str, Any], event_id: str | None = None) -> str:
    """Create events stream mode event"""
    return format_sse_message("events", event_data, event_id)


def create_state_event(state_data: dict[str, Any], event_id: str | None = None) -> str:
    """Create state event"""
    return format_sse_message("state", state_data, event_id)


def create_logs_event(logs_data: dict[str, Any], event_id: str | None = None) -> str:
    """Create logs event"""
    return format_sse_message("logs", logs_data, event_id)


def create_tasks_event(tasks_data: dict[str, Any], event_id: str | None = None) -> str:
    """Create tasks event"""
    return format_sse_message("tasks", tasks_data, event_id)


def create_subgraphs_event(
    subgraphs_data: dict[str, Any], event_id: str | None = None
) -> str:
    """Create subgraphs event"""
    return format_sse_message("subgraphs", subgraphs_data, event_id)


def create_checkpoints_event(
    checkpoints_data: dict[str, Any], event_id: str | None = None
) -> str:
    """Create checkpoints event"""
    return format_sse_message("checkpoints", checkpoints_data, event_id)


def create_custom_event(
    custom_data: dict[str, Any], event_id: str | None = None
) -> str:
    """Create custom event"""
    return format_sse_message("custom", custom_data, event_id)


def create_messages_event(
    messages_data: Any, event_type: str = "messages", event_id: str | None = None
) -> str:
    """Create messages event (messages, messages/partial, messages/complete, messages/metadata)"""
    # Handle tuple format for token streaming: (message_chunk, metadata)
    if isinstance(messages_data, tuple) and len(messages_data) == 2:
        message_chunk, metadata = messages_data
        # Format as expected by LangGraph SDK client
        data = [message_chunk, metadata]
        return format_sse_message(event_type, data, event_id)
    else:
        # Handle list of messages format
        return format_sse_message(event_type, messages_data, event_id)


# Legacy compatibility functions (deprecated)
@dataclass
class SSEEvent:
    """Legacy SSE Event data structure - deprecated"""

    id: str
    event: str
    data: dict[str, Any]
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)

    def format(self) -> str:
        """Format as proper SSE event - deprecated"""
        json_data = json.dumps(self.data, default=str)
        return f"id: {self.id}\nevent: {self.event}\ndata: {json_data}\n\n"


def format_sse_event(id: str, event: str, data: dict[str, Any]) -> str:
    """Legacy format function - deprecated"""
    json_data = json.dumps(data, default=str)
    return f"id: {id}\nevent: {event}\ndata: {json_data}\n\n"


# Legacy event creation functions - deprecated but kept for compatibility
def create_start_event(run_id: str, event_counter: int) -> str:
    """Legacy start event - deprecated, use create_metadata_event instead"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="start",
        data={
            "type": "run_start",
            "run_id": run_id,
            "status": "running",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def create_chunk_event(
    run_id: str, event_counter: int, chunk_data: dict[str, Any]
) -> str:
    """Legacy chunk event - deprecated, use create_values_event instead"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="chunk",
        data={
            "type": "execution_chunk",
            "chunk": chunk_data,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def create_complete_event(run_id: str, event_counter: int, final_output: Any) -> str:
    """Legacy complete event - deprecated, use create_end_event instead

    Note: Uses legacy "completed" status for backward compatibility with old clients.
    """
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="complete",
        data={
            "type": "run_complete",
            "status": "success",  # Use standard status
            "final_output": final_output,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def create_cancelled_event(run_id: str, event_counter: int) -> str:
    """Legacy cancelled event - deprecated

    Note: Uses "interrupted" status instead of legacy "cancelled"
    """
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="cancelled",
        data={
            "type": "run_cancelled",
            "status": "interrupted",  # Use standard status instead of legacy "cancelled"
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


def create_interrupted_event(run_id: str, event_counter: int) -> str:
    """Legacy interrupted event - deprecated"""
    return format_sse_event(
        id=f"{run_id}_event_{event_counter}",
        event="interrupted",
        data={
            "type": "run_interrupted",
            "status": "interrupted",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )

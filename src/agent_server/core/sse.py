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


# Legacy compatibility - used by event_store.py
@dataclass
class SSEEvent:
    """SSE Event data structure for event storage"""

    id: str
    event: str
    data: dict[str, Any]
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(UTC)

    def format(self) -> str:
        """Format as proper SSE event"""
        json_data = json.dumps(self.data, default=str)
        return f"id: {self.id}\nevent: {self.event}\ndata: {json_data}\n\n"


def format_sse_event(id: str, event: str, data: dict[str, Any]) -> str:
    """Format SSE event (used by event_store)"""
    json_data = json.dumps(data, default=str)
    return f"id: {id}\nevent: {event}\ndata: {json_data}\n\n"

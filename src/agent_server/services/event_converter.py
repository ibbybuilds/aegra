"""Event converter for SSE streaming"""

from typing import Any

from ..core.sse import (
    create_debug_event,
    create_end_event,
    create_error_event,
    create_messages_event,
    create_metadata_event,
    format_sse_message,
)


class EventConverter:
    """Converts events to SSE format"""

    def __init__(self):
        """Initialize event converter"""
        self.subgraphs: bool = False

    def set_subgraphs(self, subgraphs: bool) -> None:
        """Set whether subgraphs mode is enabled for namespace extraction"""
        self.subgraphs = subgraphs

    def convert_raw_to_sse(self, event_id: str, raw_event: Any) -> str | None:
        """Convert raw event to SSE format"""
        stream_mode, payload, namespace = self._parse_raw_event(raw_event)
        return self._create_sse_event(stream_mode, payload, event_id, namespace)

    def convert_stored_to_sse(self, stored_event, run_id: str = None) -> str | None:
        """Convert stored event to SSE format"""
        event_type = stored_event.event
        data = stored_event.data
        event_id = stored_event.id

        # Handle special cases with custom logic
        if event_type == "messages":
            message_chunk = data.get("message_chunk")
            metadata = data.get("metadata")
            if message_chunk is None:
                return None
            message_data = (
                (message_chunk, metadata) if metadata is not None else message_chunk
            )
            return create_messages_event(message_data, event_id=event_id)
        elif event_type == "metadata":
            return create_metadata_event(run_id, event_id)
        elif event_type == "debug":
            return create_debug_event(data.get("debug"), event_id)
        elif event_type == "end":
            return create_end_event(event_id)
        elif event_type == "error":
            return create_error_event(data.get("error"), event_id)
        else:
            # Handle all other event types generically (values, state, logs, tasks, etc.)
            # Extract payload - try common patterns
            payload = data.get(event_type) or data.get("chunk") or data
            return format_sse_message(event_type, payload, event_id)

    def _parse_raw_event(self, raw_event: Any) -> tuple[str, Any, list[str] | None]:
        """
        Parse raw event into (stream_mode, payload, namespace).

        When subgraphs=True, 3-tuple format is (namespace, mode, chunk).
        When subgraphs=False, 3-tuple format is (node_path, mode, chunk) for legacy support.
        """
        namespace = None

        if isinstance(raw_event, tuple):
            if len(raw_event) == 2:
                # Standard format: (mode, chunk)
                return raw_event[0], raw_event[1], None
            elif len(raw_event) == 3:
                if self.subgraphs:
                    # Subgraphs format: (namespace, mode, chunk)
                    namespace, mode, chunk = raw_event
                    # Normalize namespace to list format
                    if namespace is None or (
                        isinstance(namespace, (list, tuple)) and not namespace
                    ):
                        # Handle None or empty tuple/list - no namespace prefix
                        namespace_list = None
                    elif isinstance(namespace, (list, tuple)):
                        # Convert tuple/list to list of strings
                        namespace_list = [str(item) for item in namespace]
                    elif isinstance(namespace, str):
                        # Handle string namespace (shouldn't happen but be safe)
                        namespace_list = [namespace] if namespace else None
                    else:
                        # Fallback - shouldn't reach here
                        namespace_list = [str(namespace)]
                    return mode, chunk, namespace_list
                else:
                    # Legacy format: (node_path, mode, chunk)
                    return raw_event[1], raw_event[2], None

        # Non-tuple events are values mode
        return "values", raw_event, None

    def _create_sse_event(
        self,
        stream_mode: str,
        payload: Any,
        event_id: str,
        namespace: list[str] | None = None,
    ) -> str | None:
        """
        Create SSE event based on stream mode.

        Args:
            stream_mode: The stream mode (e.g., "messages", "values")
            payload: The event payload
            event_id: The event ID
            namespace: Optional namespace for subgraph events (e.g., ["subagent_name"])

        Returns:
            SSE-formatted event string or None
        """
        # Prefix event type with namespace if subgraphs enabled
        if self.subgraphs and namespace:
            event_type = f"{stream_mode}|{'|'.join(namespace)}"
        else:
            event_type = stream_mode

        # Handle updates events (rarely reached - updates are filtered in graph_streaming)
        if stream_mode == "updates":
            if isinstance(payload, dict) and "__interrupt__" in payload:
                # Convert interrupt updates to values events
                if self.subgraphs and namespace:
                    event_type = f"values|{'|'.join(namespace)}"
                else:
                    event_type = "values"
                return format_sse_message(event_type, payload, event_id)
            else:
                # Non-interrupt updates (pass through as-is)
                return format_sse_message(event_type, payload, event_id)

        # Handle specific message event types (Studio compatibility and standard messages)
        if stream_mode in (
            "messages/metadata",
            "messages/partial",
            "messages/complete",
        ):
            # Studio-specific message events - pass through as-is
            return format_sse_message(stream_mode, payload, event_id)
        elif stream_mode == "messages" or event_type.startswith("messages"):
            return create_messages_event(
                payload, event_type=event_type, event_id=event_id
            )
        elif stream_mode == "values" or event_type.startswith("values"):
            # For values events, use format_sse_message directly to support namespaces
            return format_sse_message(event_type, payload, event_id)
        elif stream_mode == "debug":
            return create_debug_event(payload, event_id)
        elif stream_mode == "end":
            return create_end_event(event_id)
        elif stream_mode == "error":
            return create_error_event(payload, event_id)
        else:
            # Generic handler for all other event types (state, logs, tasks, events, etc.)
            # This automatically supports any new event types without code changes
            return format_sse_message(event_type, payload, event_id)

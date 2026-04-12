"""Event converter for SSE streaming"""

from typing import Any

from aegra_api.core.sse import (
    create_debug_event,
    create_end_event,
    create_error_event,
    create_messages_event,
    format_sse_message,
)


class EventConverter:
    """Converts events to SSE format"""

    def __init__(self) -> None:
        """Initialize event converter"""
        self.subgraphs: bool = False

    def set_subgraphs(self, subgraphs: bool) -> None:
        """Set whether subgraphs mode is enabled for namespace extraction"""
        self.subgraphs = subgraphs

    def convert_raw_to_sse(self, event_id: str, raw_event: Any) -> str | None:
        """Convert raw event to SSE format"""
        stream_mode, payload, namespace = self._parse_raw_event(raw_event)
        return self._create_sse_event(stream_mode, payload, event_id, namespace)

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
                    if namespace is None or (isinstance(namespace, (list, tuple)) and not namespace):
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

        # Handle updates events — pass through as-is.
        # Interrupt filtering/remapping is already done upstream in graph_streaming:
        # when "updates" is NOT explicitly requested, interrupt updates are remapped
        # to "values" before reaching the converter. When "updates" IS explicitly
        # requested, all update events (including interrupts) should be "updates".
        if stream_mode == "updates":
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
            return create_messages_event(payload, event_type=event_type, event_id=event_id)
        elif stream_mode == "values" or event_type.startswith("values"):
            # For values events, use format_sse_message directly to support namespaces
            return format_sse_message(event_type, payload, event_id)
        elif stream_mode == "debug":
            return create_debug_event(payload, event_id)
        elif stream_mode == "end":
            status = payload.get("status", "success") if isinstance(payload, dict) else "success"
            return create_end_event(event_id, status=status)
        elif stream_mode == "error":
            return create_error_event(payload, event_id)
        else:
            # Generic handler for all other event types (state, logs, tasks, events, etc.)
            # This automatically supports any new event types without code changes
            return format_sse_message(event_type, payload, event_id)

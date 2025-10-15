"""Event converter for SSE streaming"""

from typing import Any

from ..core.sse import (
    create_checkpoints_event,
    create_custom_event,
    create_debug_event,
    create_end_event,
    create_error_event,
    create_events_event,
    create_logs_event,
    create_messages_event,
    create_metadata_event,
    create_state_event,
    create_subgraphs_event,
    create_tasks_event,
    create_updates_event,
    create_values_event,
)


class EventConverter:
    """Converts events to SSE format"""

    def convert_raw_to_sse(self, event_id: str, raw_event: Any) -> str | None:
        """Convert raw event to SSE format"""
        stream_mode, payload = self._parse_raw_event(raw_event)
        return self._create_sse_event(stream_mode, payload, event_id)

    def convert_stored_to_sse(self, stored_event, run_id: str = None) -> str | None:
        """Convert stored event to SSE format"""
        event_type = stored_event.event
        data = stored_event.data
        event_id = stored_event.id

        if event_type == "messages":
            message_chunk = data.get("message_chunk")
            metadata = data.get("metadata")
            if message_chunk is None:
                return None
            message_data = (
                (message_chunk, metadata) if metadata is not None else message_chunk
            )
            return create_messages_event(message_data, event_id=event_id)
        elif event_type == "values":
            return create_values_event(data.get("chunk"), event_id)
        elif event_type == "metadata":
            return create_metadata_event(run_id, event_id)
        elif event_type == "state":
            return create_state_event(data.get("state"), event_id)
        elif event_type == "logs":
            return create_logs_event(data.get("logs"), event_id)
        elif event_type == "tasks":
            return create_tasks_event(data.get("tasks"), event_id)
        elif event_type == "subgraphs":
            return create_subgraphs_event(data.get("subgraphs"), event_id)
        elif event_type == "debug":
            return create_debug_event(data.get("debug"), event_id)
        elif event_type == "events":
            return create_events_event(data.get("event"), event_id)
        elif event_type == "end":
            return create_end_event(event_id)
        elif event_type == "error":
            return create_error_event(data.get("error"), event_id)
        return None

    def _parse_raw_event(self, raw_event: Any) -> tuple[str, Any]:
        """Parse raw event into (stream_mode, payload)"""
        if isinstance(raw_event, tuple):
            if len(raw_event) == 2:
                return raw_event[0], raw_event[1]
            elif len(raw_event) == 3:
                # Ignore node_path for now, just return mode and payload
                return raw_event[1], raw_event[2]

        return "values", raw_event

    def _create_sse_event(
        self, stream_mode: str, payload: Any, event_id: str
    ) -> str | None:
        """Create SSE event based on stream mode"""
        if stream_mode == "messages":
            return create_messages_event(payload, event_id=event_id)
        elif stream_mode == "values":
            return create_values_event(payload, event_id)
        elif stream_mode == "updates":
            # Convert interrupt updates to values, otherwise keep as updates
            if isinstance(payload, dict) and "__interrupt__" in payload:
                return create_values_event(payload, event_id)
            else:
                return create_updates_event(payload, event_id)
        elif stream_mode == "state":
            return create_state_event(payload, event_id)
        elif stream_mode == "logs":
            return create_logs_event(payload, event_id)
        elif stream_mode == "tasks":
            return create_tasks_event(payload, event_id)
        elif stream_mode == "subgraphs":
            return create_subgraphs_event(payload, event_id)
        elif stream_mode == "debug":
            return create_debug_event(payload, event_id)
        elif stream_mode == "events":
            return create_events_event(payload, event_id)
        elif stream_mode == "checkpoints":
            return create_checkpoints_event(payload, event_id)
        elif stream_mode == "custom":
            return create_custom_event(payload, event_id)
        elif stream_mode == "end":
            return create_end_event(event_id)

        return None

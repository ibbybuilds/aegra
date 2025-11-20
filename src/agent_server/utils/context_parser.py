"""Context parsing utilities for different graph types."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_context_for_graph(
    graph_id: str, context_dict: dict[str, Any] | None
) -> Any:
    """
    Parse context based on the graph type.

    Args:
        graph_id: The graph identifier (e.g., "ava", "react_agent")
        context_dict: Raw context dictionary from the API request

    Returns:
        Parsed context appropriate for the graph type

    Note:
        All graphs (including AVA) now use runtime.context pattern.
        For AVA, we extract the "call_context" nested dict since ava-core's
        context_schema expects CallContext structure directly (not nested).
        Other graphs receive the raw context dict.
    """
    print(f"[Context Parser] Parsing context for graph_id={graph_id}")

    if context_dict is None:
        return None

    # For AVA, extract call_context from the nested structure
    # HTTP request: {"context": {"call_context": {...}}}
    # ava-core expects: {...} (CallContext structure directly)
    if graph_id == "ava" and "call_context" in context_dict:
        call_context = context_dict["call_context"]
        print(f"[Context Parser] Extracted call_context for AVA: {type(call_context)}")
        return call_context

    # For other graphs, pass through the raw context dict
    print(f"[Context Parser] Passing through raw context for graph_id={graph_id}")
    return context_dict

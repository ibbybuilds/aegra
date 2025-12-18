"""Context parsing utilities for different graph types."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_context_for_graph(graph_id: str, context_dict: dict[str, Any] | None) -> Any:
    """
    Parse context based on the graph type.

    Args:
        graph_id: The graph identifier (e.g., "ava", "ava_v1", "react_agent")
        context_dict: Raw context dictionary from the API request

    Returns:
        Parsed context appropriate for the graph type

    Note:
        All graphs (including AVA and AVA_V1) now use runtime.context pattern.
        For AVA and AVA_V1, we ensure the call_context dict is passed directly (not wrapped).
        LangGraph will validate and convert it to a CallContext dataclass internally.
        Other graphs receive the raw context dict.
    """
    logger.info(f"[Context Parser] Parsing context for graph_id={graph_id}")

    if context_dict is None:
        return None

    # For AVA and AVA_V1, extract call_context from the nested structure
    # HTTP request: {"context": {"call_context": {...}}}
    # LangGraph expects: {...} (CallContext structure directly as dict)
    if graph_id in ("ava", "ava_v1") and "call_context" in context_dict:
        call_context = context_dict["call_context"]
        # Ensure it's a dict (not already a dataclass instance)
        if isinstance(call_context, dict):
            logger.info(f"[Context Parser] Extracted call_context dict for {graph_id}")
            return call_context
        else:
            # If it's already a dataclass, convert to dict
            logger.warning(
                f"[Context Parser] call_context is not a dict (type={type(call_context)}), "
                "attempting to convert to dict"
            )
            if hasattr(call_context, "__dict__"):
                return vars(call_context)
            elif hasattr(call_context, "model_dump"):
                return call_context.model_dump()
            else:
                logger.error(
                    "[Context Parser] Unable to convert call_context to dict, passing as-is"
                )
                return call_context

    # For other graphs, pass through the raw context dict
    logger.info(f"[Context Parser] Passing through raw context for graph_id={graph_id}")
    return context_dict

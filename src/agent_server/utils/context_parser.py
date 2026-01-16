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
    logger.info("=" * 80)
    logger.info("[CONTEXT_MIGRATION] context_parser.parse_context_for_graph() called")
    logger.info(f"[CONTEXT_MIGRATION] graph_id: {graph_id}")
    logger.info(
        f"[CONTEXT_MIGRATION] context_dict keys: {list(context_dict.keys()) if context_dict else None}"
    )
    logger.info("=" * 80)

    if context_dict is None:
        logger.info("[CONTEXT_MIGRATION] context_dict is None, returning None")
        return None

    # For AVA and AVA_V1, handle context in two formats:
    # 1. NEW /state endpoint: {"type": "property_specific", "property": {...}}
    # 2. OLD /runs endpoint: {"call_context": {"type": "property_specific", ...}}
    if graph_id in ("ava", "ava_v1"):
        # Check if it's already the direct format (has 'type' field at top level)
        if "type" in context_dict:
            logger.info(
                "[CONTEXT_MIGRATION] ✓ Using direct context format (NEW /state pattern)"
            )
            logger.info(f"[CONTEXT_MIGRATION] Context type: {context_dict.get('type')}")
            return context_dict
        # Otherwise, check for nested call_context (OLD /runs pattern)
        elif "call_context" in context_dict:
            call_context = context_dict["call_context"]
            # Ensure it's a dict (not already a dataclass instance)
            if isinstance(call_context, dict):
                logger.info(
                    "[CONTEXT_MIGRATION] ✓ Extracted nested call_context (OLD /runs pattern)"
                )
                logger.info(
                    f"[CONTEXT_MIGRATION] Extracted call_context type: {call_context.get('type')}"
                )
                return call_context
            else:
                # If it's already a dataclass, convert to dict
                logger.warning(
                    f"[CONTEXT_MIGRATION] call_context is not a dict (type={type(call_context)}), "
                    "attempting to convert to dict"
                )
                if hasattr(call_context, "__dict__"):
                    return vars(call_context)
                elif hasattr(call_context, "model_dump"):
                    return call_context.model_dump()
                else:
                    logger.error(
                        "[CONTEXT_MIGRATION] Unable to convert call_context to dict, passing as-is"
                    )
                    return call_context
        else:
            logger.warning(
                f"[CONTEXT_MIGRATION] No 'type' or 'call_context' field found in context_dict for {graph_id}"
            )
            logger.warning("[CONTEXT_MIGRATION] Passing through raw context as-is")

    # For other graphs, pass through the raw context dict
    logger.info(f"[Context Parser] Passing through raw context for graph_id={graph_id}")
    return context_dict

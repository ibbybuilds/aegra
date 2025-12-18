"""State management primitives for context stack control."""

import json
import logging
from typing import Annotated, Any, Dict

from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


def _context_matches(ctx1: Dict[str, Any], ctx2: Dict[str, Any]) -> bool:
    """Check if two context objects are the same.

    Contexts match if they have the same type and same identifier fields.

    Args:
        ctx1: First context object
        ctx2: Second context object

    Returns:
        True if contexts match, False otherwise
    """
    # Must have same type
    if ctx1.get("type") != ctx2.get("type"):
        return False

    # Compare all identifier fields (excluding type)
    ctx1_identifiers = {k: v for k, v in ctx1.items() if k != "type"}
    ctx2_identifiers = {k: v for k, v in ctx2.items() if k != "type"}

    return ctx1_identifiers == ctx2_identifiers


@tool(description="Push a new focus object onto the context_stack")
def push_context(
    context_object: Dict[str, Any],
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Push a new focus object onto the context_stack.

    PURPOSE:
        Track the user's current conversational focus (e.g., viewing hotel list,
        viewing rooms for a specific hotel, viewing hotel details). This enables
        the agent to maintain context across the conversation and support going
        "back" to previous states.

    STACK ORDER RULES:
        Enforces idempotency (no duplicate pushes) and navigation constraints:
        - HotelList → RoomList: OK (drilling down from hotels to rooms)
        - RoomList → HotelList: ERROR (must pop_context first to go back)
        - RoomList → RoomList: ERROR (must pop_context first before new room search)
        - HotelDetails: Can be pushed anytime (side detail view)

        When to push:
        - After hotel_search: push HotelList with search_key
        - After rooms_and_rates: push RoomList with search_key and hotel_id
        - After hotel_details: push HotelDetails with search_key and hotel_id
        - After selecting room: push RoomSelected with rate_key

    PARAMETERS:
        context_object: Dict containing focus information
            Required keys:
            - type: str (e.g., "HotelList", "RoomList", "HotelDetails")
            - At least one identifier (search_key is mandatory for most)
        runtime: Injected tool runtime for accessing agent state

    Returns:
        Command with state update on success, or error string on failure

    Examples:
        Push hotel list focus:
        >>> push_context(context_object={"type": "HotelList", "search_key": "Miami"})

        Push room list focus:
        >>> push_context(context_object={
        ...     "type": "RoomList",
        ...     "search_key": "Miami",
        ...     "hotel_id": "H1024"
        ... })
    """
    logger.info("=" * 80)
    logger.info(f"[PUSH_CONTEXT] Tool called with:")
    logger.info(f"  context_object: {context_object}")
    logger.info("=" * 80)

    # Validate required type field
    if "type" not in context_object:
        error_result = {
            "error": "invalid_context",
            "message": "context_object must contain 'type' field"
        }
        return json.dumps(error_result, indent=2)

    # Validate that at least one identifier exists
    identifiers = {k for k in context_object.keys() if k != "type"}
    if not identifiers:
        error_result = {
            "error": "invalid_context",
            "message": "context_object must contain at least one identifier (e.g., search_key)"
        }
        return json.dumps(error_result, indent=2)

    # Get context_stack from runtime state (or empty list if runtime is None)
    context_stack = runtime.state.get("context_stack", []) if runtime else []

    # Idempotency check: prevent pushing duplicate context
    if context_stack and _context_matches(context_stack[-1], context_object):
        error_result = {
            "error": "duplicate_context",
            "message": f"Context {context_object.get('type')} is already at the top of the stack"
        }
        return json.dumps(error_result, indent=2)

    # Stack order validation
    current_type = context_object.get("type")
    top_type = context_stack[-1].get("type") if context_stack else None

    # Rule: Cannot push HotelList if RoomList is on top (must pop first)
    if current_type == "HotelList" and top_type == "RoomList":
        error_result = {
            "error": "invalid_stack_order",
            "message": "Cannot push HotelList when RoomList is active. Use pop_context() first to go back to hotel search.",
            "hint": "Call pop_context() to remove the current RoomList, then push the new HotelList"
        }
        return json.dumps(error_result, indent=2)

    # Rule: Cannot push RoomList if another RoomList is on top (must pop first)
    if current_type == "RoomList" and top_type == "RoomList":
        error_result = {
            "error": "invalid_stack_order",
            "message": "Cannot push RoomList when another RoomList is active. Use pop_context() first.",
            "hint": "Call pop_context() to remove the current RoomList, then push the new RoomList"
        }
        return json.dumps(error_result, indent=2)

    # HotelDetails can be pushed anywhere (no restrictions)

    # Success - return Command to push context onto stack
    # The context_stack_reducer will append this to the existing stack
    success_result = {
        "status": "success",
        "message": f"Pushed {current_type} onto context stack"
    }

    if runtime is None:
        return json.dumps(success_result, indent=2)

    return Command(
        update={
            "messages": [ToolMessage(
                content=json.dumps(success_result, indent=2),
                tool_call_id=runtime.tool_call_id
            )],
            "context_stack": [context_object],  # Will be appended by context_stack_reducer
        }
    )


@tool(description="Remove N objects from the top of the context_stack")
def pop_context(
    levels: int = 1,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Remove N objects from the top of the context_stack.

    Used when the user backs out of a detail view or after completing
    a transaction (e.g., booking).

    Args:
        levels: Number of levels to pop from stack (default=1)
        runtime: Injected tool runtime for accessing agent state

    Returns:
        Command with state update containing the popped object(s), or error string

    Examples:
        Pop one level (go back):
        >>> pop_context(levels=1)
        {"type": "RoomSelected", "search_key": "Miami", "hotel_id": "H1024"}

        Pop two levels (complete booking):
        >>> pop_context(levels=2)
        [
            {"type": "RoomSelected", "search_key": "Miami", "hotel_id": "H1024"},
            {"type": "HotelList", "search_key": "Miami"}
        ]
    """
    logger.info("=" * 80)
    logger.info(f"[POP_CONTEXT] Tool called with:")
    logger.info(f"  levels: {levels}")
    logger.info("=" * 80)

    # Validate levels parameter
    if levels < 1:
        error_result = {
            "error": "invalid_parameter",
            "message": "levels must be at least 1"
        }
        return json.dumps(error_result, indent=2)

    # Get context_stack from runtime state (or empty list if runtime is None)
    context_stack = runtime.state.get("context_stack", []) if runtime else []

    # Check if we can pop requested levels
    if len(context_stack) < levels:
        error_result = {
            "error": "insufficient_context",
            "message": f"Cannot pop {levels} levels from stack with {len(context_stack)} items"
        }
        return json.dumps(error_result, indent=2)

    # Pop the requested number of levels
    popped = context_stack[-levels:]  # Get items to be removed
    new_stack = context_stack[:-levels]  # New stack without those items

    # Build success result
    success_result = {
        "status": "success",
        "popped": popped[0] if levels == 1 else popped,
        "message": f"Popped {levels} level(s) from context stack"
    }

    if runtime is None:
        return json.dumps(success_result, indent=2)

    # Return Command with stack replacement
    # Use {"__replace__": new_stack} to signal replacement (not append) via custom reducer
    return Command(
        update={
            "messages": [ToolMessage(
                content=json.dumps(success_result, indent=2),
                tool_call_id=runtime.tool_call_id
            )],
            "context_stack": {"__replace__": new_stack},  # Signal replacement, not append
        }
    )

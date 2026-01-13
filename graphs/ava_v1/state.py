"""
State schema for ava_v1 agent state management.

This module defines the state schema for the ava_v1 agent:
- Custom reducers for parallel tool call support
"""

from typing import Annotated, NotRequired

from langgraph.graph import MessagesState


# Custom reducers (from ava_core pattern)
def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """
    Merge two dicts, with right taking precedence for conflicts.

    This reducer enables multiple tools to update the same dict field
    in parallel without conflicts.

    Args:
        left: Existing dict value
        right: New dict value to merge

    Returns:
        Merged dict with right values taking precedence
    """
    if left is None and right is None:
        return {}
    if left is None:
        return right if right is not None else {}
    if right is None:
        return left
    return {**left, **right}


def context_stack_reducer(left: list, right: list | dict) -> list:
    """
    Custom reducer for context_stack that handles both append and replace.

    This special reducer enables:
    - Append operation: when right is a list, append items to stack
    - Replace operation: when right is dict with "__replace__" key, replace entire stack

    The replace operation is needed for pop_context tool which removes items.

    Args:
        left: Existing context stack
        right: Either list to append or dict with "__replace__" key

    Returns:
        Updated context stack
    """
    if isinstance(right, dict) and "__replace__" in right:
        # Replace entire stack (for pop_context)
        return right["__replace__"]
    # Append to stack (for push_context)
    return left + right


class AvaV1State(MessagesState):
    """
    State schema for ava_v1 agent.

    Preserves ADK patterns (active_searches, context_stack) while using
    LangChain Command pattern for updates.

    State Fields:
        active_searches: Label-based search tracking (e.g., "Miami", "Miami:JW Marriott")
            Format: {"Miami": {"searchId": "abc", "status": "cached", ...}}

        context_stack: Conversational focus tracking stack
            Format: [{"type": "HotelList", "search_key": "Miami"}, ...]
            Types: HotelList, RoomList, HotelDetails, RoomSelected, BookingPending

        user_phone: User's phone number in E.164 format (e.g., +12125551234)
            Set via /state endpoint for booking operations

        call_reference: Unique call reference ID for tracking
            Set via /state endpoint for call session tracking
    """

    # ADK-style label-based search tracking
    # Format: {"Miami": {...}, "Miami:JW Marriott": {...}}  # noqa: ERA001
    active_searches: NotRequired[Annotated[dict[str, dict], merge_dicts]]

    # ADK-style conversational context tracking
    # Stack of focus objects: [{"type": "HotelList", "search_key": "Miami"}, ...]
    # Uses custom reducer to handle both push (append) and pop (replace)
    context_stack: NotRequired[Annotated[list[dict], context_stack_reducer]]

    # Call context metadata (set via /state endpoint)
    user_phone: NotRequired[str]  # User's phone number in E.164 format
    call_reference: NotRequired[str]  # Unique call reference ID

    # Verified customer details collected during conversation
    # Format: {"first_name": "John", "last_name": "Doe", "email": "john@example.com"}
    customer_details: NotRequired[Annotated[dict[str, str], merge_dicts]]

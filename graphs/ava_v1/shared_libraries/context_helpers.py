"""Context stack management helpers for automatic context tracking."""

from typing import Any


def context_matches(ctx1: dict[str, Any], ctx2: dict[str, Any]) -> bool:
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


def prepare_hotel_list_push(
    search_key: str, context_stack: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Prepare to push HotelList context, handling pops if needed.

    Args:
        search_key: Search key for the hotel list
        context_stack: Current context stack

    Returns:
        Tuple of (context_to_push or None if idempotent, new_stack)
    """
    new_context = {"type": "HotelList", "search_key": search_key}

    # Check if already at top (idempotent)
    if context_stack and context_matches(context_stack[-1], new_context):
        return None, context_stack

    # Pop RoomList, HotelList, or HotelDetails from top
    new_stack = context_stack.copy()
    while new_stack and new_stack[-1].get("type") in [
        "RoomList",
        "HotelList",
        "HotelDetails",
    ]:
        new_stack.pop()

    return new_context, new_stack


def prepare_room_list_push(
    search_key: str,
    hotel_id: str,
    room_search_id: str,
    context_stack: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Prepare to push RoomList context, handling pops if needed.

    Args:
        search_key: Search key from hotel search
        hotel_id: Hotel ID for the room search
        room_search_id: Room search ID (hash)
        context_stack: Current context stack

    Returns:
        Tuple of (context_to_push or None if idempotent, new_stack)
    """
    new_context = {
        "type": "RoomList",
        "search_key": search_key,
        "hotel_id": hotel_id,
        "roomSearchId": room_search_id,
    }

    # Check if already at top (idempotent)
    if context_stack and context_matches(context_stack[-1], new_context):
        return None, context_stack

    # Pop other RoomLists or HotelDetails from top (until we reach HotelList or empty)
    new_stack = context_stack.copy()
    while new_stack and new_stack[-1].get("type") in ["RoomList", "HotelDetails"]:
        new_stack.pop()

    return new_context, new_stack


def prepare_hotel_details_push(
    hotel_id: str, context_stack: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Prepare to push HotelDetails context.

    Args:
        hotel_id: Hotel ID for the details
        context_stack: Current context stack

    Returns:
        Tuple of (context_to_push or None if idempotent, new_stack)
    """
    new_context = {"type": "HotelDetails", "hotel_id": hotel_id}

    # Check if already at top (idempotent)
    if context_stack and context_matches(context_stack[-1], new_context):
        return None, context_stack

    # HotelDetails can be pushed on top of anything
    return new_context, context_stack


def prepare_booking_pending_push(
    booking_hash: str,
    session_id: str,
    payment_type: str,
    hold_expires_at: str,
    amount: float,
    s3_key: str,
    context_stack: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Prepare to push BookingPending context, replacing old booking if exists.

    Args:
        booking_hash: Booking hash
        session_id: Session ID
        payment_type: Payment type
        hold_expires_at: Hold expiration time
        amount: Booking amount
        s3_key: S3 key for booking data
        context_stack: Current context stack

    Returns:
        Tuple of (context_to_push, new_stack)
    """
    new_context = {
        "type": "BookingPending",
        "booking_hash": booking_hash,
        "session_id": session_id,
        "payment_type": payment_type,
        "hold_expires_at": hold_expires_at,
        "amount": amount,
        "s3_key": s3_key,
    }

    # Pop old BookingPending if at top (replace it)
    new_stack = context_stack.copy()
    if new_stack and new_stack[-1].get("type") == "BookingPending":
        new_stack.pop()

    return new_context, new_stack

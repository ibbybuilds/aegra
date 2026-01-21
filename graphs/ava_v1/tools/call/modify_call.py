"""Call modification tool for signaling call end or payment transfer."""

import json
import logging
from typing import Annotated, Literal

from langchain.tools import InjectedToolArg, ToolRuntime, tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _extract_handoff_context(runtime: ToolRuntime | None) -> str:
    """Extract human-readable context from agent state for live handoff.

    Builds a succinct summary of the latest conversation context including:
    - Current activity (searching, viewing rooms, booking)
    - Property name (human-readable, not IDs)
    - Destination and dates
    - Occupancy details
    - Booking/payment status if applicable

    Args:
        runtime: Tool runtime with access to context and state

    Returns:
        Human-readable context string (e.g., "Customer viewing rooms at JW Marriott Miami
        for Feb 1-4 (2 adults, 1 room)")
    """
    if not runtime:
        return "No context available"

    parts = []

    # Get context_stack (latest focus) and active_searches
    context_stack = runtime.state.get("context_stack", [])
    active_searches = runtime.state.get("active_searches", {})

    # Get CallContext for fallback data
    call_context = runtime.context if hasattr(runtime, "context") else None

    # Get top of context stack (current focus)
    current_context = context_stack[-1] if context_stack else None

    if current_context:
        ctx_type = current_context.get("type")
        search_key = current_context.get("search_key", "")

        # Extract property name from composite search_key (e.g., "Miami:JW Marriott")
        property_name = None
        destination = search_key
        if ":" in search_key:
            destination, property_name = search_key.split(":", 1)

        # Get search parameters for dates/occupancy
        search_params = active_searches.get(search_key, {})
        check_in = search_params.get("checkIn", "")
        check_out = search_params.get("checkOut", "")
        occupancy = search_params.get("occupancy", {})
        adults = occupancy.get("numOfAdults", 0) if occupancy else 0
        rooms = occupancy.get("numOfRooms", 0) if occupancy else 0

        # Build context based on focus type
        if ctx_type == "BookingPending":
            # Customer has a pending booking
            amount = current_context.get("amount", 0)
            parts.append("Customer booking")
            if property_name:
                parts.append(f"at {property_name}")
            if destination:
                parts.append(f"in {destination}")
            if amount:
                parts.append(f"(${amount:.2f}, payment pending)")

        elif ctx_type == "RoomList":
            # Customer viewing rooms at a specific property
            parts.append("Customer viewing rooms")
            if property_name:
                parts.append(f"at {property_name}")
            if destination:
                parts.append(f"in {destination}")
            if check_in and check_out:
                # Format dates concisely (e.g., "Feb 1-4")
                parts.append(f"for {check_in} to {check_out}")
            if adults or rooms:
                occ_parts = []
                if adults:
                    occ_parts.append(f"{adults} adult{'s' if adults != 1 else ''}")
                if rooms:
                    occ_parts.append(f"{rooms} room{'s' if rooms != 1 else ''}")
                parts.append(f"({', '.join(occ_parts)})")

        elif ctx_type == "HotelList":
            # Customer searching/browsing hotels
            parts.append("Customer searching")
            if destination:
                parts.append(destination)
            if check_in and check_out:
                parts.append(f"for {check_in} to {check_out}")
            if adults or rooms:
                occ_parts = []
                if adults:
                    occ_parts.append(f"{adults} adult{'s' if adults != 1 else ''}")
                if rooms:
                    occ_parts.append(f"{rooms} room{'s' if rooms != 1 else ''}")
                parts.append(f"({', '.join(occ_parts)})")

        elif ctx_type == "HotelDetails":
            # Customer viewing details for a specific property
            hotel_id = current_context.get("hotel_id", "")
            parts.append("Customer viewing hotel details")
            if property_name:
                parts.append(f"for {property_name}")
            elif hotel_id:
                parts.append(f"(Hotel ID: {hotel_id})")

    # Fallback to CallContext if no context_stack
    elif call_context:
        # Check if there's booking context
        if hasattr(call_context, "booking") and call_context.booking:
            booking = call_context.booking
            parts.append("Customer inquired about")
            if booking.destination:
                parts.append(booking.destination)
            if booking.check_in and booking.check_out:
                parts.append(f"({booking.check_in} to {booking.check_out})")

        # Check if there's property context
        elif hasattr(call_context, "property") and call_context.property:
            prop = call_context.property
            parts.append("Customer called about")
            if prop.property_name:
                parts.append(prop.property_name)
            if prop.location:
                parts.append(f"in {prop.location}")

    if not parts:
        parts.append("Customer requested live agent")

    return " ".join(parts)


class ModifyCallInput(BaseModel):
    """Input schema for modifying call state."""

    action_type: Literal["end-call", "pay-transfer", "live-handoff"] = Field(
        description="Action type: 'end-call' to end conversation, 'pay-transfer' to transfer to payment line, or 'live-handoff' to transfer to live agent"
    )
    summary: str | None = Field(
        default=None,
        description="Optional for live-handoff. Additional context/reason for transfer (auto-extracted context is included)",
    )


@tool(
    args_schema=ModifyCallInput,
    description="Signal to end the call, transfer to payment line, or transfer to live agent",
)
async def modify_call(
    action_type: str,
    summary: str | None = None,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> str:
    """Signal to end the call, transfer to payment line, or transfer to live agent.

    This is a tool that triggers call modification events. For pay-transfer,
    automatically retrieves booking details from the most recent BookingPending
    context in the context_stack. For live-handoff, automatically extracts
    conversation context and optionally includes agent-provided summary.

    Args:
        action_type: Action type - "end-call", "pay-transfer", or "live-handoff"
        summary: Optional for live-handoff. Additional context/reason for transfer (auto-extracted context is included)
        runtime: Injected tool runtime for accessing agent state

    Returns:
        JSON string with status:

        Success (end-call):
        {
            "status": "success",
            "type": "end-call",
            "message": str
        }

        Success (pay-transfer):
        {
            "status": "success",
            "type": "pay-transfer",
            "message": str,
            "booking_hash": str,
            "s3_key": str,
            "amount": float,
            "currency": str
        }

        Success (live-handoff):
        {
            "status": "success",
            "type": "live-handoff",
            "message": "Transferring to live agent",
            "summary": str,
            "url": str (optional)
        }

        Error:
        {
            "status": "error",
            "error": {
                "type": str,
                "message": str,
                "hint": str (optional)
            }
        }

    Examples:
        End call:
        >>> modify_call(action_type="end-call")

        Transfer to payment (retrieves details from context_stack):
        >>> modify_call(action_type="pay-transfer")

        Transfer to live agent (auto-extracts context):
        >>> modify_call(action_type="live-handoff")
        >>> modify_call(action_type="live-handoff", summary="wants group booking for 10+ rooms")
    """
    logger.info("=" * 80)
    logger.info("[MODIFY_CALL] Tool called with:")
    logger.info(f"  action_type: {action_type}")
    logger.info(f"  summary: {summary}")
    logger.info("=" * 80)

    # Validate action_type parameter
    valid_types = ["end-call", "pay-transfer", "live-handoff"]
    if action_type not in valid_types:
        result = {
            "status": "error",
            "error": {
                "type": "invalid_type",
                "message": f"action_type must be one of: {', '.join(valid_types)}",
                "hint": "Use 'end-call' to end the conversation, 'pay-transfer' to transfer to payment line, or 'live-handoff' to transfer to a live agent",
            },
        }
        logger.info(f"[modify_call] Returning invalid_type error: {result}")
        return json.dumps(result, indent=2)

    # Handle live-handoff (auto-extracts context, optionally includes agent summary)
    if action_type == "live-handoff":
        logger.info("[modify_call] Handling live-handoff")

        # Extract conversation context automatically
        auto_context = _extract_handoff_context(runtime)
        logger.info(f"[modify_call] Auto-extracted context: {auto_context}")

        # Combine with agent's summary if provided
        if summary and summary.strip():
            full_summary = f"{auto_context} - {summary.strip()}"
        else:
            full_summary = auto_context

        logger.info(f"[modify_call] Full handoff summary: {full_summary}")

        # Generate reservation URL
        reservation_url = None
        if runtime:
            from ava_v1.shared_libraries.url_generator import generate_reservation_url

            context_stack = runtime.state.get("context_stack", [])
            active_searches = runtime.state.get("active_searches", {})
            call_context = runtime.context if hasattr(runtime, "context") else None

            try:
                reservation_url = await generate_reservation_url(
                    context_stack, active_searches, call_context
                )
                if reservation_url:
                    logger.info(
                        f"[modify_call] Generated reservation URL: {reservation_url}"
                    )
            except Exception as e:
                logger.warning(f"[modify_call] Failed to generate URL: {e}")
                # Continue - URL is optional, don't fail handoff

        # Success - return handoff signal with full summary
        result = {
            "status": "success",
            "type": "live-handoff",
            "message": "Transferring to live agent",
            "summary": full_summary,
        }

        # Add URL if generated successfully
        if reservation_url:
            result["url"] = reservation_url

        logger.info(f"[modify_call] Returning live-handoff success: {result}")
        return json.dumps(result, indent=2)

    # Handle end-call (no additional params required)
    if action_type == "end-call":
        result = {
            "status": "success",
            "type": "end-call",
            "message": "Call end signal sent. The call will be terminated.",
        }
        logger.info(f"[modify_call] Returning end-call success: {result}")
        return json.dumps(result, indent=2)

    # Handle pay-transfer (requires booking details from context_stack)
    if action_type == "pay-transfer":
        logger.info("[modify_call] Handling pay-transfer")

        # Get context_stack from runtime state (or empty list if runtime is None)
        context_stack = runtime.state.get("context_stack", []) if runtime else []
        logger.info(f"[modify_call] Context stack length: {len(context_stack)}")

        # Find the most recent BookingPending context
        booking_context = None
        for ctx in reversed(context_stack):
            if ctx.get("type") == "BookingPending":
                booking_context = ctx
                break

        if not booking_context:
            result = {
                "status": "error",
                "error": {
                    "type": "no_booking_found",
                    "message": "No pending booking found in context",
                    "hint": (
                        "You must call book_room first to initiate a booking before "
                        "transferring to payment. The booking details will be automatically "
                        "retrieved from the context stack."
                    ),
                },
            }
            logger.info(f"[modify_call] No booking found error: {result}")
            return json.dumps(result, indent=2)

        # Extract required fields from BookingPending context
        booking_hash = booking_context.get("booking_hash")
        s3_key = booking_context.get("s3_key")
        amount = booking_context.get("amount")
        logger.info(
            f"[modify_call] Extracted: booking_hash={booking_hash}, s3_key={s3_key}, amount={amount}"
        )

        # Validate all required fields are present
        if not all([booking_hash, s3_key, amount]):
            missing = []
            if not booking_hash:
                missing.append("booking_hash")
            if not s3_key:
                missing.append("s3_key")
            if not amount:
                missing.append("amount")

            result = {
                "status": "error",
                "error": {
                    "type": "incomplete_booking_context",
                    "message": f"BookingPending context is missing: {', '.join(missing)}",
                    "hint": "This is likely a bug. BookingPending should contain all required fields.",
                },
            }
            logger.info(f"[modify_call] Incomplete booking error: {result}")
            return json.dumps(result, indent=2)

        # Hard-code currency to USD for now
        currency = "USD"

        # Success - return confirmation
        result = {
            "status": "success",
            "type": "pay-transfer",
            "message": f"Payment transfer signal sent. Transferring to payment line for ${amount:.2f} {currency}.",
            "booking_hash": booking_hash,
            "s3_key": s3_key,
            "amount": amount,
            "currency": currency,
        }
        logger.info(f"[modify_call] Returning pay-transfer success: {result}")
        return json.dumps(result, indent=2)

    # Fallback (should never reach here)
    logger.warning("[modify_call] WARNING: Reached fallback case")
    result = {
        "status": "error",
        "error": {
            "type": "unexpected_error",
            "message": "Unexpected error in modify_call",
        },
    }
    logger.info(f"[modify_call] Returning fallback error: {result}")
    return json.dumps(result, indent=2)

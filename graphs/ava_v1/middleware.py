"Middleware configuration for ava_v1 agent."

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    dynamic_prompt,
)
from langchain_core.messages import SystemMessage, ToolMessage

from ava_v1.context import CallContext
from ava_v1.prompts.template import get_customized_prompt

# Error types that trigger a forced silent retry
# These are errors where the agent can self-correct parameters
FIXABLE_ERRORS = {
    "invalid_input",
    "validation_error",
    "missing_parameter",
    "format_error",
    "api_timeout",
    "rate_limit",
    "server_error",
    "invalid_hotel_id",
    "invalid_payment_type",
    "name_lookup_failed",
    "token_mismatch",
}


def extract_call_context(request: ModelRequest) -> CallContext | None:
    """Extract or auto-derive CallContext from ModelRequest.

    This function implements smart context derivation:
    1. Check for explicit call_context (payment_return, abandoned_payment, session)
    2. Auto-derive from active_searches (property_booking_hybrid, property_specific, booking)
    3. Check message history for thread_continuation
    4. Default to general

    Args:
        request: ModelRequest-like object with runtime and/or state attributes

    Returns:
        CallContext instance with auto-derived type and metadata
    """
    import logging

    from ava_v1.context import DialMapBookingContext, PropertyInfo

    logger = logging.getLogger(__name__)

    # Step 1: Check for explicit call_context (for external metadata)
    call_context: CallContext | dict[str, Any] | None = None

    # Check runtime.context first
    if (
        hasattr(request, "runtime")
        and request.runtime is not None
        and hasattr(request.runtime, "context")
        and request.runtime.context is not None
    ):
        call_context = request.runtime.context
        logger.info(
            "[CONTEXT_AUTO_DERIVE] Found explicit call_context via runtime.context"
        )

    # Check state.call_context as fallback
    if (
        call_context is None
        and hasattr(request, "state")
        and isinstance(request.state, dict)
    ):
        raw_context = request.state.get("call_context")
        if raw_context is not None:
            call_context = raw_context
            logger.info(
                "[CONTEXT_AUTO_DERIVE] Found explicit call_context via state.call_context"
            )

    # Convert dict to CallContext if needed
    if isinstance(call_context, dict):
        valid_keys = {
            "type",
            "property",
            "payment",
            "session",
            "booking",
            "abandoned_payment",
            "user_phone",
            "thread_id",
            "call_reference",
            "dial_map_session_id",
        }
        filtered_context = {k: v for k, v in call_context.items() if k in valid_keys}
        call_context = CallContext(**filtered_context)

    # If explicit context exists and is external type, use it as-is
    if call_context and call_context.type in [
        "payment_return",
        "abandoned_payment",
        "session",
    ]:
        logger.info(
            f"[CONTEXT_AUTO_DERIVE] Using explicit external context type: {call_context.type}"
        )
        return call_context

    # Step 2: Auto-derive from state
    if hasattr(request, "state") and isinstance(request.state, dict):
        state = request.state
        active_searches = state.get("active_searches", {})
        context_stack = state.get("context_stack", [])
        messages = state.get("messages", [])

        # Extract metadata from state or existing call_context
        user_phone = state.get("user_phone") or (
            call_context.user_phone if call_context else None
        )
        call_reference = state.get("call_reference") or (
            call_context.call_reference if call_context else None
        )
        thread_id = call_context.thread_id if call_context else None
        dial_map_session_id = call_context.dial_map_session_id if call_context else None

        # Check active_searches for property/booking info
        hotel_id = None
        hotel_name = None
        booking_info = None

        for search_key, search_data in active_searches.items():
            if isinstance(search_data, dict):
                # Check for hotel_id (property-specific search)
                if "hotelId" in search_data or "hotel_id" in search_data:
                    hotel_id = search_data.get("hotelId") or search_data.get("hotel_id")
                    hotel_name = (
                        search_data.get("hotelName")
                        or search_data.get("hotel_name")
                        or search_key
                    )

                # Check for booking parameters (dates, occupancy)
                # Support both camelCase (from API) and snake_case (from tools)
                if (
                    "dates" in search_data
                    or "occupancy" in search_data
                    or "checkIn" in search_data
                ):
                    dates = search_data.get("dates", {})
                    occupancy = search_data.get("occupancy", {})

                    # Extract dates - check both camelCase and snake_case
                    check_in = (
                        search_data.get("checkIn")
                        or dates.get("check_in")
                        or dates.get("checkIn")
                        or ""
                    )
                    check_out = (
                        search_data.get("checkOut")
                        or dates.get("check_out")
                        or dates.get("checkOut")
                        or ""
                    )

                    # Extract occupancy - check both camelCase and snake_case
                    rooms = occupancy.get("rooms") or occupancy.get("numOfRooms") or 1
                    adults = (
                        occupancy.get("adults") or occupancy.get("numOfAdults") or 2
                    )
                    children = (
                        occupancy.get("children") or occupancy.get("numOfChildren") or 0
                    )

                    booking_info = DialMapBookingContext(
                        destination=search_data.get("destination", search_key),
                        check_in=check_in,
                        check_out=check_out,
                        rooms=rooms,
                        adults=adults,
                        children=children,
                        hotel_id=hotel_id,
                    )
                    logger.info(
                        f"[CONTEXT_AUTO_DERIVE] Extracted booking info: check_in={check_in}, check_out={check_out}, rooms={rooms}, adults={adults}"
                    )

        # Fallback: Check context_stack for property info
        if not hotel_id and context_stack:
            top_context = context_stack[-1]
            if (
                isinstance(top_context, dict)
                and top_context.get("type") == "HotelDetails"
            ):
                hotel_id = top_context.get("hotel_id")
                hotel_name = top_context.get("hotel_name")

        # Derive context type based on what we found
        derived_type = "general"
        property_info = None

        if hotel_id and booking_info:
            derived_type = "property_booking_hybrid"
            property_info = PropertyInfo(
                property_name=hotel_name or "", hotel_id=hotel_id
            )
            logger.info(
                f"[CONTEXT_AUTO_DERIVE] Auto-derived type: property_booking_hybrid (hotel_id={hotel_id}, dates present)"
            )
        elif hotel_id:
            derived_type = "property_specific"
            property_info = PropertyInfo(
                property_name=hotel_name or "", hotel_id=hotel_id
            )
            logger.info(
                f"[CONTEXT_AUTO_DERIVE] Auto-derived type: property_specific (hotel_id={hotel_id})"
            )
        elif booking_info:
            derived_type = "booking"
            logger.info(
                "[CONTEXT_AUTO_DERIVE] Auto-derived type: booking (dates present, no specific property)"
            )
        elif len(messages) > 2:  # Has conversation history
            derived_type = "thread_continuation"
            logger.info(
                "[CONTEXT_AUTO_DERIVE] Auto-derived type: thread_continuation (message history exists)"
            )
        else:
            logger.info("[CONTEXT_AUTO_DERIVE] Auto-derived type: general (default)")

        # Build derived CallContext
        return CallContext(
            type=derived_type,
            property=property_info,
            booking=booking_info,
            user_phone=user_phone,
            thread_id=thread_id,
            call_reference=call_reference,
            dial_map_session_id=dial_map_session_id,
        )

    # Step 3: No state available, return general or existing context
    if call_context:
        logger.info(
            f"[CONTEXT_AUTO_DERIVE] Using existing context type: {call_context.type}"
        )
        return call_context

    logger.info(
        "[CONTEXT_AUTO_DERIVE] No context or state available, defaulting to general"
    )
    return CallContext(type="general")


@dynamic_prompt
def customize_agent_prompt(request: ModelRequest) -> str:
    """Dynamically customize system prompt based on runtime context.

    This middleware accesses call_context from runtime.context (preferred) or state (fallback)
    and uses it to customize the agent's system prompt according to the 8-level priority system.

    According to LangChain docs:
    - @dynamic_prompt REPLACES the entire system prompt
    - Access context via request.runtime.context (preferred) or request.state (fallback)
    - Must return the FULL prompt string (base + customization or standalone)

    Args:
        request: ModelRequest containing state, runtime, and system_prompt

    Returns:
        Customized system prompt string
    """
    # Extract context using helper function (enables testing)
    call_context = extract_call_context(request)

    # Get customized prompt using priority system and template rendering
    return get_customized_prompt(call_context)


class ForcedRetryMiddleware(AgentMiddleware):
    """Middleware to force silent retries on fixable tool errors.

    Inspects the last message before the model runs. If it's a ToolMessage
    with a fixable error (e.g., validation error, missing param), it injects
    a system instruction to force the agent to retry SILENTLY (no text generation).
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Intercept model call to check for retryable errors."""
        # Get the last message in the history
        messages = request.messages
        if not messages:
            return await handler(request)

        last_msg = messages[-1]

        # Check if it's a ToolMessage with an error
        if isinstance(last_msg, ToolMessage) and last_msg.content:
            try:
                # Parse tool content (usually JSON string)
                content_str = str(last_msg.content)
                # Handle potential non-JSON content gracefully
                if content_str.strip().startswith("{"):
                    data = json.loads(content_str)

                    # Check for error status
                    if isinstance(data, dict) and data.get("status") == "error":
                        error_info = data.get("error", {})
                        error_type = (
                            error_info.get("type")
                            if isinstance(error_info, dict)
                            else None
                        )

                        # Check if this is a "fixable" error
                        if error_type in FIXABLE_ERRORS:
                            error_msg = error_info.get("message", "Unknown error")

                            # Construct the strict silent-retry instruction
                            retry_instruction = (
                                f"\n\nSYSTEM INSTRUCTION: The previous tool call failed with error type '{error_type}': {error_msg}. "
                                "You must immediately RETRY the tool call with corrected parameters. "
                                "DO NOT output any text, apology, or explanation. "
                                "Output ONLY the corrected Tool Call."
                            )

                            # Append to system message (ephemeral override)
                            current_system = request.system_message
                            if current_system:
                                new_content = current_system.content + retry_instruction
                                request = request.override(
                                    system_message=SystemMessage(content=new_content),
                                    # Force tool use to discourage chatter
                                    tool_choice="any",
                                )
            except Exception:
                # If parsing fails or any other error, pass through normally
                pass

        return await handler(request)


__all__ = ["customize_agent_prompt", "ForcedRetryMiddleware"]

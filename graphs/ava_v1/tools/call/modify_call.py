"""Call modification tool for signaling call end or payment transfer."""

import json
import logging
from typing import Annotated

from langchain.tools import InjectedToolArg, ToolRuntime, tool

logger = logging.getLogger(__name__)


@tool(description="Signal to end the call, transfer to payment line, or transfer to live agent")
def modify_call(
    action_type: str,
    summary: str | None = None,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> str:
    """Signal to end the call, transfer to payment line, or transfer to live agent.

    This is a tool that triggers call modification events. For pay-transfer,
    automatically retrieves booking details from the most recent BookingPending
    context in the context_stack. For live-handoff, requires a summary explaining
    why the transfer is needed.

    Args:
        action_type: Action type - "end-call", "pay-transfer", or "live-handoff"
        summary: Required for live-handoff. 1-2 sentences explaining why transferring to live agent
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
            "summary": str
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

        Transfer to live agent:
        >>> modify_call(action_type="live-handoff", summary="Customer needs group booking for 10+ rooms")
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

    # Handle live-handoff (requires summary parameter)
    if action_type == "live-handoff":
        logger.info("[modify_call] Handling live-handoff")

        # Validate summary is provided and non-empty
        if not summary or not summary.strip():
            result = {
                "status": "error",
                "error": {
                    "type": "missing_summary",
                    "message": "summary parameter is required for live-handoff",
                    "hint": (
                        "Provide a brief 1-2 sentence explanation of why you're transferring "
                        "to a live agent. Example: modify_call(action_type='live-handoff', "
                        "summary='Customer needs to book 10 rooms for corporate event')"
                    ),
                },
            }
            logger.info(f"[modify_call] Missing summary error: {result}")
            return json.dumps(result, indent=2)

        # Success - return handoff signal with summary
        result = {
            "status": "success",
            "type": "live-handoff",
            "message": "Transferring to live agent",
            "summary": summary.strip(),
        }
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

"""Book room tool for initiating hotel room bookings with price verification."""

import contextlib
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

import httpx
from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from ava_v1.shared_libraries.context_helpers import prepare_booking_pending_push
from ava_v1.shared_libraries.hashing import _generate_booking_hash
from ava_v1.shared_libraries.input_sanitizer import sanitize_tool_input

# Import redis_client and shared libraries
from ava_v1.shared_libraries.redis_client import (
    get_redis_client,
    redis_get_json,
    redis_set_json,
)
from ava_v1.shared_libraries.validation import (
    _validate_customer_info,
    _validate_room_object,
)

logger = logging.getLogger(__name__)


class RoomDict(BaseModel):
    """Room object structure for booking."""

    hotel_id: str = Field(description="Hotel ID from query_vfs results")
    rate_key: str = Field(description="Rate key from room object in query_vfs")
    token: str = Field(description="Token from TOP LEVEL of query_vfs response")
    refundable: bool = Field(description="Whether the rate is refundable")
    expected_price: float = Field(
        description="Expected price for price verification", gt=0
    )


class BookRoomInput(BaseModel):
    """Input schema for booking a hotel room."""

    room: RoomDict = Field(
        description="Complete room object built from query_vfs response"
    )
    payment_type: Literal["phone", "sms"] = Field(
        description="Payment method: 'phone' for phone payment or 'sms' for SMS link"
    )
    session_id: str | None = Field(
        default=None, description="Optional session ID for tracking"
    )
    price_confirmation_token: str | None = Field(
        default=None,
        description="Token from previous call if price changed and user confirmed",
    )


@tool(
    args_schema=BookRoomInput,
    description="""Initiate hotel room booking with price verification and payment setup.

PREREQUISITES (must complete in order):
1. Call start_room_search(hotel_id, search_key) to initiate room search
2. Engage user while search runs
3. Call query_vfs(destination, sort_by) to get complete room data with token and rate_key
4. User selects a room
5. Verify customer details via update_customer_details (first_name, last_name, email) - call sequentially for each field

CRITICAL - Room Object Structure:
Must be built from query_vfs response (NOT from firstRoom preview):
{
  "hotel_id": vfs_response["results"][0]["hotel_id"],
  "rate_key": vfs_response["results"][0]["rate_key"],     // FROM room object
  "token": vfs_response["token"],                          // FROM TOP LEVEL
  "refundable": vfs_response["results"][0]["refundable_rate"] != null,
  "expected_price": vfs_response["results"][0]["refundable_rate"] or non_refundable_rate
}

WARNING: FirstRoom preview from start_room_search is INCOMPLETE - it lacks token and complete rate_key. NEVER use firstRoom for booking - you MUST call query_vfs first.

Behavior:
- Creates 10-minute prebook hold with price verification
- If price changed: Returns price_confirmation_token (call again with token after user confirms)
- If success: Returns payment_pending status (then call modify_call with action_type="pay-transfer")
- Validates all customer details are verified before proceeding

Payment Types:
- "phone": Transfer to phone payment line
- "sms": Send SMS payment link""",
)
async def book_room(
    room: RoomDict,
    payment_type: str,
    session_id: str | None = None,
    price_confirmation_token: str | None = None,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Initiate hotel room booking with price verification and payment setup.

    Creates a 10-minute prebook hold and prepares payment. Requires complete room data from query_vfs
    and verified customer details from update_customer_details.

    Args:
        room: RoomDict Pydantic model with validated booking data (converted to dict internally)
        payment_type: Payment method - "phone" or "sms"
        session_id: Optional session ID for tracking
        price_confirmation_token: Token from previous call if price changed and user confirmed
        runtime: Injected tool runtime for accessing agent state

    Returns:
        Command with state updates or JSON string with booking status
    """
    # Convert Pydantic model to dict for downstream processing
    room_dict = room.model_dump()

    logger.info(
        "[BOOK_ROOM] Initiating booking",
        extra={
            "payment_type": payment_type,
            "has_session_id": bool(session_id),
            "has_price_token": bool(price_confirmation_token),
            "hotel_id": room_dict["hotel_id"],
        },
    )

    logger.debug(
        "[BOOK_ROOM] Booking details",
        extra={
            "room": room_dict,
            "session_id": session_id,
            "price_confirmation_token": price_confirmation_token,
        },
    )

    # Extract verified customer details from state
    customer_details = {}
    if runtime:
        customer_details = runtime.state.get("customer_details", {})
        # Redact email PII partially in logs
        log_details = customer_details.copy()
        if "email" in log_details:
            parts = log_details["email"].split("@")
            if len(parts) == 2:
                log_details["email"] = f"{parts[0][:2]}***@{parts[1]}"
        logger.info(f"[BOOK_ROOM] Retrieved customer_details from state: {log_details}")
    else:
        logger.warning(
            "[BOOK_ROOM] Runtime not available, cannot retrieve customer details"
        )

    first_name = customer_details.get("first_name")
    last_name = customer_details.get("last_name")
    email = customer_details.get("email")

    if not all([first_name, last_name, email]):
        missing = []
        if not first_name:
            missing.append("first_name")
        if not last_name:
            missing.append("last_name")
        if not email:
            missing.append("email")

        error_msg = f"Missing verified customer details: {', '.join(missing)}. Please verify these details sequentially using update_customer_details tool."
        return json.dumps(
            {
                "status": "error",
                "error": {"type": "missing_customer_details", "message": error_msg},
            }
        )

    # Construct verified customer info
    customer_info = {"firstName": first_name, "lastName": last_name, "email": email}

    # Fallback: use user_phone from call_context or state if customer phone not provided
    # Note: customer_info currently constructed above doesn't have phone yet
    if runtime:
        user_phone = None

        # OPTION 1: Access via runtime.context (for /runs endpoint with context parameter)
        if hasattr(runtime, "context") and runtime.context is not None:
            call_context = runtime.context
            logger.info(
                f"[BOOK_ROOM] Extracted context from runtime.context: {call_context}"
            )

            # Extract user_phone from context (object or dict)
            if hasattr(call_context, "user_phone"):
                user_phone = call_context.user_phone
                logger.info(
                    f"[BOOK_ROOM] Extracted user_phone from context object: {user_phone}"
                )
            elif isinstance(call_context, dict):
                user_phone = call_context.get("user_phone")
                logger.info(
                    f"[BOOK_ROOM] Extracted user_phone from context dict: {user_phone}"
                )

        # OPTION 2: Access via runtime.state (for /state endpoint updates)
        if (
            user_phone is None
            and hasattr(runtime, "state")
            and isinstance(runtime.state, dict)
        ):
            # Try nested call_context first
            call_context = runtime.state.get("call_context")
            if call_context:
                logger.info(
                    f"[BOOK_ROOM] Found call_context in runtime.state: {call_context}"
                )
                if hasattr(call_context, "user_phone"):
                    user_phone = call_context.user_phone
                    logger.info(
                        f"[BOOK_ROOM] Extracted user_phone from state.call_context object: {user_phone}"
                    )
                elif isinstance(call_context, dict):
                    user_phone = call_context.get("user_phone")
                    logger.info(
                        f"[BOOK_ROOM] Extracted user_phone from state.call_context dict: {user_phone}"
                    )

            # Try direct state.user_phone if still not found
            if user_phone is None:
                user_phone = runtime.state.get("user_phone")
                if user_phone:
                    logger.info(
                        f"[BOOK_ROOM] Extracted user_phone directly from runtime.state: {user_phone}"
                    )

        if user_phone:
            # Preserve E.164 format (e.g., +1234567890)
            customer_info["phone"] = user_phone
            logger.info(
                f"[BOOK_ROOM] Using user_phone (E.164 format preserved): {user_phone}"
            )
        else:
            logger.warning(
                "[BOOK_ROOM] user_phone not found in runtime.context or runtime.state"
            )
            # If no phone found, validation below will catch it if required by payment type

    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())

    # Validate payment_type
    if payment_type not in ["phone", "sms"]:
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_payment_type",
                "message": "payment_type must be 'phone' or 'sms'",
            },
        }
        return json.dumps(error_result, indent=2)

    # Validate room object
    room_error = _validate_room_object(room_dict)
    if room_error:
        return json.dumps(room_error, indent=2)

    # Validate customer info
    customer_error = _validate_customer_info(customer_info)
    if customer_error:
        return json.dumps(customer_error, indent=2)

    # Generate booking hash
    booking_hash = _generate_booking_hash(room_dict)

    # Initialize idempotency_key (used later for caching results)
    idempotency_key = f"booking_attempt:{booking_hash}:{session_id}"

    # Check idempotency - prevent duplicate bookings
    try:
        get_redis_client()

        # Check if this exact booking attempt already exists
        existing_attempt = await redis_get_json(idempotency_key)
        if existing_attempt:
            # Return cached result to prevent duplicate booking
            return json.dumps(existing_attempt, indent=2)

    except Exception as e:
        # Log but don't fail - idempotency check is not critical
        logger.warning(f"Idempotency check error: {e}")

    # Determine if this is a price confirmation retry
    skip_price_check = False
    if price_confirmation_token:
        # Validate token
        try:
            token_key = f"price_token:{price_confirmation_token}"
            token_data = await redis_get_json(token_key)

            if not token_data:
                error_result = {
                    "status": "error",
                    "error": {
                        "type": "invalid_token",
                        "message": "Price confirmation token is invalid or expired",
                    },
                }
                return json.dumps(error_result, indent=2)

            # Verify token matches this booking
            if token_data.get("hash") != booking_hash:
                error_result = {
                    "status": "error",
                    "error": {
                        "type": "token_mismatch",
                        "message": "Price confirmation token does not match this booking",
                    },
                }
                return json.dumps(error_result, indent=2)

            # Valid token - skip price check
            skip_price_check = True

        except Exception as e:
            error_result = {
                "status": "error",
                "error": {
                    "type": "token_validation_error",
                    "message": f"Failed to validate price confirmation token: {str(e)}",
                },
            }
            return json.dumps(error_result, indent=2)

    # Build request to cache-worker
    cache_worker_url = os.getenv("CACHE_WORKER_URL", "http://localhost:8080")
    endpoint = f"{cache_worker_url}/v1/book"

    request_body = {
        "room": room_dict,
        "customer_info": customer_info,
        "hash": booking_hash,
        "session_id": session_id,
        "skip_price_check": skip_price_check,
    }

    # Call cache-worker
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(endpoint, json=request_body, timeout=30.0)

            # 409 Conflict means price mismatch - this is expected, not an error
            # Don't raise exception, parse the response body with price info
            if response.status_code == 409:
                booking_response = response.json()
            else:
                # For all other status codes, raise on error
                response.raise_for_status()
                booking_response = response.json()

    except httpx.HTTPStatusError as e:
        error_result = {
            "status": "error",
            "error": {
                "type": "booking_service_error",
                "message": f"Cache-worker HTTP error {e.response.status_code}: {str(e)}",
            },
            "retryable": e.response.status_code >= 500,
        }
        return json.dumps(error_result, indent=2)

    except httpx.TimeoutException:
        error_result = {
            "status": "error",
            "error": {
                "type": "timeout",
                "message": "Request to cache-worker timed out",
            },
            "retryable": True,
        }
        return json.dumps(error_result, indent=2)

    except Exception as e:
        error_result = {
            "status": "error",
            "error": {
                "type": "unexpected_error",
                "message": f"Unexpected error calling cache-worker: {str(e)}",
            },
            "retryable": False,
        }
        return json.dumps(error_result, indent=2)

    # Handle cache-worker response

    # Case 1: Price mismatch (only possible when skip_price_check=False)
    if booking_response.get("priceMatch") is False:
        original_price = booking_response.get("originalPrice")
        new_price = booking_response.get("newPrice")

        # Check if room is no longer available (price = 0)
        if new_price == 0 or new_price is None:
            result = {
                "status": "error",
                "error": {
                    "type": "room_unavailable",
                    "message": "This room is no longer available. Apologize to the customer and ask if they would like to see other rooms at this hotel or explore different hotels.",
                },
                "booking_hash": booking_hash,
            }
            return json.dumps(result, indent=2)

        # Calculate price increase percentage
        price_increase_percent = 0
        if original_price and original_price > 0:
            price_increase_percent = (
                (new_price - original_price) / original_price
            ) * 100

        # Generate price confirmation token
        token = str(uuid.uuid4())
        token_key = f"price_token:{token}"

        # Store token data with 10-min TTL (matches prebook hold)
        token_data = {
            "hash": booking_hash,
            "original_price": original_price,
            "new_price": new_price,
            "created_at": datetime.now(UTC).isoformat(),
        }

        with contextlib.suppress(Exception):
            await redis_set_json(token_key, token_data, ttl_seconds=600)

        # Calculate hold expiry
        hold_expires_at = datetime.now(UTC) + timedelta(minutes=10)
        time_remaining_seconds = 600

        result = {
            "status": "price_changed",
            "booking_hash": booking_hash,
            "price_confirmation_token": token,
            "original_price": original_price,
            "new_price": new_price,
            "price_increase_percent": round(price_increase_percent, 2),
            "suggest_alternatives": price_increase_percent > 20,
            "hold_expires_at": hold_expires_at.isoformat(),
            "time_remaining_seconds": time_remaining_seconds,
            "hint": f'Price changed from ${original_price:.2f} to ${new_price:.2f}. Inform user of new price and ask for confirmation. If user confirms, call book_room() again with price_confirmation_token="{token}". If user declines, suggest alternative rooms or hotels.',
        }

        # Cache this result for idempotency
        with contextlib.suppress(Exception):
            await redis_set_json(idempotency_key, result, ttl_seconds=600)

        return json.dumps(result, indent=2)

    # Case 2: Success - booking initiated, S3 upload complete
    if "key" in booking_response and "hash" in booking_response:
        s3_key = booking_response["key"]

        # Generate payment link if SMS
        payment_link = None
        if payment_type == "sms":
            # Payment link will be generated by websocket server
            # For now, return a placeholder that indicates SMS payment
            payment_link = f"<SMS_PAYMENT_LINK:{s3_key}>"

        # Calculate hold expiry
        hold_expires_at = datetime.now(UTC) + timedelta(minutes=10)
        time_remaining_seconds = 600

        # Get amount from poll response or estimate
        amount = booking_response.get("amount", 0.0)
        currency = booking_response.get("currency", "USD")

        result = {
            "status": "payment_pending",
            "booking_hash": booking_hash,
            "s3_key": s3_key,
            "payment_type": payment_type,
            "payment_link": payment_link,
            "amount": amount,
            "currency": currency,
            "hold_expires_at": hold_expires_at.isoformat(),
            "time_remaining_seconds": time_remaining_seconds,
            "hint": 'Booking successful! Room is on hold for 10 minutes. Inform user booking is confirmed and explain payment process. When ready to transfer to payment, call modify_call(action_type="pay-transfer").',
        }

        # Cache this result for idempotency
        with contextlib.suppress(Exception):
            await redis_set_json(idempotency_key, result, ttl_seconds=600)

        if runtime is None:
            return json.dumps(result, indent=2)

        # Auto-manage context stack: push BookingPending (replace old booking if exists)
        context_stack = runtime.state.get("context_stack", [])
        context_to_push, new_stack = prepare_booking_pending_push(
            booking_hash,
            session_id,
            payment_type,
            hold_expires_at.isoformat(),
            amount,
            s3_key,
            context_stack,
        )

        # Context is always pushed for new bookings
        update_dict = {
            "messages": [
                ToolMessage(
                    content=json.dumps(result, indent=2),
                    tool_call_id=runtime.tool_call_id,
                )
            ],
            # __replace__ is a special LangGraph pattern for state replacement
            "context_stack": {"__replace__": new_stack + [context_to_push]},  # type: ignore[dict-item]
        }

        logger.info(
            f"[BOOK_ROOM] Pushing BookingPending({booking_hash}) to context stack"
        )

        # Return Command with state updates
        return Command(update=update_dict)

    # Case 3: Unexpected response from cache-worker
    error_result = {
        "status": "error",
        "error": {
            "type": "unexpected_response",
            "message": f"Unexpected response from cache-worker: {booking_response}",
        },
        "retryable": True,
    }
    return json.dumps(error_result, indent=2)

"""Book room tool for initiating hotel room bookings with price verification."""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict

import httpx
from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

# Import redis_client and shared libraries
from ava_v1.shared_libraries.redis_client import get_redis_client, redis_get_json, redis_set_json

from ava_v1.shared_libraries.validation import (
    _validate_email,
    _validate_room_object,
    _validate_customer_info
)
from ava_v1.shared_libraries.hashing import _generate_booking_hash
from ava_v1.shared_libraries.input_sanitizer import sanitize_tool_input
from ava_v1.shared_libraries.context_helpers import prepare_booking_pending_push

logger = logging.getLogger(__name__)


@tool(description="Initiate hotel room booking with price verification and payment setup")
async def book_room(
    room: Dict[str, Any],
    customer_info: Dict[str, Any],
    payment_type: str,
    session_id: str = None,
    price_confirmation_token: str = None,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Initiate hotel room booking with price verification and payment setup.

    PURPOSE:
        Complete the booking process by creating a 10-minute prebook hold and
        preparing payment. CRITICAL: You MUST call query_vfs first to obtain
        complete room data with token and rate_key. The firstRoom preview from
        start_room_search is incomplete and CANNOT be used.

    PREREQUISITE:
        Before calling this tool, you MUST:
        1. Call start_room_search() to initiate room search
        2. Engage user and wait for response
        3. Call query_vfs() to get complete room data with token
        4. Extract token from TOP LEVEL and rate_key from room object

    PARAMETERS:
        room (dict): Room object built from query_vfs response
            CRITICAL STRUCTURE:
            {
                "hotel_id": vfs_response["results"][0]["hotel_id"],
                "rate_key": vfs_response["results"][0]["rate_key"],
                "token": vfs_response["token"],  # FROM TOP LEVEL
                "refundable": True or False,
                "expected_price": vfs_response["results"][0]["refundable_rate"]
            }

        customer_info (dict): Customer information
            {
                "firstName": str,
                "lastName": str,
                "email": str,
                "phone": str  # Required only if payment_type is "sms"
            }

        payment_type (str): Payment method - "phone" or "sms"
        session_id (str, optional): Session ID for tracking
        price_confirmation_token (str, optional): Token from previous call if price changed
        runtime: Injected tool runtime for accessing agent state

    RETURNS:
        Command with state updates containing booking metadata
    """
    logger.info("=" * 80)
    logger.info(f"[BOOK_ROOM] Tool called with:")
    logger.info(f"  room: {room}")
    logger.info(f"  customer_info: {customer_info}")
    logger.info(f"  payment_type: {payment_type}")
    logger.info(f"  session_id: {session_id}")
    logger.info(f"  price_confirmation_token: {price_confirmation_token}")
    logger.info("=" * 80)

    # Sanitize input to handle malformed JSON keys
    room = sanitize_tool_input(room)
    customer_info = sanitize_tool_input(customer_info)
    logger.info(f"[BOOK_ROOM] Sanitized room: {room}")
    logger.info(f"[BOOK_ROOM] Sanitized customer_info: {customer_info}")

    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())

    # Validate payment_type
    if payment_type not in ["phone", "sms"]:
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_payment_type",
                "message": "payment_type must be 'phone' or 'sms'"
            }
        }
        return json.dumps(error_result, indent=2)

    # Validate room object
    room_error = _validate_room_object(room)
    if room_error:
        return json.dumps(room_error, indent=2)

    # Validate customer info
    customer_error = _validate_customer_info(customer_info, payment_type)
    if customer_error:
        return json.dumps(customer_error, indent=2)

    # Generate booking hash
    booking_hash = _generate_booking_hash(room)

    # Check idempotency - prevent duplicate bookings
    try:
        redis_client = get_redis_client()
        idempotency_key = f"booking_attempt:{booking_hash}:{session_id}"

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
                        "message": "Price confirmation token is invalid or expired"
                    }
                }
                return json.dumps(error_result, indent=2)

            # Verify token matches this booking
            if token_data.get("hash") != booking_hash:
                error_result = {
                    "status": "error",
                    "error": {
                        "type": "token_mismatch",
                        "message": "Price confirmation token does not match this booking"
                    }
                }
                return json.dumps(error_result, indent=2)

            # Valid token - skip price check
            skip_price_check = True

        except Exception as e:
            error_result = {
                "status": "error",
                "error": {
                    "type": "token_validation_error",
                    "message": f"Failed to validate price confirmation token: {str(e)}"
                }
            }
            return json.dumps(error_result, indent=2)

    # Build request to polling service
    poll_service_url = os.getenv("POLLING_SERVICE_URL", "http://localhost:8080")
    endpoint = f"{poll_service_url}/v1/book"

    request_body = {
        "room": room,
        "customer_info": customer_info,
        "hash": booking_hash,
        "session_id": session_id,
        "skip_price_check": skip_price_check
    }

    # Call polling service
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                json=request_body,
                timeout=30.0
            )

            # 409 Conflict means price mismatch - this is expected, not an error
            # Don't raise exception, parse the response body with price info
            if response.status_code == 409:
                poll_response = response.json()
            else:
                # For all other status codes, raise on error
                response.raise_for_status()
                poll_response = response.json()

    except httpx.HTTPStatusError as e:
        error_result = {
            "status": "error",
            "error": {
                "type": "poll_service_error",
                "message": f"Polling service HTTP error {e.response.status_code}: {str(e)}"
            },
            "retryable": e.response.status_code >= 500
        }
        return json.dumps(error_result, indent=2)

    except httpx.TimeoutException:
        error_result = {
            "status": "error",
            "error": {
                "type": "timeout",
                "message": "Request to polling service timed out"
            },
            "retryable": True
        }
        return json.dumps(error_result, indent=2)

    except Exception as e:
        error_result = {
            "status": "error",
            "error": {
                "type": "unexpected_error",
                "message": f"Unexpected error calling polling service: {str(e)}"
            },
            "retryable": False
        }
        return json.dumps(error_result, indent=2)

    # Handle polling service response

    # Case 1: Price mismatch (only possible when skip_price_check=False)
    if poll_response.get("priceMatch") is False:
        original_price = poll_response.get("originalPrice")
        new_price = poll_response.get("newPrice")

        # Check if room is no longer available (price = 0)
        if new_price == 0 or new_price is None:
            result = {
                "status": "error",
                "error": {
                    "type": "room_unavailable",
                    "message": "This room is no longer available. Apologize to the customer and ask if they would like to see other rooms at this hotel or explore different hotels."
                },
                "booking_hash": booking_hash
            }
            return json.dumps(result, indent=2)

        # Calculate price increase percentage
        price_increase_percent = 0
        if original_price and original_price > 0:
            price_increase_percent = ((new_price - original_price) / original_price) * 100

        # Generate price confirmation token
        token = str(uuid.uuid4())
        token_key = f"price_token:{token}"

        # Store token data with 10-min TTL (matches prebook hold)
        token_data = {
            "hash": booking_hash,
            "original_price": original_price,
            "new_price": new_price,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            await redis_set_json(token_key, token_data, ttl_seconds=600)
        except Exception:
            pass

        # Calculate hold expiry
        hold_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
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
            "hint": f"Price changed from ${original_price:.2f} to ${new_price:.2f}. Inform user of new price and ask for confirmation. If user confirms, call book_room() again with price_confirmation_token=\"{token}\". If user declines, suggest alternative rooms or hotels."
        }

        # Cache this result for idempotency
        try:
            await redis_set_json(idempotency_key, result, ttl_seconds=600)
        except Exception:
            pass

        return json.dumps(result, indent=2)

    # Case 2: Success - booking initiated, S3 upload complete
    if "key" in poll_response and "hash" in poll_response:
        s3_key = poll_response["key"]

        # Generate payment link if SMS
        payment_link = None
        if payment_type == "sms":
            # Payment link will be generated by websocket server
            # For now, return a placeholder that indicates SMS payment
            payment_link = f"<SMS_PAYMENT_LINK:{s3_key}>"

        # Calculate hold expiry
        hold_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        time_remaining_seconds = 600

        # Get amount from poll response or estimate
        amount = poll_response.get("amount", 0.0)
        currency = poll_response.get("currency", "USD")

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
            "hint": f"Booking successful! Room is on hold for 10 minutes. Inform user booking is confirmed and explain payment process. When ready to transfer to payment, call modify_call(action_type=\"pay-transfer\")."
        }

        # Cache this result for idempotency
        try:
            await redis_set_json(idempotency_key, result, ttl_seconds=600)
        except Exception:
            pass

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
            context_stack
        )

        # Context is always pushed for new bookings
        update_dict = {
            "messages": [ToolMessage(
                content=json.dumps(result, indent=2),
                tool_call_id=runtime.tool_call_id
            )],
            "context_stack": {"__replace__": new_stack + [context_to_push]}
        }

        logger.info(f"[BOOK_ROOM] Pushing BookingPending({booking_hash}) to context stack")

        # Return Command with state updates
        return Command(update=update_dict)

    # Case 3: Unexpected response from polling service
    error_result = {
        "status": "error",
        "error": {
            "type": "unexpected_response",
            "message": f"Unexpected response from polling service: {poll_response}"
        },
        "retryable": True
    }
    return json.dumps(error_result, indent=2)

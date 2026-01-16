"""Validation utilities for the ava travel assistant."""

import re
from typing import Any


def _validate_email(email: str) -> bool:
    """Validate email format using regex.

    Args:
        email: Email address to validate

    Returns:
        True if valid format, False otherwise
    """
    # Standard email regex pattern
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def _validate_room_object(room: dict[str, Any]) -> dict[str, Any] | None:
    """Validate room object has all required fields.

    Returns:
        Error dict if invalid, None if valid
    """
    required_fields = ["hotel_id", "rate_key", "token", "refundable", "expected_price"]

    for field in required_fields:
        if field not in room:
            return {
                "status": "error",
                "error": {
                    "type": "invalid_room_object",
                    "message": f"room object missing required field: {field}",
                },
            }

    # Validate types
    if (
        not isinstance(room["hotel_id"], (str, int))
        or not str(room["hotel_id"]).strip()
    ):
        return {
            "status": "error",
            "error": {
                "type": "invalid_room_object",
                "message": "hotel_id must be a non-empty string or integer",
            },
        }

    if not isinstance(room["rate_key"], str) or not room["rate_key"].strip():
        return {
            "status": "error",
            "error": {
                "type": "invalid_room_object",
                "message": "rate_key must be a non-empty string",
            },
        }

    if not isinstance(room["token"], str) or not room["token"].strip():
        return {
            "status": "error",
            "error": {
                "type": "invalid_room_object",
                "message": "token must be a non-empty string",
            },
        }

    if not isinstance(room["refundable"], bool):
        return {
            "status": "error",
            "error": {
                "type": "invalid_room_object",
                "message": "refundable must be a boolean",
            },
        }

    if (
        not isinstance(room["expected_price"], (int, float))
        or room["expected_price"] <= 0
    ):
        return {
            "status": "error",
            "error": {
                "type": "invalid_room_object",
                "message": "expected_price must be a positive number",
            },
        }

    return None


def _validate_customer_info(
    customer_info: dict[str, Any],
) -> dict[str, Any] | None:
    """Validate customer info has all required fields.

    Args:
        customer_info: Customer information dict (must include phone)

    Returns:
        Error dict if invalid, None if valid
    """
    required_fields = ["firstName", "lastName", "email"]

    for field in required_fields:
        if field not in customer_info:
            return {
                "status": "error",
                "error": {
                    "type": "invalid_customer_info",
                    "message": f"customer_info missing required field: {field}",
                },
            }

        if (
            not isinstance(customer_info[field], str)
            or not customer_info[field].strip()
        ):
            return {
                "status": "error",
                "error": {
                    "type": "invalid_customer_info",
                    "message": f"{field} must be a non-empty string",
                },
            }

    # Validate email format
    if not _validate_email(customer_info["email"]):
        return {
            "status": "error",
            "error": {
                "type": "invalid_email",
                "message": f"Invalid email format: {customer_info['email']}",
            },
        }

    # Phone required for billing contact
    if "phone" not in customer_info or not customer_info["phone"]:
        return {
            "status": "error",
            "error": {
                "type": "missing_phone",
                "message": "phone is required for billing contact",
            },
        }

    if (
        not isinstance(customer_info["phone"], str)
        or not customer_info["phone"].strip()
    ):
        return {
            "status": "error",
            "error": {
                "type": "invalid_phone",
                "message": "phone must be a non-empty string",
            },
        }

    return None

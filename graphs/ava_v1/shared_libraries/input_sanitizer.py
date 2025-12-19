"""Input sanitization utilities for handling malformed tool inputs."""

from typing import Any, Union


def normalize_search_params(search: dict[str, Any]) -> dict[str, Any]:
    """Normalize search parameters from snake_case to camelCase.

    Handles both snake_case (check_in, check_out, adults) and camelCase
    (checkIn, checkOut, occupancy) parameter formats.

    Args:
        search: Search parameters dictionary

    Returns:
        Normalized search dictionary with camelCase keys
    """
    normalized = {}

    # Map all variations to camelCase
    key_mapping = {
        # Check-in variations
        "check_in": "checkIn",
        "check_in_date": "checkIn",
        "checkin": "checkIn",
        "checkIn": "checkIn",
        # Check-out variations
        "check_out": "checkOut",
        "check_out_date": "checkOut",
        "checkout": "checkOut",
        "checkOut": "checkOut",
        # Destination variations
        "destination": "destination",
        "Destination": "destination",
        # Name variations
        "name": "name",
        "hotel_name": "name",
        "hotelName": "name",
    }

    for key, value in search.items():
        # Use mapping if exists, otherwise use original key
        normalized_key = key_mapping.get(key, key)
        normalized[normalized_key] = value

    # Handle adults -> occupancy conversion
    if "adults" in search and "occupancy" not in normalized:
        adults = search["adults"]
        # Convert to int if it's a float with no decimal part
        if isinstance(adults, float) and adults.is_integer():
            adults = int(adults)
        normalized["occupancy"] = {"numOfAdults": adults}

    return normalized


def normalize_dict_keys(obj: Any) -> Any:
    """Recursively normalize dictionary keys by stripping embedded quotes.

    Handles malformed JSON where keys have extra quotes like '"checkOut"'
    instead of 'checkOut'. This is a workaround for the Gemini Live API
    native audio model occasionally generating improperly quoted JSON keys.

    Args:
        obj: The object to normalize (dict, list, or primitive)

    Returns:
        Normalized object with cleaned keys

    Example:
        Input:  {'"checkOut"': '2026-01-06', '"occupancy"': {'"numOfAdults"': 2}}
        Output: {'checkOut': '2026-01-06', 'occupancy': {'numOfAdults': 2}}
    """
    if isinstance(obj, dict):
        normalized = {}
        for key, value in obj.items():
            # Strip leading/trailing quotes from keys
            clean_key = key.strip("\"'")
            # Recursively normalize nested structures
            normalized[clean_key] = normalize_dict_keys(value)
        return normalized
    elif isinstance(obj, list):
        return [normalize_dict_keys(item) for item in obj]
    else:
        return obj


def sanitize_tool_input(data: Union[dict, list]) -> Union[dict, list]:
    """Sanitize tool input by normalizing malformed keys.

    Primary entry point for cleaning tool inputs before processing.

    Args:
        data: Dictionary or list to sanitize

    Returns:
        Sanitized data structure
    """
    return normalize_dict_keys(data)

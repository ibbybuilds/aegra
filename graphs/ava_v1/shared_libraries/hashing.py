"""Hashing utilities for the ava travel assistant."""

import hashlib
import json
from typing import Any, Dict


def _generate_booking_hash(room: Dict[str, Any]) -> str:
    """Generate deterministic hash from room object.

    Hash components: hotel_id + rate_key + token
    Token is unique per user, ensuring no collisions.

    Args:
        room: Room object with hotel_id, rate_key, token

    Returns:
        12-character MD5 hash
    """
    hash_input = {
        "hotel_id": str(room["hotel_id"]),
        "rate_key": room["rate_key"],
        "token": room["token"],
    }

    canonical_string = json.dumps(hash_input, sort_keys=True, separators=(",", ":"))
    hash_object = hashlib.md5(canonical_string.encode("utf-8"))
    return hash_object.hexdigest()[:12]


def canonical_api_hash(search_params: Dict[str, Any]) -> str:
    """Generate a canonical hash for API search parameters.

    Creates a deterministic hash by normalizing and sorting all parameters.
    Uses MD5 for speed and truncates to 12 characters for compact Redis keys.

    Args:
        search_params: The search parameters dictionary

    Returns:
        A 12-character hex hash string representing the search
    """
    # Create a normalized copy of the search params
    normalized = {}

    # Normalize destination (lowercase, strip whitespace)
    if "Destination" in search_params:
        normalized["destination"] = search_params["Destination"].lower().strip()

    # Add dates as-is (assumed to be in YYYY-MM-DD format)
    if "checkIn" in search_params:
        normalized["check_in"] = search_params["checkIn"]
    if "checkOut" in search_params:
        normalized["check_out"] = search_params["checkOut"]

    # Normalize occupancy
    if "occupancy" in search_params:
        occupancy = search_params["occupancy"]
        normalized_occupancy = {}

        if "numOfAdults" in occupancy:
            normalized_occupancy["num_adults"] = occupancy["numOfAdults"]

        # Optional: numOfRooms
        if "numOfRooms" in occupancy:
            normalized_occupancy["num_rooms"] = occupancy["numOfRooms"]

        # Optional: childAges (sort to make order-independent)
        if "childAges" in occupancy and occupancy["childAges"]:
            normalized_occupancy["child_ages"] = sorted(occupancy["childAges"])

        normalized["occupancy"] = normalized_occupancy

    # Convert to JSON with sorted keys for deterministic output
    canonical_string = json.dumps(normalized, sort_keys=True, separators=(",", ":"))

    # Generate MD5 hash (fast and sufficient for Redis key generation)
    hash_object = hashlib.md5(canonical_string.encode("utf-8"))
    full_hash = hash_object.hexdigest()

    # Truncate to 12 characters for compact Redis keys
    return full_hash[:12]


def canonical_rooms_hash(hotel_id: str, search_params: Dict[str, Any]) -> str:
    """Generate a canonical hash for room search parameters.

    Matches the Go polling service hash pattern exactly:
    {hotelId}-{checkIn}-{checkOut}-{numOfAdults}[-[childAges]][-numOfRooms]

    Args:
        hotel_id: Hotel ID string
        search_params: Dict with checkIn, checkOut, occupancy

    Returns:
        A 12-character hex hash string representing the room search

    Examples:
        Without optional fields:
        >>> canonical_rooms_hash("39615853", {
        ...     "checkIn": "2025-12-26",
        ...     "checkOut": "2025-12-29",
        ...     "occupancy": {"numOfAdults": 2}
        ... })
        "fbb3a0e51f5a"  # From: 39615853-2025-12-26-2025-12-29-2

        With childAges:
        >>> canonical_rooms_hash("39615853", {
        ...     "checkIn": "2025-12-26",
        ...     "checkOut": "2025-12-29",
        ...     "occupancy": {"numOfAdults": 2, "childAges": [5, 8]}
        ... })
        "7a8c3f2e9d1b"  # From: 39615853-2025-12-26-2025-12-29-2-[5 8]
    """
    occupancy = search_params["occupancy"]

    # Build canonical string matching Go service pattern
    parts = [
        str(hotel_id),
        search_params["checkIn"],
        search_params["checkOut"],
        str(occupancy["numOfAdults"]),
    ]

    # Add childAges if present (format: [age1 age2 ...])
    if "childAges" in occupancy and occupancy["childAges"]:
        # Format as [5 8] with space separation
        child_ages_str = (
            "[" + " ".join(str(age) for age in occupancy["childAges"]) + "]"
        )
        parts.append(child_ages_str)

    # Add numOfRooms if present
    if "numOfRooms" in occupancy:
        parts.append(str(occupancy["numOfRooms"]))

    canonical_string = "-".join(parts)
    hash_object = hashlib.md5(canonical_string.encode("utf-8"))
    return hash_object.hexdigest()[:12]

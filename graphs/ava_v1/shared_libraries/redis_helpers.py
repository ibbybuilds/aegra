"""Redis and data filtering utilities for the ava travel assistant."""

from typing import Any, Dict


def _filter_hotel_details(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter hotel details API response to include only relevant fields.

    Args:
        raw_data: Full API response

    Returns:
        Filtered dict with only selected fields
    """
    # Extract basic info
    filtered = {
        "id": raw_data.get("id"),
        "name": raw_data.get("name"),
        "chainName": raw_data.get("chainName"),
        "brandName": raw_data.get("brandName"),
        "starRating": raw_data.get("starRating"),
        "propertyType": raw_data.get("propertyType"),
    }

    # Extract location
    if "geocode" in raw_data:
        filtered["geocode"] = raw_data["geocode"]

    if "contact" in raw_data and "address" in raw_data["contact"]:
        filtered["address"] = raw_data["contact"]["address"]

    # Extract property details
    if "descriptions" in raw_data:
        filtered["descriptions"] = raw_data["descriptions"]

    if "facilities" in raw_data:
        filtered["facilities"] = raw_data["facilities"]

    if "policies" in raw_data:
        filtered["policies"] = raw_data["policies"]

    # Extract reviews
    if "review" in raw_data:
        filtered["review"] = raw_data["review"]

    # Extract timezone
    if "timezone" in raw_data:
        filtered["timezone"] = raw_data["timezone"]

    return filtered

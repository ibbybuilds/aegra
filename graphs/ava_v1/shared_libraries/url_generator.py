"""URL generator for reservation portal links based on conversation context.

This module generates reservation portal URLs from the conversation context stack,
enabling live agents to see what customers are viewing during handoffs.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from ava_v1.context import CallContext

logger = logging.getLogger(__name__)

# Base URL for reservation portal (configurable via environment)
BASE_URL = os.getenv(
    "RESERVATION_PORTAL_BASE_URL", "https://sandbox.reservationsportal.com"
)


def _format_dates_for_url(check_in: str, check_out: str) -> str | None:
    """Convert YYYY-MM-DD dates to MM/DD/YYYY-MM/DD/YYYY format.

    Args:
        check_in: Check-in date in YYYY-MM-DD format (e.g., "2026-01-04")
        check_out: Check-out date in YYYY-MM-DD format (e.g., "2026-01-06")

    Returns:
        Formatted date string (e.g., "01/04/2026-01/06/2026") or None if invalid
    """
    try:
        # Validate format
        date_pattern = r"^\d{4}-\d{2}-\d{2}$"
        if not re.match(date_pattern, check_in) or not re.match(
            date_pattern, check_out
        ):
            return None

        # Parse and reformat
        check_in_dt = datetime.strptime(check_in, "%Y-%m-%d")
        check_out_dt = datetime.strptime(check_out, "%Y-%m-%d")

        check_in_formatted = check_in_dt.strftime("%m/%d/%Y")
        check_out_formatted = check_out_dt.strftime("%m/%d/%Y")

        return f"{check_in_formatted}-{check_out_formatted}"

    except (ValueError, AttributeError) as e:
        logger.warning(f"[url_generator] Date formatting error: {e}")
        return None


def _build_property_url(
    hotel_id: str, dates: tuple[str, str] | None, occupancy: dict | None
) -> str:
    """Build property URL with optional dates and occupancy.

    Args:
        hotel_id: Hotel/property ID
        dates: Optional tuple of (check_in, check_out) in YYYY-MM-DD format
        occupancy: Optional occupancy dict with numOfAdults, rooms, numOfChildren

    Returns:
        Property URL string
    """
    url = f"{BASE_URL}/property/{hotel_id}"

    # Add query parameters if dates and occupancy available
    if dates and occupancy:
        check_in, check_out = dates
        formatted_dates = _format_dates_for_url(check_in, check_out)

        if formatted_dates:
            adults = occupancy.get("numOfAdults", 1)
            rooms = occupancy.get("rooms", 1)

            url += f"?dates={formatted_dates}&numberAdults={adults}&numberRooms={rooms}"

    return url


def _build_location_url(
    geo_data: dict, dates: tuple[str, str], occupancy: dict
) -> str:
    """Build location search URL.

    Args:
        geo_data: Geographic data with latitude, longitude, formattedAddress, countryCode
        dates: Tuple of (check_in, check_out) in YYYY-MM-DD format
        occupancy: Occupancy dict with numOfAdults, rooms, numOfChildren

    Returns:
        Location search URL string
    """
    # Extract coordinates
    latitude = geo_data.get("latitude")
    longitude = geo_data.get("longitude")

    # Parse location from formattedAddress
    # Example: "Miami, FL, USA" -> locality=Miami, region=FL, country=US
    formatted_address = geo_data.get("formattedAddress", "")
    parts = [p.strip() for p in formatted_address.split(",")]

    locality = parts[0] if len(parts) > 0 else ""
    region = parts[1] if len(parts) > 1 else ""
    country = parts[2] if len(parts) > 2 else geo_data.get("countryCode", "US")

    # Format dates
    check_in, check_out = dates
    formatted_dates = _format_dates_for_url(check_in, check_out)

    # Extract occupancy
    adults = occupancy.get("numOfAdults", 1)
    rooms = occupancy.get("rooms", 1)
    children = occupancy.get("numOfChildren", 0)

    # Build URL with URL encoding for string parameters
    url = (
        f"{BASE_URL}/availability?"
        f"scrollOnSubmit=true&"
        f"propertyUrl=&"
        f"latitude={latitude}&"
        f"longitude={longitude}&"
        f"locality={quote(locality)}&"
        f"region={quote(region)}&"
        f"country={quote(country)}&"
        f"dates={formatted_dates}&"
        f"numberRooms={rooms}&"
        f"numberAdults={adults}&"
        f"numberChildren={children}"
    )

    return url


async def _get_geo_from_search_key(
    search_key: str, active_searches: dict
) -> dict | None:
    """Get geographic coordinates for location URL.

    Checks active_searches for geoHash, then lookups Redis geo cache.
    Falls back to calling get_geo_coordinates() if cache miss.

    Args:
        search_key: Search key (e.g., "Miami")
        active_searches: Active searches dict from state

    Returns:
        Geo data dict with latitude, longitude, formattedAddress, countryCode
        Returns None if not found
    """
    try:
        # Get search data
        search_data = active_searches.get(search_key)
        if not search_data:
            return None

        geo_hash = search_data.get("geoHash")
        if not geo_hash:
            return None

        # Check Redis geo cache
        from ava_v1.shared_libraries.redis_client import redis_get_json_compressed

        redis_key = f"geo:{geo_hash}"
        geo_data = await redis_get_json_compressed(redis_key)

        if geo_data:
            return geo_data

        # Cache miss - fallback to API call
        # Extract destination from search_key (handle composite keys like "Miami:JW Marriott")
        destination = search_key.split(":")[0] if ":" in search_key else search_key

        from ava_v1.tools.explore.hotel_search import get_geo_coordinates

        geo_response = await get_geo_coordinates(destination)
        geo_result = json.loads(geo_response)

        # Check if successful response
        if "error" not in geo_result:
            return geo_result

        return None

    except Exception as e:
        logger.warning(f"[url_generator] Geo lookup error: {e}")
        return None


def _find_hotel_context_in_stack(context_stack: list[dict]) -> dict | None:
    """Walk back context stack to find hotel_id from RoomList context.

    Used for BookingPending contexts which don't store hotel_id.

    Args:
        context_stack: Context stack from state

    Returns:
        RoomList context dict with hotel_id, or None if not found
    """
    for ctx in reversed(context_stack):
        if ctx.get("type") == "RoomList" and "hotel_id" in ctx:
            return ctx
    return None


def _extract_url_data(
    context_stack: list[dict],
    active_searches: dict[str, dict],
    call_context: CallContext | None,
) -> dict | None:
    """Extract URL-relevant data from agent state.

    Args:
        context_stack: Context stack from state
        active_searches: Active searches dict from state
        call_context: CallContext for fallback when context_stack is empty

    Returns:
        Dict with keys: url_type, hotel_id, search_key, dates, occupancy, geo_data
        Returns None if insufficient data
    """
    # Try context_stack first (conversation state)
    if context_stack:
        current_context = context_stack[-1]
        ctx_type = current_context.get("type")

        # HotelList - location search URL
        if ctx_type == "HotelList":
            search_key = current_context.get("search_key")
            if not search_key:
                return None

            search_data = active_searches.get(search_key, {})
            check_in = search_data.get("checkIn")
            check_out = search_data.get("checkOut")
            occupancy = search_data.get("occupancy")

            if check_in and check_out and occupancy:
                return {
                    "url_type": "location",
                    "search_key": search_key,
                    "dates": (check_in, check_out),
                    "occupancy": occupancy,
                }

        # RoomList - dated property URL
        elif ctx_type == "RoomList":
            hotel_id = current_context.get("hotel_id")
            search_key = current_context.get("search_key")

            if not hotel_id:
                return None

            search_data = active_searches.get(search_key, {}) if search_key else {}
            check_in = search_data.get("checkIn")
            check_out = search_data.get("checkOut")
            occupancy = search_data.get("occupancy")

            if check_in and check_out and occupancy:
                return {
                    "url_type": "dated_property",
                    "hotel_id": hotel_id,
                    "dates": (check_in, check_out),
                    "occupancy": occupancy,
                }

            # Fallback: property URL without dates
            return {"url_type": "property", "hotel_id": hotel_id}

        # HotelDetails - property URL (no dates)
        elif ctx_type == "HotelDetails":
            hotel_id = current_context.get("hotel_id")
            if hotel_id:
                return {"url_type": "property", "hotel_id": hotel_id}

        # BookingPending - walk back to find RoomList
        elif ctx_type == "BookingPending":
            room_context = _find_hotel_context_in_stack(context_stack)
            if room_context:
                hotel_id = room_context.get("hotel_id")
                search_key = room_context.get("search_key")

                if hotel_id:
                    search_data = (
                        active_searches.get(search_key, {}) if search_key else {}
                    )
                    check_in = search_data.get("checkIn")
                    check_out = search_data.get("checkOut")
                    occupancy = search_data.get("occupancy")

                    if check_in and check_out and occupancy:
                        return {
                            "url_type": "dated_property",
                            "hotel_id": hotel_id,
                            "dates": (check_in, check_out),
                            "occupancy": occupancy,
                        }

                    return {"url_type": "property", "hotel_id": hotel_id}

    # Fallback to CallContext if context_stack is empty
    if call_context:
        # property_specific context - property URL
        if call_context.property and call_context.property.hotel_id:
            return {
                "url_type": "property",
                "hotel_id": call_context.property.hotel_id,
            }

        # booking context - dated property or location URL
        if call_context.booking:
            booking = call_context.booking

            # Dated property URL if hotel_id and dates available
            if booking.hotel_id and booking.check_in and booking.check_out:
                occupancy = {
                    "numOfAdults": booking.adults,
                    "rooms": booking.rooms,
                    "numOfChildren": booking.children,
                }
                return {
                    "url_type": "dated_property",
                    "hotel_id": booking.hotel_id,
                    "dates": (booking.check_in, booking.check_out),
                    "occupancy": occupancy,
                }

            # Location URL if destination and dates available
            if booking.destination and booking.check_in and booking.check_out:
                occupancy = {
                    "numOfAdults": booking.adults,
                    "rooms": booking.rooms,
                    "numOfChildren": booking.children,
                }
                # Need to fetch geo data for this destination
                # Return partial data, geo lookup will happen in main function
                return {
                    "url_type": "location_from_booking",
                    "destination": booking.destination,
                    "dates": (booking.check_in, booking.check_out),
                    "occupancy": occupancy,
                }

    return None


def _validate_url_data(url_data: dict) -> bool:
    """Validate that required fields exist for URL type.

    Args:
        url_data: URL data dict from _extract_url_data

    Returns:
        True if valid, False otherwise
    """
    url_type = url_data.get("url_type")

    if url_type == "dated_property":
        return all(
            [
                url_data.get("hotel_id"),
                url_data.get("dates"),
                url_data.get("occupancy"),
            ]
        )

    if url_type == "property":
        return bool(url_data.get("hotel_id"))

    if url_type == "location":
        return all(
            [
                url_data.get("search_key"),
                url_data.get("dates"),
                url_data.get("occupancy"),
            ]
        )

    if url_type == "location_from_booking":
        return all(
            [
                url_data.get("destination"),
                url_data.get("dates"),
                url_data.get("occupancy"),
            ]
        )

    return False


async def generate_reservation_url(
    context_stack: list[dict],
    active_searches: dict[str, dict],
    call_context: CallContext | None = None,
) -> str | None:
    """Generate reservation portal URL from current agent state.

    Args:
        context_stack: Context stack from state
        active_searches: Active searches dict from state
        call_context: Optional CallContext for fallback

    Returns:
        URL string or None if insufficient data
    """
    try:
        # Extract URL data
        url_data = _extract_url_data(context_stack, active_searches, call_context)

        if not url_data:
            logger.info("[url_generator] No URL data extracted")
            return None

        # Validate data
        if not _validate_url_data(url_data):
            logger.warning(f"[url_generator] Invalid URL data: {url_data}")
            return None

        url_type = url_data["url_type"]

        # Generate property URL (no dates)
        if url_type == "property":
            hotel_id = url_data["hotel_id"]
            url = _build_property_url(hotel_id, None, None)
            logger.info(f"[url_generator] Generated property URL: {url}")
            return url

        # Generate dated property URL
        if url_type == "dated_property":
            hotel_id = url_data["hotel_id"]
            dates = url_data["dates"]
            occupancy = url_data["occupancy"]
            url = _build_property_url(hotel_id, dates, occupancy)
            logger.info(f"[url_generator] Generated dated property URL: {url}")
            return url

        # Generate location URL
        if url_type == "location":
            search_key = url_data["search_key"]
            dates = url_data["dates"]
            occupancy = url_data["occupancy"]

            # Fetch geo data
            geo_data = await _get_geo_from_search_key(search_key, active_searches)
            if not geo_data:
                logger.warning(
                    f"[url_generator] Geo data not found for search_key: {search_key}"
                )
                return None

            # Validate geo data has required fields
            if not all(
                [geo_data.get("latitude"), geo_data.get("longitude"), geo_data.get("formattedAddress")]
            ):
                logger.warning(f"[url_generator] Incomplete geo data: {geo_data}")
                return None

            url = _build_location_url(geo_data, dates, occupancy)
            logger.info(f"[url_generator] Generated location URL: {url}")
            return url

        # Generate location URL from CallContext booking
        if url_type == "location_from_booking":
            destination = url_data["destination"]
            dates = url_data["dates"]
            occupancy = url_data["occupancy"]

            # Fetch geo data for destination
            from ava_v1.tools.explore.hotel_search import get_geo_coordinates

            geo_response = await get_geo_coordinates(destination)
            geo_result = json.loads(geo_response)

            # Check if successful response
            if "error" in geo_result:
                logger.warning(
                    f"[url_generator] Geo lookup failed for destination: {destination}"
                )
                return None

            # Validate geo data
            if not all(
                [
                    geo_result.get("latitude"),
                    geo_result.get("longitude"),
                    geo_result.get("formattedAddress"),
                ]
            ):
                logger.warning(
                    f"[url_generator] Incomplete geo data for destination: {destination}"
                )
                return None

            url = _build_location_url(geo_result, dates, occupancy)
            logger.info(
                f"[url_generator] Generated location URL from booking context: {url}"
            )
            return url

        return None

    except Exception as e:
        logger.error(f"[url_generator] Error generating URL: {e}", exc_info=True)
        return None

"""Hotel search tool for finding and managing hotel searches."""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from typing import Annotated, Any

import httpx
import jwt
import redis.asyncio as redis_async
from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field, model_validator

from ava_v1.shared_libraries.context_helpers import prepare_hotel_list_push
from ava_v1.shared_libraries.hashing import canonical_api_hash
from ava_v1.shared_libraries.lookup_id import lookup_id

# Import redis_client and shared libraries
from ava_v1.shared_libraries.redis_client import (
    get_redis_pool,
    redis_get_json_compressed,
    redis_set_json_compressed,
)

logger = logging.getLogger(__name__)


class HotelSearchParams(BaseModel):
    """Parameters for a single hotel search."""

    destination: str = Field(
        description="Destination city or location (e.g., 'Orlando', 'Miami, Florida')"
    )
    checkIn: str = Field(
        description="Check-in date in YYYY-MM-DD format (e.g., '2026-01-04')",
        alias="check_in",
    )
    checkOut: str = Field(
        description="Check-out date in YYYY-MM-DD format (e.g., '2026-01-06')",
        alias="check_out",
    )
    occupancy: dict[str, int | list[int]] | None = Field(
        default=None,
        description="Occupancy details with numOfAdults and optional childAges (e.g., {'numOfAdults': 2, 'numOfRooms': 1, 'childAges': [5, 3]})",
    )
    name: str | None = Field(
        default=None,
        description="Optional hotel name for direct lookup (e.g., 'JW Marriott')",
    )

    @model_validator(mode="before")
    @classmethod
    def convert_adults_to_occupancy(cls, data: Any) -> Any:
        """Convert 'adults' field to 'occupancy' structure if needed."""
        # If 'adults' is provided but 'occupancy' is not, convert it
        if isinstance(data, dict) and "adults" in data and "occupancy" not in data:
            adults = data["adults"]
            # Convert to int if it's a float with no decimal part
            if isinstance(adults, float) and adults.is_integer():
                adults = int(adults)
            data["occupancy"] = {"numOfAdults": adults}
        return data

    class Config:
        populate_by_name = True  # Allow both 'checkIn' and 'check_in'


def geo_destination_hash(destination: str) -> str:
    """Generate a canonical hash for a destination string.

    Creates a deterministic hash by normalizing the destination.
    Uses MD5 for speed and truncates to 12 characters for compact Redis keys.

    Args:
        destination: The destination string (e.g., "Miami, Florida")

    Returns:
        A 12-character hex hash string representing the normalized destination
    """
    # Normalize: lowercase, strip whitespace, remove extra spaces
    normalized = " ".join(destination.lower().strip().split())

    # Generate MD5 hash
    hash_object = hashlib.md5(normalized.encode("utf-8"))
    full_hash = hash_object.hexdigest()

    # Truncate to 12 characters for compact Redis keys
    return full_hash[:12]


async def get_geo_coordinates(destination: str) -> str:
    """Get geographic coordinates for a destination using cache-worker.

    Cache-worker handles Redis caching and Google Places API calls internally.
    Returns coordinates directly (tiny payload exception).

    Args:
        destination: The destination query string (e.g., "Orlando, Florida")

    Returns:
        JSON string with latitude, longitude, and formatted_address if found.
        Returns error dict if lookup fails:
        {"error": "location_not_found", "message": "..."}
        {"error": "geocode_error", "message": "..."}
    """
    logger.info(f"[DEBUG] get_geo_coordinates() called with destination: {destination}")

    # Validate inputs
    if not destination or not destination.strip():
        result = {
            "error": "invalid_input",
            "message": "Destination query cannot be empty",
        }
        return json.dumps(result, indent=2)

    cache_worker_url = os.getenv("CACHE_WORKER_URL", "http://localhost:8080")
    endpoint = f"{cache_worker_url}/v1/search/geo"

    logger.info(f"[DEBUG] CACHE_WORKER_URL: {cache_worker_url}")
    logger.info(
        f"[GEO_COORDINATES] Calling cache-worker for destination: {destination}"
    )

    try:
        logger.info(f"[DEBUG] Creating httpx.AsyncClient for geocode request")
        async with httpx.AsyncClient() as client:
            logger.info(f"[DEBUG] Sending GET request to {endpoint}")
            response = await client.get(
                endpoint, params={"destination": destination}, timeout=10.0
            )
            logger.info(
                f"[DEBUG] Received response with status: {response.status_code}"
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"[DEBUG] Parsed response JSON successfully")

            logger.info(
                f"[GEO_COORDINATES] Cache {'HIT' if data.get('status') == 'cached' else 'MISS'}"
            )

            # Extract coordinates (format unchanged for downstream code)
            geo_data = {
                "latitude": data["latitude"],
                "longitude": data["longitude"],
                "formatted_address": data["formatted_address"],
            }

            logger.info(f"[DEBUG] get_geo_coordinates() returning successfully")
            return json.dumps(geo_data, indent=2)

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[DEBUG] HTTPStatusError in get_geo_coordinates: {type(e).__name__}: {str(e)}"
        )
        logger.error(
            f"[DEBUG] Response status: {e.response.status_code}, body: {e.response.text[:200]}"
        )
        if e.response.status_code == 404:
            error_response = {
                "error": "location_not_found",
                "message": f"Could not find coordinates for '{destination}'",
            }
        else:
            error_response = {
                "error": "geocode_error",
                "message": f"Geocode API error: {str(e)}",
            }
        return json.dumps(error_response, indent=2)

    except httpx.TimeoutException as e:
        logger.error(f"[DEBUG] TimeoutException in get_geo_coordinates: {str(e)}")
        error_response = {"error": "timeout", "message": "Geocode request timed out"}
        return json.dumps(error_response, indent=2)

    except Exception as e:
        logger.error(
            f"[DEBUG] Unexpected exception in get_geo_coordinates: {type(e).__name__}: {str(e)}"
        )
        logger.error(f"[DEBUG] Exception traceback:", exc_info=True)
        error_response = {
            "error": "unexpected_error",
            "message": f"Unexpected geocode error: {str(e)}",
        }
        return json.dumps(error_response, indent=2)


def _generate_jwt_token() -> str:
    """Generate JWT token for hotel API authentication.

    Returns:
        JWT token string
    """
    # Get JWT configuration from environment
    jwt_secret = os.getenv("HOTEL_JWT_SECRET", "your-jwt-secret-key-here")
    jwt_issuer = os.getenv("HOTEL_JWT_ISSUER", "postman-test")
    jwt_expiry_seconds = int(os.getenv("HOTEL_JWT_EXPIRY_SECONDS", "30"))

    # Generate JWT payload
    current_time_ms = int(time.time() * 1000)
    payload = {
        "iss": jwt_issuer,
        "iat": current_time_ms,
        "exp": current_time_ms + (jwt_expiry_seconds * 1000),
        "jti": f"jwt_{uuid.uuid4().hex[:8]}",
    }

    # Generate and return JWT token
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")
    return token


async def _start_hotel_search(
    search: dict[str, Any], geo_data: dict[str, Any]
) -> dict[str, Any]:
    """Send hotel search request to cache-worker.

    Cache-worker handles hash generation, cache checking, init API calls,
    and polling internally. Returns metadata only.

    Args:
        search: Search parameters (destination, checkIn, checkOut, occupancy)
        geo_data: Geographic coordinates (latitude, longitude)

    Returns:
        Dict with searchId, status, hotelCount (metadata only)
    """
    cache_worker_url = os.getenv("CACHE_WORKER_URL", "http://localhost:8080")
    endpoint = f"{cache_worker_url}/v1/search"

    request_body = {
        "destination": search["destination"],
        "checkIn": search["checkIn"],
        "checkOut": search["checkOut"],
        "occupancy": search["occupancy"],
        "geoCoordinates": {
            "latitude": geo_data["latitude"],
            "longitude": geo_data["longitude"],
        },
    }

    logger.info(f"[DEBUG] _start_hotel_search() called")
    logger.info(f"[HOTEL_SEARCH] Calling cache-worker: {endpoint}")
    logger.info(f"[HOTEL_SEARCH] Request body: {request_body}")

    try:
        logger.info(f"[DEBUG] Creating httpx.AsyncClient for hotel search")
        async with httpx.AsyncClient() as client:
            logger.info(f"[DEBUG] Sending POST request to cache-worker")
            response = await client.post(endpoint, json=request_body, timeout=30.0)
            logger.info(
                f"[DEBUG] Received response with status: {response.status_code}"
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"[DEBUG] Parsed response JSON successfully")

        logger.info(f"[HOTEL_SEARCH] Response status: {data['status']}")
        logger.info(f"[HOTEL_SEARCH] Search ID: {data['searchId']}")

        return data
    except Exception as e:
        logger.error(
            f"[DEBUG] Exception in _start_hotel_search: {type(e).__name__}: {str(e)}"
        )
        logger.error(f"[DEBUG] Exception traceback:", exc_info=True)
        raise


def _normalize_search_dict(search: dict[str, Any]) -> dict[str, Any]:
    """Normalize search dict to consistent key names.

    Ensures all keys are lowercase and handles aliases consistently.
    This prevents KeyError bugs from case mismatches.

    Args:
        search: Search dict from Pydantic model_dump()

    Returns:
        Normalized dict with guaranteed lowercase keys
    """
    return {
        "destination": search.get("destination") or search.get("Destination"),
        "checkIn": search.get("checkIn") or search.get("check_in"),
        "checkOut": search.get("checkOut") or search.get("check_out"),
        "occupancy": search.get("occupancy"),
        "name": search.get("name"),
    }


async def _process_single_search(search: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single hotel search - initiate or return cached.

    Args:
        search: Search parameters dictionary

    Returns:
        Dict with search metadata (searchId, status, etc.)
        None if invalid parameters
    """
    # Normalize keys to prevent case mismatch errors
    search = _normalize_search_dict(search)
    logger.info(f"[DEBUG] _process_single_search() called with search: {search}")

    # Validate required fields
    required_fields = ["destination", "checkIn", "checkOut", "occupancy"]
    if not all(field in search and search[field] for field in required_fields):
        logger.warning(
            f"[HOTEL_SEARCH] Missing required fields in search: {search}. Required: {required_fields}, Got keys: {list(search.keys())}"
        )
        return None

    destination = search["destination"]

    label = destination.split(",")[0].strip()

    # Handle optional name lookup
    resolved_hotel_id = None
    hotel_name_from_lookup = None

    if "name" in search and search["name"]:
        # Call lookup_id to resolve hotel name
        lookup_result = await lookup_id(query=search["name"], city_hint=label)

        # Handle lookup errors
        if "error" in lookup_result:
            return {
                "destination": destination,
                "searchId": None,
                "status": "error",
                "error": {
                    "type": "name_lookup_failed",
                    "message": lookup_result.get(
                        "message", "Failed to lookup hotel by name"
                    ),
                },
            }

        # Check confidence level
        confidence = lookup_result.get("confidence")

        if confidence == "high":
            # Single high-confidence match
            hotels = lookup_result.get("hotels", [])
            if hotels and len(hotels) > 0:
                resolved_hotel_id = hotels[0].get("id")
                hotel_name_from_lookup = hotels[0].get("name")
            else:
                resolved_hotel_id = None
                hotel_name_from_lookup = None

            return {
                "destination": destination,
                "searchId": None,
                "status": "name_resolved",
                "resolvedHotelId": resolved_hotel_id,
                "resolvedHotelName": hotel_name_from_lookup,
                "checkIn": search["checkIn"],
                "checkOut": search["checkOut"],
                "occupancy": search["occupancy"],
                "message": f"Found {hotel_name_from_lookup}. Ready to check room availability.",
                "hint": f'Hotel identified. Skip query_vfs and call start_room_search(hotel_id="{resolved_hotel_id}", search_key="{destination}") directly to check room availability.',
            }

        elif confidence == "low":
            # Multiple matches - return for clarification
            hotels = lookup_result.get("hotels", [])
            return {
                "destination": destination,
                "searchId": None,
                "status": "clarification_needed",
                "hotels": hotels,
                "message": f"Found {len(hotels)} hotels matching '{search['name']}'.",
            }

    # Regular hotel search (no name or name lookup failed)
    # Get geo coordinates
    try:
        # Get geo data
        geo_result_str = await get_geo_coordinates(destination)
        geo_data = json.loads(geo_result_str)

        if "error" in geo_data:
            return {
                "destination": destination,
                "searchId": None,
                "status": "error",
                "error": geo_data,
            }

        # Call cache-worker (replaces: hash generation, cache check, init, polling)
        search_result = await _start_hotel_search(search, geo_data)

        # Build result for ava_v1 state management
        result = {
            "destination": destination,
            "searchId": search_result["searchId"],
            "status": search_result["status"],
            "checkIn": search["checkIn"],
            "checkOut": search["checkOut"],
            "occupancy": search["occupancy"],
        }

        # Add optional fields if present in response
        if "hotelCount" in search_result:
            result["hotelCount"] = search_result["hotelCount"]
        if "expectedHotelCount" in search_result:
            result["expectedHotelCount"] = search_result["expectedHotelCount"]
        if "estimatedSeconds" in search_result:
            result["estimatedSeconds"] = search_result["estimatedSeconds"]
        if "message" in search_result:
            result["message"] = search_result["message"]

        # Generate hint based on status
        if search_result["status"] == "cached":
            count = result.get("hotelCount", 0)
            result["hint"] = (
                f'Found {count} hotels. Call query_vfs(destination="{destination}") to retrieve and present results to the user.'
            )
        elif search_result["status"] == "polling":
            result["hint"] = (
                f'Hotel search initiated. Ask user about preferences (budget, star rating) while search runs. Call query_vfs(destination="{destination}") after {search_result.get("estimatedSeconds", 8)}s.'
            )

        # Add resolved hotel_id if name lookup was performed
        if resolved_hotel_id:
            result["resolvedHotelId"] = resolved_hotel_id
            result["resolvedHotelName"] = hotel_name_from_lookup

        return result

    except Exception as e:
        return {
            "destination": destination,
            "searchId": None,
            "status": "error",
            "error": {"type": "search_failed", "message": str(e)},
        }


@tool(
    description="Start hotel search - initiates search and returns status (does not return hotel results)"
)
async def start_hotel_search(
    searches: list[HotelSearchParams],
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Start hotel search - initiates search but does NOT return hotel results.

    PURPOSE:
        Initiate hotel searches for a destination. This tool does NOT wait for complete
        results - it returns immediately with a status. Use query_vfs() tool after engaging
        the user to retrieve and filter results.

        If user provides a hotel name (e.g., "JW Marriott"), this tool will attempt
        to resolve it directly, allowing you to skip straight to start_room_search().

    PARAMETERS:
        searches: List of search dictionaries, each containing:
            - Destination (required, str): Destination city/location
            - checkIn (required, str): Check-in date in YYYY-MM-DD format
            - checkOut (required, str): Check-out date in YYYY-MM-DD format
            - occupancy (required, dict): Occupancy details
            - name (optional, str): Hotel name for direct lookup

    RETURNS:
        Command with state updates containing search metadata

    Args:
        searches: List of search parameters
        runtime: Injected tool runtime for accessing agent state
    """
    logger.info("=" * 80)
    logger.info(f"[DEBUG] start_hotel_search() ENTRY POINT - Tool called")
    logger.info(f"[HOTEL_SEARCH] Tool called with {len(searches)} search(es)")
    logger.info(f"[HOTEL_SEARCH] Searches: {searches}")
    logger.info("=" * 80)

    try:
        # Convert Pydantic models to dicts
        logger.info(f"[DEBUG] Converting {len(searches)} Pydantic models to dicts")
        search_dicts = [search.model_dump(by_alias=False) for search in searches]
        logger.info(f"[DEBUG] Conversion successful")

        # Process all searches in parallel
        logger.info(
            f"[DEBUG] Starting parallel processing of {len(search_dicts)} searches"
        )
        search_tasks = [_process_single_search(search) for search in search_dicts]
        search_results = await asyncio.gather(*search_tasks)
        logger.info(
            f"[DEBUG] Parallel processing completed, got {len(search_results)} results"
        )
    except Exception as e:
        logger.error(
            f"[DEBUG] Exception in start_hotel_search: {type(e).__name__}: {str(e)}"
        )
        logger.error(f"[DEBUG] Exception traceback:", exc_info=True)
        raise

    # Build response
    searches_metadata = []

    # Get existing active_searches from runtime state
    active_searches = runtime.state.get("active_searches", {}) if runtime else {}

    for search_result in search_results:
        if search_result is None:
            continue

        destination = search_result["destination"]
        base_label = destination.split(",")[0].strip()

        # For name_resolved searches, use composite key: "Miami:JW Marriott"
        # For regular searches, use simple key: "Miami"
        if search_result["status"] == "name_resolved":
            hotel_name = search_result.get("resolvedHotelName")
            # Only create composite key if we have a valid hotel name
            # If name resolution failed, treat as error - don't store
            label = f"{base_label}:{hotel_name}" if hotel_name else None
        else:
            label = base_label

        # Update active_searches state
        # Include both regular searches (with searchId) and name_resolved searches
        if label and (
            search_result["searchId"] or search_result["status"] == "name_resolved"
        ):
            active_searches[label] = {
                "searchId": search_result["searchId"],
                "status": search_result["status"],
                "destination": destination,
                "checkIn": search_result.get("checkIn"),
                "checkOut": search_result.get("checkOut"),
                "occupancy": search_result.get("occupancy"),
                "geoHash": search_result.get("geoHash"),
            }

            # For name_resolved, also store the resolved hotel info
            if search_result["status"] == "name_resolved":
                active_searches[label]["resolvedHotelId"] = search_result.get(
                    "resolvedHotelId"
                )
                active_searches[label]["resolvedHotelName"] = search_result.get(
                    "resolvedHotelName"
                )

            # Add search_key to the result so LLM knows what to use for start_room_search
            search_result["search_key"] = label

        searches_metadata.append(search_result)

    # Log what was stored
    logger.info("=" * 80)
    logger.info(f"[HOTEL_SEARCH] Stored {len(active_searches)} active search(es):")
    for label, search_info in active_searches.items():
        logger.info(
            f"  Label: '{label}' -> searchId: {search_info.get('searchId')}, status: {search_info.get('status')}"
        )
    logger.info(f"[HOTEL_SEARCH] Returning {len(searches_metadata)} search result(s)")
    logger.info("=" * 80)

    response_data = {"searches": searches_metadata}

    if runtime is None:
        return json.dumps(response_data, indent=2)

    # Auto-manage context stack: push HotelList for first successful search
    context_stack = runtime.state.get("context_stack", [])
    first_search_key = None

    # Find first successful search (with searchId or name_resolved)
    for search_meta in searches_metadata:
        if search_meta.get("searchId") or search_meta.get("status") == "name_resolved":
            destination = search_meta["destination"]
            base_label = destination.split(",")[0].strip()

            if search_meta.get("status") == "name_resolved":
                hotel_name = search_meta.get("resolvedHotelName", "")
                first_search_key = f"{base_label}:{hotel_name}"
            else:
                first_search_key = base_label
            break

    # Prepare context stack update
    update_dict = {
        "messages": [
            ToolMessage(
                content=json.dumps(response_data, indent=2),
                tool_call_id=runtime.tool_call_id,
            )
        ],
        "active_searches": active_searches,  # Will be merged by merge_dicts reducer
    }

    if first_search_key:
        context_to_push, new_stack = prepare_hotel_list_push(
            first_search_key, context_stack
        )
        if context_to_push:
            # Need to push - replace stack and append new context
            update_dict["context_stack"] = {
                "__replace__": new_stack + [context_to_push]
            }
            logger.info(
                f"[HOTEL_SEARCH] Pushing HotelList({first_search_key}) to context stack"
            )

    # Return Command with state updates
    return Command(update=update_dict)

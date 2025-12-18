"""Hotel search tool for finding and managing hotel searches."""

import asyncio
import hashlib
import httpx
import json
import jwt
import logging
import os
import time
import uuid
from typing import Annotated, Any, Dict, List, Optional

from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field, model_validator

# Import redis_client and shared libraries
from ava_v1.shared_libraries.redis_client import (
    redis_get_json_compressed,
    redis_set_json_compressed,
    get_redis_pool
)
import redis.asyncio as redis_async

from ava_v1.shared_libraries.hashing import canonical_api_hash
from ava_v1.shared_libraries.lookup_id import lookup_id
from ava_v1.shared_libraries.context_helpers import prepare_hotel_list_push

logger = logging.getLogger(__name__)


class HotelSearchParams(BaseModel):
    """Parameters for a single hotel search."""

    destination: str = Field(
        description="Destination city or location (e.g., 'Orlando', 'Miami, Florida')"
    )
    checkIn: str = Field(
        description="Check-in date in YYYY-MM-DD format (e.g., '2026-01-04')",
        alias="check_in"
    )
    checkOut: str = Field(
        description="Check-out date in YYYY-MM-DD format (e.g., '2026-01-06')",
        alias="check_out"
    )
    occupancy: Optional[Dict[str, int]] = Field(
        default=None,
        description="Occupancy details with numOfAdults (e.g., {'numOfAdults': 2})"
    )
    name: Optional[str] = Field(
        default=None,
        description="Optional hotel name for direct lookup (e.g., 'JW Marriott')"
    )

    @model_validator(mode='before')
    @classmethod
    def convert_adults_to_occupancy(cls, data: Any) -> Any:
        """Convert 'adults' field to 'occupancy' structure if needed."""
        if isinstance(data, dict):
            # If 'adults' is provided but 'occupancy' is not, convert it
            if 'adults' in data and 'occupancy' not in data:
                adults = data['adults']
                # Convert to int if it's a float with no decimal part
                if isinstance(adults, float) and adults.is_integer():
                    adults = int(adults)
                data['occupancy'] = {'numOfAdults': adults}
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
    hash_object = hashlib.md5(normalized.encode('utf-8'))
    full_hash = hash_object.hexdigest()

    # Truncate to 12 characters for compact Redis keys
    return full_hash[:12]


async def get_geo_coordinates(destination: str) -> str:
    """Get geographic coordinates for a destination using Google Places API.

    Includes Redis caching to reduce API calls and country gating for restrictions.

    Args:
        destination: The destination query string (e.g., "Orlando, Florida")
        runtime: Injected tool runtime (unused, no state updates)

    Returns:
        JSON string with latitude, longitude, displayName, formattedAddress, and countryCode if found.
        Returns error dict if country not allowed or lookup fails:
        {"error": "country_not_supported", "country": "FR", "message": "..."}
        {"error": "no_results", "message": "..."}
        {"error": "api_error", "message": "..."}
    """
    try:
        # Validate inputs
        if not destination or not destination.strip():
            result = {"error": "invalid_input", "message": "Destination query cannot be empty"}
            return json.dumps(result, indent=2)

        # Generate hash for Redis cache key
        dest_hash = geo_destination_hash(destination)
        redis_key = f"geo:{dest_hash}"

        # Check Redis cache first
        cached_geo_data = await redis_get_json_compressed(redis_key)
        if cached_geo_data:
            # Cache hit - return cached data
            return json.dumps(cached_geo_data, indent=2)

        # Cache miss - fetch from Google Places API
        # Get Google API key from environment variables
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            result = {"error": "configuration", "message": "GOOGLE_API_KEY not configured"}
            return json.dumps(result, indent=2)

        # Prepare request body
        request_body = {"textQuery": destination.strip(), "pageSize": 1}

        # Prepare headers - include addressComponents to get country code
        headers = {
            "X-Goog-Api-Key": google_api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.addressComponents",
            "Content-Type": "application/json",
        }

        # Make async POST request to Google Places API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=request_body,
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

        # Extract and format results
        places = data.get("places", [])

        if not places:
            result = {"error": "no_results", "message": f"No places found for '{destination}'"}
            return json.dumps(result, indent=2)

        # Format the first place result
        place = places[0]
        location = place.get("location", {})

        # Extract country code from address components
        country_code = None
        address_components = place.get("addressComponents", [])
        for component in address_components:
            if "country" in component.get("types", []):
                country_code = component.get("shortText", "").upper()  # ISO 3166-1 alpha-2
                break

        geo_data = {
            "displayName": place.get("displayName", {}).get("text", "N/A"),
            "formattedAddress": place.get("formattedAddress", "N/A"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "countryCode": country_code,
        }

        # Validate that we got coordinates
        if geo_data["latitude"] is None or geo_data["longitude"] is None:
            result = {"error": "no_coordinates", "message": f"No coordinates found for '{destination}'"}
            return json.dumps(result, indent=2)

        # Country gating validation
        gating_enabled = os.getenv("HOTEL_SEARCH_COUNTRY_GATING_ENABLED", "true").lower() == "true"

        if gating_enabled and country_code:
            allowed_countries = os.getenv("HOTEL_SEARCH_ALLOWED_COUNTRIES", "US").upper().split(",")
            allowed_countries = [c.strip() for c in allowed_countries]  # Clean whitespace

            if country_code not in allowed_countries:
                error_response = {
                    "error": "country_not_supported",
                    "country": country_code,
                    "destination": destination,
                    "message": f"Hotel search is currently only available in: {', '.join(allowed_countries)}. "
                               f"The destination '{destination}' is in {country_code}."
                }
                # Don't cache errors - user might be testing different destinations
                return json.dumps(error_response, indent=2)

        # Store successful geo data in Redis cache with 30-day TTL
        # Coordinates don't change often, so long TTL is appropriate
        TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days = 2,592,000 seconds
        await redis_set_json_compressed(redis_key, geo_data, TTL_SECONDS)

        return json.dumps(geo_data, indent=2)

    except httpx.HTTPStatusError as e:
        result = {"error": "api_error", "message": f"HTTP error: {str(e)}"}
        return json.dumps(result, indent=2)
    except httpx.RequestError as e:
        result = {"error": "api_error", "message": f"Request error: {str(e)}"}
        return json.dumps(result, indent=2)
    except Exception as e:
        result = {"error": "api_error", "message": f"Unexpected error: {str(e)}"}
        return json.dumps(result, indent=2)


async def _check_redis_cache(search_hash: str) -> Optional[List[Dict[str, Any]]]:
    """Check Redis JSON cache for existing search results.

    Args:
        search_hash: The canonical hash for the search (e.g., "abc123")

    Returns:
        Cached results if found, None otherwise
    """
    try:
        pool = get_redis_pool()
        redis_client = redis_async.Redis(connection_pool=pool)

        # Build Redis key: search:{hash}
        redis_key = f"search:{search_hash}"

        # Check if key exists
        exists = await redis_client.exists(redis_key)
        if not exists:
            return None

        # Get data using Redis JSON
        cached_data = await redis_client.execute_command(
            'JSON.GET', redis_key
        )

        if cached_data:
            return json.loads(cached_data)

        return None

    except Exception as e:
        # Log error but don't fail - just treat as cache miss
        logger.warning(f"Redis cache check error: {e}")
        return None


async def _init_hotel_search(search: Dict[str, Any], geo_data: Dict[str, Any]) -> str:
    """Initialize hotel search by calling the init API endpoint.

    Args:
        search: The search parameters
        geo_data: Geographic data including coordinates and country code

    Returns:
        Token string for polling the search results

    Raises:
        httpx.HTTPStatusError: If the API returns an error status
        Exception: For other API-related errors
    """
    # Build request body
    request_body = {
        "currency": "USD",
        "culture": "en-US",
        "checkIn": search["checkIn"],
        "checkOut": search["checkOut"],
        "occupancy": search["occupancy"],
        "circularRegion": {
            "centerLat": geo_data["latitude"],
            "centerLong": geo_data["longitude"],
            "radiusInKM": 50  # Hardcoded 50km radius
        },
        "countryOfResidence": "US"
    }

    # Build headers
    correlation_id = str(uuid.uuid4())
    headers = {
        "accountId": os.getenv("HOTEL_API_ACCOUNT_ID", "test-hotels-account-v2"),
        "channelId": os.getenv("HOTEL_API_CHANNEL_ID", "test-hotels-channel-v2"),
        "Content-Type": "application/json",
        "correlationId": correlation_id
    }

    # Call init endpoint
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://54.198.17.253:6001/api/hotel/availability/init",
            headers=headers,
            json=request_body,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    # Extract and return token
    token = data.get("token")
    if not token:
        raise Exception("API did not return a token")

    return token


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
        "jti": f"jwt_{uuid.uuid4().hex[:8]}"
    }

    # Generate and return JWT token
    token = jwt.encode(payload, jwt_secret, algorithm="HS256")
    return token


async def _start_polling_job(token: str, search_hash: str, destination: str) -> Dict[str, Any]:
    """Send token to Go polling service to start background polling job.

    Args:
        token: Token from init endpoint
        search_hash: Redis cache key (canonical hash, without 'search:' prefix)
        destination: Destination name (for logging)

    Returns:
        Dict with search metadata

    Raises:
        httpx.HTTPError: If polling service call fails
        Exception: If polling service returns an error response
    """
    # Get polling service URL from environment
    polling_service_url = os.getenv(
        "POLLING_SERVICE_URL",
        "http://localhost:8080"
    )

    # Ensure search_id has "search:" prefix for Go service
    search_id_with_prefix = f"search:{search_hash}" if not search_hash.startswith("search:") else search_hash

    # Call polling service
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{polling_service_url}/v1/search",
            json={
                "token": token,
                "search_id": search_id_with_prefix,
                "destination": destination
            },
            timeout=5.0
        )

        # Check for HTTP errors (400, 502, etc.)
        response.raise_for_status()

        # Parse response
        response_data = response.json()

        # Check if response contains an error
        if "error" in response_data:
            error_msg = response_data.get("message", "Unknown polling service error")
            raise Exception(f"Polling service error: {error_msg}")

        return response_data


async def _process_single_search(search: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Process a single hotel search - initiate or return cached.

    Args:
        search: Search parameters dictionary

    Returns:
        Dict with search metadata (searchId, status, etc.)
        None if invalid parameters
    """
    # Validate required fields
    required_fields = ["checkIn", "checkOut", "occupancy"]
    if not all(field in search for field in required_fields):
        logger.warning(f"[HOTEL_SEARCH] Missing required fields in search: {search}. Required: {required_fields}, Got keys: {list(search.keys())}")
        return None

    # Accept both "Destination" (capital D) and "destination" (lowercase d)
    destination = search.get("Destination") or search.get("destination")
    if not destination:
        return None

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
                    "message": lookup_result.get("message", "Failed to lookup hotel by name")
                }
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
                "message": f"Found {hotel_name_from_lookup}. Ready to check room availability."
            }

        elif confidence == "low":
            # Multiple matches - return for clarification
            hotels = lookup_result.get("hotels", [])
            return {
                "destination": destination,
                "searchId": None,
                "status": "clarification_needed",
                "hotels": hotels,
                "message": f"Found {len(hotels)} hotels matching '{search['name']}'."
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
                "error": geo_data
            }

        # Generate canonical hash for this search
        search_params = {
            "checkIn": search["checkIn"],
            "checkOut": search["checkOut"],
            "occupancy": search["occupancy"],
            "circularRegion": {
                "centerLat": geo_data["latitude"],
                "centerLong": geo_data["longitude"],
                "radiusInKM": 50
            }
        }
        search_hash = canonical_api_hash(search_params)
        geo_hash = geo_destination_hash(destination)

        # Check Redis cache for existing results
        cached_results = await _check_redis_cache(search_hash)

        if cached_results:
            # Cache hit - return immediately
            hotel_count = len(cached_results) if isinstance(cached_results, list) else 0
            return {
                "destination": destination,
                "searchId": search_hash,
                "status": "cached",
                "hotelCount": hotel_count,
                "checkIn": search["checkIn"],
                "checkOut": search["checkOut"],
                "occupancy": search["occupancy"],
                "geoHash": geo_hash,
                "message": f"Found {hotel_count} hotels (from recent search)."
            }

        # Cache miss - initiate new search
        # Step 1: Call init endpoint to get token
        token = await _init_hotel_search(search, geo_data)

        # Step 2: Start polling job
        polling_response = await _start_polling_job(token, search_hash, destination)

        # Build result
        result = {
            "destination": destination,
            "searchId": search_hash,
            "status": "polling",
            "checkIn": search["checkIn"],
            "checkOut": search["checkOut"],
            "occupancy": search["occupancy"],
            "geoHash": geo_hash
        }

        # Add optional fields if present
        if "expected_hotel_count" in polling_response:
            result["expectedHotelCount"] = polling_response["expected_hotel_count"]
        if "loaded_count" in polling_response:
            result["loadedCount"] = polling_response["loaded_count"]
        if "estimated_seconds" in polling_response:
            result["estimatedSeconds"] = polling_response["estimated_seconds"]
        if "message" in polling_response:
            result["message"] = polling_response["message"]

        # Add resolved hotel_id if name lookup was performed
        if resolved_hotel_id:
            result["resolvedHotelId"] = resolved_hotel_id
            result["resolvedHotelName"] = hotel_name_from_lookup

        return result

    except Exception as e:
        return {
            "destination": destination,
            "searchId": search_hash if 'search_hash' in locals() else None,
            "status": "error",
            "error": {
                "type": "init_failed",
                "message": str(e)
            }
        }


@tool(description="Initiate hotel searches - returns immediately with search status")
async def hotel_search(
    searches: List[HotelSearchParams],
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Initiate hotel searches - returns immediately with search status.

    PURPOSE:
        Initiate hotel searches for a destination. This tool does NOT wait for complete
        results - it returns immediately with a status. Use query_vfs() tool after engaging
        the user to retrieve and filter results.

        If user provides a hotel name (e.g., "JW Marriott"), this tool will attempt
        to resolve it directly, allowing you to skip straight to rooms_and_rates().

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
    logger.info(f"[HOTEL_SEARCH] Tool called with {len(searches)} search(es)")
    logger.info(f"[HOTEL_SEARCH] Searches: {searches}")
    logger.info("=" * 80)

    # Convert Pydantic models to dicts
    search_dicts = [search.model_dump(by_alias=False) for search in searches]

    # Process all searches in parallel
    search_tasks = [_process_single_search(search) for search in search_dicts]
    search_results = await asyncio.gather(*search_tasks)

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
            if hotel_name:
                label = f"{base_label}:{hotel_name}"
            else:
                # If name resolution failed, treat as error - don't store
                label = None
        else:
            label = base_label

        # Update active_searches state
        # Include both regular searches (with searchId) and name_resolved searches
        if label and (search_result["searchId"] or search_result["status"] == "name_resolved"):
            active_searches[label] = {
                "searchId": search_result["searchId"],
                "status": search_result["status"],
                "destination": destination,
                "checkIn": search_result.get("checkIn"),
                "checkOut": search_result.get("checkOut"),
                "occupancy": search_result.get("occupancy"),
                "geoHash": search_result.get("geoHash")
            }

            # For name_resolved, also store the resolved hotel info
            if search_result["status"] == "name_resolved":
                active_searches[label]["resolvedHotelId"] = search_result.get("resolvedHotelId")
                active_searches[label]["resolvedHotelName"] = search_result.get("resolvedHotelName")

            # Add search_key to the result so LLM knows what to use for rooms_and_rates
            search_result["search_key"] = label

        searches_metadata.append(search_result)

    # Log what was stored
    logger.info("=" * 80)
    logger.info(f"[HOTEL_SEARCH] Stored {len(active_searches)} active search(es):")
    for label, search_info in active_searches.items():
        logger.info(f"  Label: '{label}' -> searchId: {search_info.get('searchId')}, status: {search_info.get('status')}")
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
        "messages": [ToolMessage(
            content=json.dumps(response_data, indent=2),
            tool_call_id=runtime.tool_call_id
        )],
        "active_searches": active_searches,  # Will be merged by merge_dicts reducer
    }

    if first_search_key:
        context_to_push, new_stack = prepare_hotel_list_push(first_search_key, context_stack)
        if context_to_push:
            # Need to push - replace stack and append new context
            update_dict["context_stack"] = {"__replace__": new_stack + [context_to_push]}
            logger.info(f"[HOTEL_SEARCH] Pushing HotelList({first_search_key}) to context stack")

    # Return Command with state updates
    return Command(update=update_dict)

"""Room inventory and rate tool for hotels."""

import httpx
import json
import logging
import os
from typing import Annotated, Any, Dict, Optional

from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

# Import redis_client and shared libraries
from ava_v1.shared_libraries.redis_client import get_redis_pool
import redis.asyncio as redis_async

from ava_v1.shared_libraries.hashing import canonical_rooms_hash
from ava_v1.shared_libraries.context_helpers import prepare_room_list_push

logger = logging.getLogger(__name__)


async def _check_redis_cache_rooms(room_search_hash: str) -> Optional[Dict[str, Any]]:
    """Check Redis JSON cache for existing room/rate results.

    Args:
        room_search_hash: The canonical hash for the room search (e.g., "f3a9b2c8d1e4")

    Returns:
        Dict with {rooms: [...], name: str, token: str} if cached
        None if cache miss or error
    """
    try:
        pool = get_redis_pool()
        redis_client = redis_async.Redis(connection_pool=pool)

        redis_key = f"rooms:{room_search_hash}"

        # Check if key exists first
        exists = await redis_client.exists(redis_key)
        if not exists:
            return None

        # Get data using Redis JSON
        result = await redis_client.execute_command('JSON.GET', redis_key, '$')

        if result:
            # Parse JSON result
            data = json.loads(result)
            # Redis JSON returns array when using '$' path, get first element
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return data

        return None

    except Exception as e:
        logger.warning(f"Redis cache check error for rooms:{room_search_hash}: {e}")
        return None


async def _start_rooms_polling_job(
    hotel_id: str,
    search_params: Dict[str, Any],
    room_search_hash: str
) -> Dict[str, Any]:
    """Send request to Go polling service to start room/rate polling job.

    Args:
        hotel_id: Hotel ID (e.g., "39615853")
        search_params: Dict with checkIn, checkOut, occupancy
        room_search_hash: Redis cache key (canonical hash, without 'rooms:' prefix)

    Returns:
        Dict with polling metadata

    Raises:
        httpx.HTTPError: If polling service call fails
        Exception: If polling service returns an error response
    """
    polling_service_url = os.getenv("POLLING_SERVICE_URL", "http://localhost:8080")
    endpoint = f"{polling_service_url}/v1/search/rooms"

    # Build request body
    request_body = {
        "checkIn": search_params["checkIn"],
        "checkOut": search_params["checkOut"],
        "occupancy": search_params["occupancy"],
        "hotelId": int(hotel_id)  # Convert to int for API
    }

    # Make async POST request
    async with httpx.AsyncClient() as client:
        response = await client.post(
            endpoint,
            json=request_body,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    # Validate response
    if "error" in data:
        raise Exception(f"Polling service error: {data.get('message', 'Unknown error')}")

    return data


@tool(description="Start room search - initiates room search and returns status (does not return room results)")
async def start_room_search(
    hotel_id: str,
    search_key: str,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Start room search - initiates room search but does NOT return room results.

    PURPOSE:
        Initiate room search for a specific hotel. This tool does NOT return room results -
        it returns immediately with a status and optional firstRoom preview. CRITICAL: The
        firstRoom preview is INCOMPLETE and CANNOT be used for booking. You MUST call
        query_vfs() after engaging the user to get complete room data with token and rate_key.

    PARAMETERS:
        hotel_id (str): Hotel ID from either:
            - query_vfs results after hotel search (the "id" field)
            - start_hotel_search resolvedHotelId (when name_resolved status)
        search_key (str): Search key from start_hotel_search response
            - Simple format: "Miami" (for full destination searches)
            - Composite format: "Miami:JW Marriott" (for name-resolved searches)
            - IMPORTANT: Use the exact searchKey from start_hotel_search response
        runtime: Injected tool runtime for accessing agent state

    RETURNS:
        Command with state updates containing room search metadata

    CRITICAL WARNINGS:
        - The firstRoom field (when status="cached") is a PREVIEW ONLY
        - firstRoom does NOT contain the token or complete rate_key needed for booking
        - DO NOT attempt to book using firstRoom data
        - You MUST call query_vfs() after this tool to get complete room data
    """
    logger.info("=" * 80)
    logger.info(f"[ROOMS_AND_RATES] Tool called with:")
    logger.info(f"  hotel_id: {hotel_id}")
    logger.info(f"  search_key: {search_key}")
    logger.info("=" * 80)

    # Validate inputs
    if not hotel_id or not isinstance(hotel_id, str) or not hotel_id.strip():
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_hotel_id",
                "message": "hotel_id must be a non-empty string"
            }
        }
        return json.dumps(error_result, indent=2)

    if not search_key or not isinstance(search_key, str) or not search_key.strip():
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_search_key",
                "message": "search_key must be a non-empty string"
            }
        }
        return json.dumps(error_result, indent=2)

    # Lookup search parameters from active_searches
    active_searches = runtime.state.get("active_searches", {}) if runtime else {}

    if search_key not in active_searches:
        # Provide helpful hints about available searches
        available = list(active_searches.keys())
        hint = ""
        if available:
            hint = f" Available searches: {', '.join(available)}. Use the search_key from start_hotel_search response."
        else:
            hint = " Run start_hotel_search first to create a search."

        error_result = {
            "status": "error",
            "error": {
                "type": "search_key_not_found",
                "message": f"No active search found for '{search_key}'.{hint}"
            }
        }
        return json.dumps(error_result, indent=2)

    search_meta = active_searches[search_key]

    # Check if hotel search has expired (Redis keys missing)
    try:
        pool = get_redis_pool()
        redis_client = redis_async.Redis(connection_pool=pool)

        hotel_search_id = search_meta.get("searchId")
        if hotel_search_id:
            exists = await redis_client.exists(f"search:{hotel_search_id}")
            if not exists:
                error_result = {
                    "status": "error",
                    "error": {
                        "type": "search_expired",
                        "message": f"Hotel search for '{search_key}' has expired. Please run a new search."
                    }
                }
                return json.dumps(error_result, indent=2)
    except Exception as e:
        logger.warning(f"Could not check hotel search expiration: {e}")

    # Validate required parameters in search_meta
    required = ["checkIn", "checkOut", "occupancy"]
    missing = [f for f in required if f not in search_meta]
    if missing:
        error_result = {
            "status": "error",
            "error": {
                "type": "missing_parameters",
                "message": f"Search key '{search_key}' missing required fields: {', '.join(missing)}"
            }
        }
        return json.dumps(error_result, indent=2)

    # Extract search parameters
    search_params = {
        "checkIn": search_meta["checkIn"],
        "checkOut": search_meta["checkOut"],
        "occupancy": search_meta["occupancy"]
    }

    # Generate canonical hash
    room_search_hash = canonical_rooms_hash(hotel_id, search_params)

    # Check Redis cache
    cached_rooms = await _check_redis_cache_rooms(room_search_hash)

    if cached_rooms is not None:
        # Cache HIT - return first room + count
        rooms_array = cached_rooms.get("rooms", [])

        result = {
            "hotelId": hotel_id,
            "searchKey": search_key,
            "roomSearchId": room_search_hash,
            "status": "cached",
            "roomCount": len(rooms_array),
            "checkIn": search_params["checkIn"],
            "checkOut": search_params["checkOut"],
            "occupancy": search_params["occupancy"]
        }

        # Add first room and hotel name if available
        if len(rooms_array) > 0:
            result["firstRoom"] = rooms_array[0]
        if "name" in cached_rooms:
            result["hotelName"] = cached_rooms["name"]

        # Add hint for next action
        result["hint"] = f"Room data available. firstRoom is a preview only. Ask user about room preferences (refundable/non-refundable, bed type), then call query_vfs(destination=\"{search_key}:rooms:{hotel_id}\") to get complete booking data."

        # Update active_searches with roomSearchId
        updated_search_meta = {**search_meta, "roomSearchId": room_search_hash}

        if runtime is None:
            return json.dumps(result, indent=2)

        # Auto-manage context stack: push RoomList
        context_stack = runtime.state.get("context_stack", [])
        context_to_push, new_stack = prepare_room_list_push(
            search_key, hotel_id, room_search_hash, context_stack
        )

        update_dict = {
            "messages": [ToolMessage(
                content=json.dumps(result, indent=2),
                tool_call_id=runtime.tool_call_id
            )],
            "active_searches": {
                search_key: updated_search_meta
            },  # Will be merged by merge_dicts reducer
        }

        if context_to_push:
            # Need to push - replace stack and append new context
            update_dict["context_stack"] = {"__replace__": new_stack + [context_to_push]}
            logger.info(f"[ROOMS_AND_RATES] Pushing RoomList({search_key}, {hotel_id}) to context stack")

        return Command(update=update_dict)

    # Cache MISS - start polling job
    try:
        polling_response = await _start_rooms_polling_job(
            hotel_id=hotel_id,
            search_params=search_params,
            room_search_hash=room_search_hash
        )

        result = {
            "hotelId": hotel_id,
            "searchKey": search_key,
            "roomSearchId": room_search_hash,
            "status": "polling",
            "checkIn": search_params["checkIn"],
            "checkOut": search_params["checkOut"],
            "occupancy": search_params["occupancy"],
            "hint": f"Room search initiated. Ask user about room preferences (refundable/non-refundable, bed type, floor preference) while search runs. Call query_vfs(destination=\"{search_key}:rooms:{hotel_id}\") after user responds."
        }

        # Update active_searches with roomSearchId
        updated_search_meta = {**search_meta, "roomSearchId": room_search_hash}

        if runtime is None:
            return json.dumps(result, indent=2)

        # Auto-manage context stack: push RoomList
        context_stack = runtime.state.get("context_stack", [])
        context_to_push, new_stack = prepare_room_list_push(
            search_key, hotel_id, room_search_hash, context_stack
        )

        update_dict = {
            "messages": [ToolMessage(
                content=json.dumps(result, indent=2),
                tool_call_id=runtime.tool_call_id
            )],
            "active_searches": {
                search_key: updated_search_meta
            },  # Will be merged by merge_dicts reducer
        }

        if context_to_push:
            # Need to push - replace stack and append new context
            update_dict["context_stack"] = {"__replace__": new_stack + [context_to_push]}
            logger.info(f"[ROOMS_AND_RATES] Pushing RoomList({search_key}, {hotel_id}) to context stack")

        return Command(update=update_dict)

    except Exception as e:
        error_result = {
            "status": "error",
            "error": {
                "type": "polling_service_error",
                "message": f"Failed to start room search: {str(e)}"
            }
        }
        return json.dumps(error_result, indent=2)

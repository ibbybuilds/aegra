"""Room inventory and rate tool for hotels."""

import json
import logging
import os
from typing import Annotated, Any

import httpx
import redis.asyncio as redis_async
from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from ava_v1.shared_libraries.context_helpers import prepare_room_list_push
from ava_v1.shared_libraries.hashing import canonical_rooms_hash

# Import redis_client and shared libraries
from ava_v1.shared_libraries.redis_client import get_redis_pool

logger = logging.getLogger(__name__)


async def _start_rooms_search(
    hotel_id: str,
    search_params: dict[str, Any]
) -> dict[str, Any]:
    """Send room search request to cache-worker.

    Cache-worker handles hash generation, cache checking, and polling internally.
    Returns metadata only.

    Args:
        hotel_id: Hotel ID
        search_params: Dict with checkIn, checkOut, occupancy

    Returns:
        Dict with roomSearchId, status, roomCount (metadata only)
    """
    cache_worker_url = os.getenv("CACHE_WORKER_URL", "http://localhost:8080")
    endpoint = f"{cache_worker_url}/v1/search/rooms"

    request_body = {
        "hotelId": int(hotel_id),
        "checkIn": search_params["checkIn"],
        "checkOut": search_params["checkOut"],
        "occupancy": search_params["occupancy"],
    }

    logger.info(f"[ROOMS_SEARCH] Calling cache-worker: {endpoint}")
    logger.info(f"[ROOMS_SEARCH] Request body: {request_body}")

    async with httpx.AsyncClient() as client:
        response = await client.post(endpoint, json=request_body, timeout=30.0)
        response.raise_for_status()
        data = response.json()

    logger.info(f"[ROOMS_SEARCH] Response status: {data['status']}")
    logger.info(f"[ROOMS_SEARCH] Room search ID: {data['roomSearchId']}")

    return data


@tool(
    description="Start room search - initiates room search and returns status (does not return room results)"
)
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
    logger.info("[ROOMS_AND_RATES] Tool called with:")
    logger.info(f"  hotel_id: {hotel_id}")
    logger.info(f"  search_key: {search_key}")
    logger.info("=" * 80)

    # Validate inputs
    if not hotel_id or not isinstance(hotel_id, str) or not hotel_id.strip():
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_hotel_id",
                "message": "hotel_id must be a non-empty string",
            },
        }
        return json.dumps(error_result, indent=2)

    if not search_key or not isinstance(search_key, str) or not search_key.strip():
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_search_key",
                "message": "search_key must be a non-empty string",
            },
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
                "message": f"No active search found for '{search_key}'.{hint}",
            },
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
                        "message": f"Hotel search for '{search_key}' has expired. Please run a new search.",
                    },
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
                "message": f"Search key '{search_key}' missing required fields: {', '.join(missing)}",
            },
        }
        return json.dumps(error_result, indent=2)

    # Extract search parameters
    search_params = {
        "checkIn": search_meta["checkIn"],
        "checkOut": search_meta["checkOut"],
        "occupancy": search_meta["occupancy"],
    }

    logger.info(f"[ROOMS_AND_RATES] Search params: {search_params}")

    # Call cache-worker (replaces hash generation, cache check, polling)
    try:
        search_result = await _start_rooms_search(hotel_id, search_params)

        # Cache HIT - return metadata
        if search_result["status"] == "cached":
            logger.info(f"[ROOMS_AND_RATES] Cache HIT! {search_result.get('roomCount', 0)} rooms available")

            result = {
                "hotelId": hotel_id,
                "searchKey": search_key,
                "roomSearchId": search_result["roomSearchId"],
                "status": "cached",
                "roomCount": search_result.get("roomCount", 0),
                "checkIn": search_params["checkIn"],
                "checkOut": search_params["checkOut"],
                "occupancy": search_params["occupancy"],
            }

            # Add optional fields if present
            if "hotelName" in search_result:
                result["hotelName"] = search_result["hotelName"]

            # Add hint for next action
            result["hint"] = (
                f'Room data cached. Ask user about room preferences (refundable/non-refundable, bed type), '
                f'then call query_vfs(destination="{search_key}:rooms:{hotel_id}") to retrieve complete room list.'
            )

            # Update active_searches with roomSearchId
            updated_search_meta = {**search_meta, "roomSearchId": search_result["roomSearchId"]}

        # Cache MISS - return polling status
        else:
            logger.info(f"[ROOMS_AND_RATES] Cache MISS - polling initiated")

            result = {
                "hotelId": hotel_id,
                "searchKey": search_key,
                "roomSearchId": search_result["roomSearchId"],
                "status": "polling",
                "checkIn": search_params["checkIn"],
                "checkOut": search_params["checkOut"],
                "occupancy": search_params["occupancy"],
                "estimatedSeconds": search_result.get("estimatedSeconds", 5),
                "hint": (
                    f'Room search initiated. Ask user about room preferences (refundable/non-refundable, bed type) '
                    f'while search runs. Call query_vfs(destination="{search_key}:rooms:{hotel_id}") after user responds.'
                ),
            }

            # Update active_searches with roomSearchId
            updated_search_meta = {**search_meta, "roomSearchId": search_result["roomSearchId"]}

        if runtime is None:
            return json.dumps(result, indent=2)

        # Auto-manage context stack: push RoomList
        context_stack = runtime.state.get("context_stack", [])
        context_to_push, new_stack = prepare_room_list_push(
            search_key, hotel_id, search_result["roomSearchId"], context_stack
        )

        update_dict = {
            "messages": [
                ToolMessage(
                    content=json.dumps(result, indent=2),
                    tool_call_id=runtime.tool_call_id,
                )
            ],
            "active_searches": {
                search_key: updated_search_meta
            },  # Will be merged by merge_dicts reducer
        }

        if context_to_push:
            # Need to push - replace stack and append new context
            update_dict["context_stack"] = {
                "__replace__": new_stack + [context_to_push]
            }
            logger.info(
                f"[ROOMS_AND_RATES] Pushing RoomList({search_key}, {hotel_id}) to context stack"
            )

        return Command(update=update_dict)

    except Exception as e:
        logger.error(f"[ROOMS_AND_RATES] Cache-worker error: {type(e).__name__}: {str(e)}")
        error_result = {
            "status": "error",
            "error": {
                "type": "room_search_error",
                "message": f"Failed to start room search: {str(e)}",
            },
        }
        return json.dumps(error_result, indent=2)

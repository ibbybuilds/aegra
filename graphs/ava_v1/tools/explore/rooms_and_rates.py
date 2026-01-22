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
from pydantic import BaseModel, Field

from ava_v1.shared_libraries.context_helpers import prepare_room_list_push

# Import redis_client and shared libraries
from ava_v1.shared_libraries.redis_client import get_redis_pool

logger = logging.getLogger(__name__)


async def _start_rooms_search(
    hotel_id: str, search_params: dict[str, Any]
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


class StartRoomSearchInput(BaseModel):
    """Input schema for starting room search."""

    hotel_id: str = Field(
        description="Hotel ID from query_vfs results (the 'id' field) or start_hotel_search resolvedHotelId"
    )
    search_key: str | None = Field(
        default=None,
        description="Optional search key from start_hotel_search response (e.g., 'Miami' or 'Miami:JW Marriott'). "
        "Omit for property_specific searches where params are collected via update_search_params."
    )


@tool(
    args_schema=StartRoomSearchInput,
    description="""Start room search for a specific hotel - initiates search but does NOT return complete room results.

WARNING - FirstRoom Preview:
When status='cached', response MAY include a 'firstRoom' field as a PREVIEW ONLY.
- firstRoom is INCOMPLETE and CANNOT be used for booking
- firstRoom lacks token (required for book_room)
- firstRoom has incomplete rate_key (required for book_room)
- DO NOT attempt to book using firstRoom data

REQUIRED Next Step:
You MUST call query_vfs(destination="{search_key}:rooms:{hotel_id}") after engaging user to get:
- Complete room list with all available rooms
- Token at TOP LEVEL (required for book_room)
- Complete rate_key in each room object (required for book_room)

Parameters:
- hotel_id: From query_vfs results ('id' field) or start_hotel_search resolvedHotelId
- search_key: Optional. From start_hotel_search response (e.g., "Miami" or "Miami:JW Marriott").
  OMIT this parameter for property_specific searches where you used update_search_params to collect dates/occupancy.

Usage Patterns:
1. Regular flow (after hotel_search): start_room_search(hotel_id="123", search_key="Miami")
2. Property_specific flow (no hotel_search): Use update_search_params first, then start_room_search(hotel_id="123")

Returns:
Search status (cached/polling) and metadata. Always call query_vfs() next for complete room data with token.

Example Flow 1 (Regular):
1. start_room_search(hotel_id="123", search_key="Miami")
2. Response: {"status": "cached", "roomSearchId": "abc", "hint": "...call query_vfs..."}
3. Engage user about room preferences
4. query_vfs(destination="Miami:rooms:123")
5. Response: Complete room list with token and rate_keys for booking

Example Flow 2 (Property-specific):
1. update_search_params(field="checkIn", value="2026-02-01")
2. update_search_params(field="checkOut", value="2026-02-04")
3. update_search_params(field="numOfAdults", value=2)
4. start_room_search(hotel_id="123")  # No search_key
5. Response: Creates active_searches entry with hotel_name as key
6. query_vfs(destination="{hotel_name}:rooms:123")""",
)
async def start_room_search(
    hotel_id: str,
    search_key: str | None = None,
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

    # Validate hotel_id
    if not hotel_id or not isinstance(hotel_id, str) or not hotel_id.strip():
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_hotel_id",
                "message": "hotel_id must be a non-empty string",
            },
        }
        return json.dumps(error_result, indent=2)

    # Get state
    active_searches = runtime.state.get("active_searches", {}) if runtime else {}
    search_params_staging = runtime.state.get("search_params", {}) if runtime else {}
    if search_params_staging is None:
        search_params_staging = {}

    logger.info("=" * 80)
    logger.info("[ROOMS_AND_RATES] State at entry:")
    logger.info(f"  search_params: {search_params_staging}")
    logger.info(f"  active_searches keys: {list(active_searches.keys())}")
    logger.info(f"  search_key provided: {search_key}")
    logger.info("=" * 80)

    # Track whether we used search_params (so we can clear it later)
    clear_staging = False

    # PATH 1: search_key provided (existing or needs backfill)
    if search_key:
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

        # Check if params are missing (need backfill)
        required = ["checkIn", "checkOut", "occupancy"]
        missing = [f for f in required if f not in search_meta or not search_meta[f]]

        if missing:
            # Backfill from search_params
            if not search_params_staging:
                error_result = {
                    "status": "error",
                    "error": {
                        "type": "missing_parameters",
                        "message": f"Search key '{search_key}' missing required fields: {', '.join(missing)} and no search_params available",
                    },
                }
                return json.dumps(error_result, indent=2)

            # Validate search_params has what we need
            # For occupancy, we only require numOfAdults (numOfRooms and childAges have defaults)
            staging_missing = []
            if "checkIn" in missing and "checkIn" not in search_params_staging:
                staging_missing.append("checkIn")
            if "checkOut" in missing and "checkOut" not in search_params_staging:
                staging_missing.append("checkOut")
            if "occupancy" in missing and "numOfAdults" not in search_params_staging:
                staging_missing.append("numOfAdults")

            if staging_missing:
                error_result = {
                    "status": "error",
                    "error": {
                        "type": "incomplete_search_params",
                        "message": f"search_params missing required fields: {', '.join(staging_missing)}",
                    },
                }
                return json.dumps(error_result, indent=2)

            # Backfill missing fields with defaults
            logger.info("=" * 80)
            logger.info(f"[ROOMS_AND_RATES] PATH 1 - Backfilling {len(missing)} missing fields from search_params")
            if "checkIn" in missing:
                search_meta["checkIn"] = search_params_staging["checkIn"]
                logger.info(f"[ROOMS_AND_RATES]   Backfilled checkIn: {search_meta['checkIn']}")
            if "checkOut" in missing:
                search_meta["checkOut"] = search_params_staging["checkOut"]
                logger.info(f"[ROOMS_AND_RATES]   Backfilled checkOut: {search_meta['checkOut']}")
            if "occupancy" in missing:
                search_meta["occupancy"] = {
                    "numOfAdults": search_params_staging["numOfAdults"],  # Required field
                    "numOfRooms": search_params_staging.get("numOfRooms", 1),  # Default: 1 room
                    "childAges": search_params_staging.get("childAges", []),  # Default: no children
                }
                logger.info(f"[ROOMS_AND_RATES]   Backfilled occupancy (with defaults): {search_meta['occupancy']}")
            logger.info(f"[ROOMS_AND_RATES]   Updated search_meta: {search_meta}")
            logger.info("=" * 80)

            clear_staging = True

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

        # Extract search parameters
        search_params = {
            "checkIn": search_meta["checkIn"],
            "checkOut": search_meta["checkOut"],
            "occupancy": search_meta["occupancy"],
        }

    # PATH 2: No search_key (property_specific case)
    else:
        # Must use search_params
        if not search_params_staging:
            error_result = {
                "status": "error",
                "error": {
                    "type": "missing_search_params",
                    "message": "No search_key provided and search_params is empty. Use update_search_params to collect dates and occupancy first.",
                },
            }
            return json.dumps(error_result, indent=2)

        # Validate search_params has required fields
        # For occupancy, we only require numOfAdults (numOfRooms and childAges have defaults)
        staging_missing = []
        if "checkIn" not in search_params_staging:
            staging_missing.append("checkIn")
        if "checkOut" not in search_params_staging:
            staging_missing.append("checkOut")
        if "numOfAdults" not in search_params_staging:
            staging_missing.append("numOfAdults")

        if staging_missing:
            error_result = {
                "status": "error",
                "error": {
                    "type": "incomplete_search_params",
                    "message": f"search_params missing required fields: {', '.join(staging_missing)}",
                },
            }
            return json.dumps(error_result, indent=2)

        # Extract search params from staging (construct occupancy object with defaults)
        logger.info("=" * 80)
        logger.info("[ROOMS_AND_RATES] PATH 2 - No search_key, constructing from search_params")
        search_params = {
            "checkIn": search_params_staging["checkIn"],
            "checkOut": search_params_staging["checkOut"],
            "occupancy": {
                "numOfAdults": search_params_staging["numOfAdults"],  # Required field
                "numOfRooms": search_params_staging.get("numOfRooms", 1),  # Default: 1 room
                "childAges": search_params_staging.get("childAges", []),  # Default: no children
            },
        }
        logger.info(f"[ROOMS_AND_RATES]   Constructed search_params: {search_params}")
        logger.info("=" * 80)

        # Get hotel_name for active_searches key
        # Try: call_context.property.property_name, fallback to hotel_id
        hotel_name = None
        if runtime and hasattr(runtime, "context"):
            call_context = runtime.context
            if call_context and hasattr(call_context, "property") and call_context.property:
                hotel_name = call_context.property.property_name

        if not hotel_name:
            # Fallback: use hotel_id as key
            hotel_name = hotel_id
            logger.warning(f"[ROOMS_AND_RATES] No hotel_name found, using hotel_id as search_key: {hotel_id}")

        search_key = hotel_name
        logger.info(f"[ROOMS_AND_RATES]   Using search_key: '{search_key}'")

        # Create new active_searches entry
        search_meta = {
            "hotelId": hotel_id,
            "resolvedHotelName": hotel_name,
            "checkIn": search_params["checkIn"],
            "checkOut": search_params["checkOut"],
            "occupancy": search_params["occupancy"],
        }

        logger.info(f"[ROOMS_AND_RATES]   Created new active_searches entry: {search_meta}")
        logger.info(f"[ROOMS_AND_RATES] PATH 2 complete - search_key: '{search_key}'")

        clear_staging = True

    logger.info(f"[ROOMS_AND_RATES] Search params: {search_params}")

    # Call cache-worker (replaces hash generation, cache check, polling)
    try:
        search_result = await _start_rooms_search(hotel_id, search_params)

        # Cache HIT - return metadata
        if search_result["status"] == "cached":
            logger.info(
                f"[ROOMS_AND_RATES] Cache HIT! {search_result.get('roomCount', 0)} rooms available"
            )

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
                f"Room data cached. Ask user about room preferences (refundable/non-refundable, bed type), "
                f'then call query_vfs(destination="{search_key}:rooms:{hotel_id}") to retrieve complete room list.'
            )

            # Update active_searches with roomSearchId
            updated_search_meta = {
                **search_meta,
                "roomSearchId": search_result["roomSearchId"],
            }

        # Cache MISS - return polling status
        else:
            logger.info("[ROOMS_AND_RATES] Cache MISS - polling initiated")

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
                    f"Room search initiated. Ask user about room preferences (refundable/non-refundable, bed type) "
                    f'while search runs. Call query_vfs(destination="{search_key}:rooms:{hotel_id}") after user responds.'
                ),
            }

            # Update active_searches with roomSearchId
            updated_search_meta = {
                **search_meta,
                "roomSearchId": search_result["roomSearchId"],
            }

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

        # Clear search_params if we used it
        if clear_staging:
            update_dict["search_params"] = None
            logger.info("[ROOMS_AND_RATES] Cleared search_params after successful use")
        else:
            logger.info("[ROOMS_AND_RATES] search_params NOT cleared (not used)")

        logger.info("=" * 80)
        logger.info("[ROOMS_AND_RATES] Final state update:")
        logger.info(f"  search_key: '{search_key}'")
        logger.info(f"  roomSearchId: {search_result['roomSearchId']}")
        logger.info(f"  clear_staging: {clear_staging}")
        logger.info("=" * 80)

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
        logger.error(
            f"[ROOMS_AND_RATES] Cache-worker error: {type(e).__name__}: {str(e)}"
        )
        error_result = {
            "status": "error",
            "error": {
                "type": "room_search_error",
                "message": f"Failed to start room search: {str(e)}",
            },
        }
        return json.dumps(error_result, indent=2)

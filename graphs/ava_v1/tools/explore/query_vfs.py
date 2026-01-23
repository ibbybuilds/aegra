"""VFS query tool for querying search results from Redis JSON."""

import json
import logging
from typing import Annotated

import redis.asyncio as redis_async
from langchain.tools import InjectedToolArg, ToolRuntime, tool
from pydantic import BaseModel, Field

# Import redis_client
from ava_v1.shared_libraries.redis_client import get_redis_pool

logger = logging.getLogger(__name__)

# Maximum number of results that can be returned at once (for context preservation)
MAX_RESULTS_LIMIT = 5


class QueryVfsInput(BaseModel):
    """Input schema for querying virtual file system."""

    search_id: str | None = Field(
        default=None, description="Direct search ID to query results for"
    )
    destination: str | None = Field(
        default=None,
        description="Destination name or composite key (e.g., 'Miami' or 'Miami:JW Marriott')",
    )
    jsonpath: str | None = Field(
        default=None,
        description="JSONPath query for filtering results (e.g., '$.results[?(@.rating >= 4)]')",
    )
    sort_by: str | None = Field(
        default=None,
        description="Field name to sort results by (e.g., 'price', 'rating')",
    )
    sort_order: str = Field(
        default="asc",
        description="Sort order: 'asc' for ascending or 'desc' for descending",
    )
    limit: int | None = Field(
        default=None,
        description="Maximum number of results to return (capped at 5)",
        le=5,
    )


@tool(
    args_schema=QueryVfsInput,
    description="""PRIMARY tool for retrieving complete hotel/room search results from Redis cache.

CRITICAL - Token Placement:
- 'token' field is at TOP LEVEL of response (required for book_room)
- 'rate_key' is INSIDE each room object (required for book_room)
- NEVER fabricate these values - they must come from query_vfs response
- The firstRoom preview from start_room_search is INCOMPLETE (lacks token/rate_key) - CANNOT be used for booking

Usage Patterns:
- After start_hotel_search: query_vfs(destination="Miami") to retrieve hotel list
- After start_room_search: query_vfs(destination="Miami", sort_by="price") to retrieve room list with token
- After hotel_details: query_vfs(destination="details:hotel_123") to retrieve hotel details

Status Meanings:
- 'cached': Results ready and complete
- 'not_ready': Still searching (wait 2-3 seconds and retry)
- 'expired': Search data expired (run new search)
- 'partial': Incomplete results (some data available)

Validation Rules:
If response lacks token or rate_key:
1. Check 'status' field
2. If 'not_ready', wait and retry (max 3 times)
3. If 'expired', inform user and offer new search
4. NEVER proceed to book_room without valid token AND rate_key

Structure Examples:
Hotel search response: {"searchId": "abc", "results": [{"id": 123, "name": "Hotel", "price": 250}], "count": 5}
Room search response: {"searchId": "def", "token": "TOP_LEVEL_TOKEN", "results": [{"rate_key": "IN_ROOM", "hotel_id": 123, "price": 250}], "count": 3}""",
)
async def query_vfs(
    search_id: str | None = None,
    destination: str | None = None,
    jsonpath: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    limit: int | None = None,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> str:
    """Query and filter search results from Redis JSON cache.

    Primary tool for retrieving complete search results with token and rate_key required for booking.

    Args:
        search_id: Direct search ID from previous search response
        destination: Destination name or composite key (e.g., "Miami", "Miami:rooms:123", "details:456")
        jsonpath: JSONPath query for filtering results
        sort_by: Field name to sort by (e.g., "price", "rating")
        sort_order: Sort order - "asc" or "desc"
        limit: Maximum number of results to return (capped at 5)
        runtime: Injected tool runtime for accessing agent state

    Returns:
        JSON string with search results, including token for room searches
    """
    # Get active_searches from runtime state
    active_searches = runtime.state.get("active_searches", {}) if runtime else {}

    # Enforce maximum results limit for context preservation
    limit_capped = False
    original_limit = limit
    if limit is None or limit > MAX_RESULTS_LIMIT:
        limit_capped = limit is not None and limit > MAX_RESULTS_LIMIT
        limit = MAX_RESULTS_LIMIT

    logger.info("[QUERY_VFS] Querying VFS", extra={
        "search_id_present": bool(search_id),
        "destination": destination,
        "limit": limit,
        "limit_capped": limit_capped,
        "active_searches_count": len(active_searches)
    })
    logger.debug("[QUERY_VFS] Query details", extra={
        "search_id": search_id,
        "jsonpath": jsonpath,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "original_limit": original_limit
    })

    # Check if destination is a room search composite key first - resolve from context_stack
    if not search_id and destination and ":rooms:" in destination:
        # Format: "Miami:rooms:15335119"  # noqa: ERA001
        parts = destination.split(":rooms:")
        if len(parts) == 2:
            _, hotel_id = parts
            # Look in context_stack for matching hotel_id with room_search_id
            context_stack = runtime.state.get("context_stack", []) if runtime else []
            for ctx in reversed(context_stack):  # Search from most recent
                if ctx.get("hotel_id") == hotel_id and "room_search_id" in ctx:
                    search_id = ctx["room_search_id"]
                    break

            if not search_id:
                result = {
                    "error": "room_search_not_found",
                    "message": f"No room search found for hotel {hotel_id}. Run start_room_search(hotel_id, search_key) first to initiate room search.",
                }
                return json.dumps(result, indent=2)

    # Check if destination is a hotel details lookup - handle "details:" prefix
    if not search_id and destination and destination.startswith("details:"):
        # Format: "details:39615853"  # noqa: ERA001
        search_id = destination.split("details:")[1].strip()
        logger.info(
            f"[QUERY_VFS] Detected hotel details lookup, extracted search_id: {search_id}"
        )

    # Resolve search_id from regular destination (non-room search) if needed
    if not search_id and destination:
        label = destination.split(",")[0].strip()
        if label in active_searches:
            search_id = active_searches[label]["searchId"]
        else:
            # Provide helpful hints about available searches
            available = list(active_searches.keys())
            hint = ""
            if available:
                hint = f" Available searches: {', '.join(available)}. Use one of these keys or run start_hotel_search first."
            else:
                hint = " Run start_hotel_search first to create a search."

            result = {
                "error": "search_not_found",
                "message": f"No active search found for '{destination}'.{hint}",
            }
            return json.dumps(result, indent=2)

    # If still no search_id, check if we can infer or provide helpful error
    if not search_id:
        if len(active_searches) == 0:
            result = {
                "error": "missing_parameter",
                "message": "Must provide either search_id or destination. No active searches found. Run start_hotel_search first to create a search.",
            }
            return json.dumps(result, indent=2)
        elif len(active_searches) == 1:
            # Auto-use the only available search
            search_id = list(active_searches.values())[0]["searchId"]
        else:
            # Multiple searches exist - require specification
            available = ", ".join(active_searches.keys())
            result = {
                "error": "missing_parameter",
                "message": f"Must provide either search_id or destination. Available searches: {available}. Use one of these as the destination parameter.",
            }
            return json.dumps(result, indent=2)

    try:
        pool = get_redis_pool()
        redis_client = redis_async.Redis(connection_pool=pool)

        # Build Redis keys - detect room vs hotel vs details search
        redis_key_rooms = f"rooms:{search_id}"
        redis_key_search = f"search:{search_id}"
        redis_key_details = f"details:{search_id}"

        # Check which key exists
        exists_rooms = await redis_client.exists(redis_key_rooms)
        exists_search = await redis_client.exists(redis_key_search)
        exists_details = await redis_client.exists(redis_key_details)

        if exists_details:
            # Hotel details (no status key for details)
            redis_key = redis_key_details
            status_key = None
        elif exists_rooms:
            redis_key = redis_key_rooms
            status_key = f"rooms:{search_id}:status"
        elif exists_search:
            redis_key = redis_key_search
            status_key = f"search:{search_id}:status"
        else:
            # No data key exists - wait briefly and retry
            import asyncio

            logger.info(
                "[QUERY_VFS] No data found yet, waiting 3 seconds for polling service..."
            )
            await asyncio.sleep(3)
            logger.info("[QUERY_VFS] Retrying after wait...")

            # Retry: check again which key exists
            exists_rooms = await redis_client.exists(redis_key_rooms)
            exists_search = await redis_client.exists(redis_key_search)
            exists_details = await redis_client.exists(redis_key_details)

            if exists_details:
                redis_key = redis_key_details
                status_key = None
            elif exists_rooms:
                redis_key = redis_key_rooms
                status_key = f"rooms:{search_id}:status"
            elif exists_search:
                redis_key = redis_key_search
                status_key = f"search:{search_id}:status"
            else:
                # Still no data - check status keys to determine type
                status_key_rooms = f"rooms:{search_id}:status"
                status_key_search = f"search:{search_id}:status"

                exists_status_rooms = await redis_client.exists(status_key_rooms)

                if exists_status_rooms:
                    redis_key = redis_key_rooms
                    status_key = status_key_rooms
                else:
                    # Default to search pattern (might be polling or not found)
                    redis_key = redis_key_search
                    status_key = status_key_search

        # Check status first (if available) with retry logic
        # Skip status check for hotel details (no status key)
        partial_due_to_error = False
        error_message = None
        status_exists = await redis_client.exists(status_key) if status_key else False
        if status_exists:
            import asyncio

            # status_key is guaranteed to be str here (checked above)
            assert status_key is not None

            max_retries = 4  # Check up to 4 times
            retry_delay = 0.5  # 0.5 seconds between retries = 2 seconds max

            for attempt in range(max_retries):
                # redis.asyncio.Redis.hgetall is async, type stubs may not reflect this
                status_data = await redis_client.hgetall(status_key)  # type: ignore[misc]
                # Note: decode_responses=True in pool, so data is already decoded
                # But hgetall returns dict with potentially bytes keys/values depending on config
                # Ensure strings for safety
                if status_data and isinstance(next(iter(status_data.keys())), bytes):
                    status_data = {
                        k.decode(): v.decode() for k, v in status_data.items()
                    }

                state = status_data.get("state")

                # Check for error state
                if state == "error":
                    error_msg = status_data.get("error_msg", "Unknown error occurred")

                    # Check if partial data exists despite the error
                    data_exists = await redis_client.exists(redis_key)
                    if data_exists:
                        # Partial results available - continue to return them with error note
                        logger.info(
                            f"[QUERY_VFS] Error state but partial data exists for {search_id}"
                        )
                        partial_due_to_error = True
                        error_message = error_msg
                        break  # Exit retry loop, proceed to query partial data
                    else:
                        # No data available, return error
                        result = {
                            "status": "error",
                            "message": error_msg,
                            "searchId": search_id,
                        }
                        return json.dumps(result, indent=2)

                # Check if completed (data should be ready)
                if state == "complete" or state == "completed":
                    break  # Exit retry loop, proceed to query data

                # Check if still running
                if state == "running" or state == "inprogress":
                    # If not last attempt, wait and retry
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        # Re-check if data key exists now
                        data_exists = await redis_client.exists(redis_key)
                        if data_exists:
                            break  # Data is ready, exit retry loop
                        continue
                    else:
                        # Last attempt, return not_ready with expected count
                        result = {
                            "status": "not_ready",
                            "message": "Search results not ready yet. Still polling...",
                            "searchId": search_id,
                            "expectedHotelCount": status_data.get("expected_count"),
                            "lastUpdated": status_data.get("last_updated"),
                        }
                        return json.dumps(result, indent=2)

        # Check if data exists
        exists = await redis_client.exists(redis_key)
        if not exists:
            # Check if this is an expired search vs still polling
            # If neither status nor data key exists, search likely expired
            if not status_exists:
                # Check if search is tracked in active_searches
                search_found = any(
                    s["searchId"] == search_id for s in active_searches.values()
                )

                if search_found:
                    # Search was initiated but keys are gone - expired
                    result = {
                        "status": "expired",
                        "message": "Search results have expired. Please run a new hotel search.",
                        "searchId": search_id,
                    }
                    return json.dumps(result, indent=2)

            # Still polling or very recent search
            result = {
                "status": "not_ready",
                "message": "Search results not ready yet. Still polling...",
                "searchId": search_id,
            }
            return json.dumps(result, indent=2)

        # Default JSONPath: get all results
        if not jsonpath:
            jsonpath = "$"

        # Auto-rewrite common JSONPath mistakes based on Redis key type
        # Agent often confuses response structure (results) with Redis structure
        original_jsonpath = jsonpath
        jsonpath_rewritten = False

        if jsonpath and "$.results" in jsonpath:
            if redis_key.startswith("rooms:"):
                # rooms:* keys have structure: {"rooms": [...], "token": "..."}
                # Rewrite $.results[...] → $.rooms[...]
                jsonpath = jsonpath.replace("$.results", "$.rooms")
                jsonpath_rewritten = True
                logger.info(
                    f"[QUERY_VFS] Auto-rewriting JSONPath: '{original_jsonpath}' → '{jsonpath}'"
                )
            elif redis_key.startswith("search:"):
                # search:* keys are direct arrays: [{hotel1}, {hotel2}, ...]
                # Rewrite $.results[...] → $[...]
                jsonpath = jsonpath.replace("$.results", "$")
                jsonpath_rewritten = True
                logger.info(
                    f"[QUERY_VFS] Auto-rewriting JSONPath: '{original_jsonpath}' → '{jsonpath}'"
                )
            # details:* keys are single objects, no rewrite needed

        # Get data using Redis JSON with JSONPath
        result = await redis_client.execute_command("JSON.GET", redis_key, jsonpath)

        if result:
            results = json.loads(result)

            # Redis JSON returns array when using '$' path, unwrap it
            if isinstance(results, list) and len(results) > 0:
                results = results[0]

            # For room searches, extract token separately
            room_token = None
            if redis_key.startswith("rooms:"):
                # Fetch the top-level token from the full Redis data
                full_data_result = await redis_client.execute_command(
                    "JSON.GET", redis_key, "$"
                )
                if full_data_result:
                    full_data = json.loads(full_data_result)
                    if isinstance(full_data, list) and len(full_data) > 0:
                        full_data = full_data[0]

                    # full_data is now dict after unwrapping
                    if isinstance(full_data, dict):
                        room_token = full_data.get("token")

            # Apply sorting if specified (only for lists)
            if sort_by and isinstance(results, list):
                reverse = sort_order.lower() == "desc"
                try:
                    # Sort by the specified field
                    # Handle missing fields gracefully by using None as default
                    results = sorted(
                        results,
                        key=lambda x: x.get(sort_by)
                        if x.get(sort_by) is not None
                        else float("inf"),
                        reverse=reverse,
                    )
                except Exception as e:
                    # If sorting fails, log but continue with unsorted results
                    logger.warning(f"Warning: Failed to sort by {sort_by}: {e}")

            # Calculate total count before limiting
            # Handle different result types:
            # - Hotel searches: results is a list
            # - Room searches: results is a dict with "rooms" array
            if isinstance(results, list):
                total_count = len(results)
            elif isinstance(results, dict) and "rooms" in results:
                total_count = len(results.get("rooms", []))
            else:
                total_count = 1

            # Apply limit if specified
            if limit and isinstance(results, list):
                results = results[:limit]

            # Build response - include token separately for room searches
            response = {
                "searchId": search_id,
                "results": results,
                "count": total_count,  # Total available, not just returned
            }

            # Add token separately for room searches
            if room_token:
                response["token"] = room_token
                # Add hint for room searches
                # Room results are dict with "rooms" array
                if isinstance(results, dict) and isinstance(results.get("rooms"), list) and len(results.get("rooms", [])) > 0:
                    response["hint"] = (
                        "Room search complete. Present room options to user with prices and refund policies. When user selects a room, use this response to build the room object for book_room() - extract token from top level and rate_key from the room object."
                    )
                else:
                    response["hint"] = (
                        "No rooms available for this hotel. Suggest alternative hotels or different dates to the user."
                    )
            else:
                # Add hint for hotel searches
                if isinstance(results, list) and len(results) > 0:
                    response["hint"] = (
                        "Hotel search complete. Present hotel options to user with prices, ratings, and amenities. When user selects a hotel, call start_room_search(hotel_id, search_key) to check room availability."
                    )
                else:
                    response["hint"] = (
                        "No hotels found. Suggest adjusting search criteria (dates, location, budget) to the user."
                    )

            # Add warning if returning partial results due to error
            if partial_due_to_error:
                response["warning"] = (
                    f"Partial results returned due to error: {error_message}"
                )
                response["status"] = "partial"

            # Add hint if limit was capped
            if limit_capped:
                if "warning" in response:
                    response["warning"] += (
                        f" | Results limited to {MAX_RESULTS_LIMIT} for context preservation."
                    )
                else:
                    response["note"] = (
                        f"Results limited to {MAX_RESULTS_LIMIT} for context preservation. Query again with different filters to see more results."
                    )

            # Add note if JSONPath was auto-rewritten
            if jsonpath_rewritten:
                rewrite_msg = f"JSONPath was auto-corrected from '{original_jsonpath}' to '{jsonpath}'. "
                if redis_key.startswith("rooms:"):
                    rewrite_msg += (
                        "For room queries, use $.rooms[...] not $.results[...]."
                    )
                elif redis_key.startswith("search:"):
                    rewrite_msg += "For hotel queries, use $[...] not $.results[...] (direct array)."

                if "note" in response:
                    response["note"] += f" | {rewrite_msg}"
                else:
                    response["note"] = rewrite_msg

            # Log what we're returning
            logger.info(f"[QUERY_VFS] Returning {response['count']} results", extra={
                "count": response['count'],
                "has_room_token": bool(room_token),
                "results_preview_count": min(len(results) if isinstance(results, list) else 0, 2)
            })
            if isinstance(results, list) and len(results) > 0:
                logger.debug(f"[QUERY_VFS] Results preview", extra={
                    "first_result": results[0],
                    "second_result": results[1] if len(results) > 1 else None,
                    "room_token": room_token
                })

            return json.dumps(response, indent=2)
        else:
            logger.warning(
                f"[QUERY_VFS] No results found in Redis for search_id: {search_id}"
            )
            result = {"searchId": search_id, "results": [], "count": 0}
            return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"[QUERY_VFS] Query failed: {str(e)}", exc_info=True)
        result = {
            "error": "query_failed",
            "message": f"Failed to query results: {str(e)}",
            "searchId": search_id,
        }
        return json.dumps(result, indent=2)

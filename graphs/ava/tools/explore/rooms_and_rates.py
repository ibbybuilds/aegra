import httpx
import json
import os
import time
from typing import Annotated, Union, Dict, List, Any
from langchain.tools import tool, InjectedToolCallId, InjectedState
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from ava.utils.ranking.rank_rooms import rank_rooms
from ava.utils.jwt import get_auth_headers

def safe_get_state_value(state: dict, key: str, default=None):
    """Safely get a value from state, returning default if key doesn't exist"""
    try:
        return state.get(key, default)
    except (KeyError, AttributeError):
        return default

@tool(description="Get room details for a hotel. Auto-injects dates/occupancy/token from state when available from previous hotel search. Falls back to explicit parameters when needed.")
async def rooms_and_rates(
    hotelId: str,
    dates: dict = None,
    occupancy: dict = None,
    filters: dict = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    limit: int = 1,
    # State injection parameters (with safe access)
    state: Annotated[dict, InjectedState] = None,
) -> Union[Command, str]:
    """
    Get room details for a hotel. Auto-injects dates/occupancy/token from state when available.
    
    Args:
        hotelId: Hotel ID to fetch rooms for (required)
        dates: Check-in/check-out dates (optional, will use from state if not provided)
        occupancy: Guest occupancy details (optional, will use from state if not provided)
        filters: Room-specific filters to apply
        tool_call_id: Tool call ID for tracking
        limit: Maximum number of results to return (defaults to 1)
        state: Agent state (auto-injected, contains hotelParams and hotelToken if available)
    
    Returns:
        Command with ToolMessage containing rooms and rates
    """
    try:
        # Validate inputs
        if not hotelId or not hotelId.strip():
            raise ValueError("Hotel ID is required. Please provide the hotelId from the hotel search results.")
        
        # Safely extract state values
        hotelParams = safe_get_state_value(state, "hotelParams")
        hotelToken = safe_get_state_value(state, "hotelToken")
        
        # Extract dates and occupancy from explicit parameters or hotelParams
        if not dates and hotelParams and isinstance(hotelParams, dict):
            dates = hotelParams.get("dates")
        if not occupancy and hotelParams and isinstance(hotelParams, dict):
            occupancy = hotelParams.get("occupancy")
        
        # Determine which API endpoint to use based on available parameters
        use_cached_token = hotelToken and hotelToken.strip()
        
        # Validate that we have the required parameters
        if not use_cached_token and (not dates or not occupancy):
            error_msg = "Missing required parameters. Either provide explicit dates and occupancy, or ensure hotelParams is available in state from a previous hotel search."
            if hotelParams:
                error_msg += f" Current hotelParams keys: {list(hotelParams.keys())}"
            
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "error": error_msg,
                                "room": None,
                                "nextCursor": None
                            }, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
        
        if not use_cached_token:
            # Use direct API call (requires dates and occupancy)
            if not dates or not isinstance(dates, dict):
                raise ValueError("Dates are required when no cached token is available. Please provide dates in format: {'checkIn': 'YYYY-MM-DD', 'checkOut': 'YYYY-MM-DD'}")
            
            if not occupancy or not isinstance(occupancy, dict):
                raise ValueError("Occupancy is required when no cached token is available. Please provide occupancy in format: {'adults': int, 'children': int}")
        
        # Handle filters parameter - allow None or empty dict
        if filters is None:
            filters = {}
        elif not isinstance(filters, dict):
            raise ValueError("Filters must be a dictionary")
        
        # Allow empty filters - will be handled gracefully in ranking
        if not filters:
            filters = {}
        
        if not limit or limit < 1 or limit > 100:
            limit = 1
        
        # Set up endpoint and parameters based on token availability
        if use_cached_token:
            # Use cached token from previous hotel search (faster, consistent pricing)
            endpoint = f"/api/hotel/{hotelId}/roomsandrates/{hotelToken}"
        else:
            # Use direct API call (requires dates and occupancy)
            endpoint = f"/api/hotel/{hotelId}/roomsandrates"
            
            # Build request body in correct API format
            request_body = {
                "currency": "USD",
                "checkIn": dates.get("checkIn"),
                "checkOut": dates.get("checkOut"),
                "occupancy": {
                    "numOfAdults": occupancy.get("adults", 2)
                },
                "countryOfResidence": "US",
                "respondImages": False
            }
            
            # Add children if specified (childAges should be an array of ages)
            if occupancy.get("children", 0) > 0:
                # For now, use default age of 5 for each child
                # TODO: Allow specifying actual child ages if needed
                num_children = occupancy.get("children", 0)
                request_body["occupancy"]["childAges"] = [5] * num_children
            
            # Note: Filters and limit are not added to API request body - they're only used for ranking
            # The API request body should match the exact format specified
        
        # Get base URL from environment variable
        tt_baseurl = os.getenv("TT_BASEURL")
        
        if not tt_baseurl:
            raise ValueError("TT_BASEURL environment variable is required")
        
        # Make API request
        auth_headers = get_auth_headers()
        
        async with httpx.AsyncClient(http2=True) as client:
            if use_cached_token:
                # GET request with cached token
                results_resp = await client.get(
                    f"{tt_baseurl}{endpoint}",
                    headers=auth_headers
                )
            else:
                # POST request with dates/occupancy in correct API format
                results_resp = await client.post(
                    f"{tt_baseurl}{endpoint}",
                    headers=auth_headers,
                    json=request_body
                )
            
            results_resp.raise_for_status()
            
            # Get the response data
            results_data = results_resp.json()
            results_content = results_resp.content
        
        # Build params for ranking
        ranking_params = {
            "hotelId": hotelId,
            "token": hotelToken if use_cached_token else "",
            "filters": filters,
            "limit": limit
        }
        
        if not use_cached_token:
            ranking_params.update({
                "dates": dates,
                "occupancy": occupancy
            })
        
        # Rank rooms using the ranking utility
        ranked_results = rank_rooms(results_data, params=ranking_params)
        
        # Extract room for LLM response (single room object, not array)
        room = ranked_results.get("room")
        
        # Build response for LLM (consistent with hotels pattern)
        response = {
            "room": room,
            "nextCursor": ranked_results.get("nextCursor"),
            "token": ranked_results.get("meta", {}).get("provenance", {}).get("token"),
            "totalAvailable": len(ranked_results.get("vfsRooms", [])),
            "searchMethod": "cached_token" if use_cached_token else "direct_api"
        }
        
        # Extract searchKey for VFS filename and state management
        search_key = ranked_results.get("meta", {}).get("searchKey", f"rooms_{hotelId}_{int(time.time())}")
        vfs_filename = f"rooms_{search_key}.json"
        next_cursor = ranked_results.get("nextCursor", "")
        
        # Build room params for potential re-fetch
        room_params = {
            "hotelId": hotelId,
            "limit": limit
        }
        
        if use_cached_token:
            room_params["token"] = hotelToken
        else:
            room_params.update({
                "dates": dates,
                "occupancy": occupancy,
                "filters": filters
            })
        
        # Build metadata
        from ava.utils.ranking.policies import DEFAULT_TTLS
        room_meta = {
            "fetchedAt": int(time.time()),
            "ttlSec": DEFAULT_TTLS.get("rooms_and_rates", 600),
            "status": "complete"
        }
        
        # Return Command with room to LLM, full results to VFS, and state updates
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(response, indent=2),
                        tool_call_id=tool_call_id
                    )
                ],
                "files": {
                    vfs_filename: json.dumps(ranked_results, indent=2)
                },
                # State updates for VFS pagination
                "roomSearchKey": search_key,
                "roomCursor": next_cursor,
                "roomParams": room_params,
                "roomMeta": room_meta
            }
        )
        
    except Exception as e:
        # Enhanced error logging for debugging
        import traceback
        
        # Build detailed error information
        error_details = {
            "error": str(e) if str(e) else "Unknown error occurred",
            "error_type": type(e).__name__,
            "hotelId": hotelId,
            "use_cached_token": use_cached_token if 'use_cached_token' in locals() else "unknown",
            "has_hotelToken": bool(hotelToken),
            "has_hotelParams": bool(hotelParams),
            "endpoint": endpoint if 'endpoint' in locals() else "unknown",
            "traceback": traceback.format_exc()
        }
        
        # Add parameter details for debugging
        if hotelParams:
            error_details["hotelParams_keys"] = list(hotelParams.keys())
            if "dates" in hotelParams:
                error_details["dates"] = hotelParams["dates"]
            if "occupancy" in hotelParams:
                error_details["occupancy"] = hotelParams["occupancy"]
        
        error_response = {
            "error": f"Failed to fetch rooms and rates: {error_details['error']}",
            "room": None,
            "nextCursor": None
        }
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(error_response, indent=2),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
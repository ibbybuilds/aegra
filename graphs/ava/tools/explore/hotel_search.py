import httpx
import json
import asyncio
import random
import os
import time
from typing import Annotated, Union, Dict, List, Any
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from ava.utils.parsers import decode_hotels
from ava.utils.ranking import rank_hotels_typed, rank_hotels
from ava.utils.jwt import get_auth_headers

@tool(description="Search for hotels with coordinates, dates, occupancy, and filters.")
async def hotel_search(
    circular_region: dict,
    dates: dict,
    occupancy: dict,
    filters: dict = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    limit: int = 3,
) -> Union[Command, str]:
    """
    Search for hotels with coordinates, dates, occupancy, and optional filters.
    
    Args:
        circular_region: Circular region to search for hotels in ["centerLat": float, "centerLong": float, "radiusInKM": float]
        dates: Dates to search for hotels in ["checkIn": str, "checkOut": str]
        occupancy: Occupancy to search for hotels in ["adults": int, "childAges": list[int]]
        filters: Optional filters to apply to the search ["amenities": list[str], "starMin": int, "priceMax": int, "brands": list[str]] (defaults to empty dict)
        limit: Maximum number of results to return (defaults to 3)
        tool_call_id: Tool call ID for tracking
    
    Returns:
        Command with ToolMessage containing hotel search results
    """
    try:
        # Validate inputs
        if not circular_region:
            raise ValueError("Circular region cannot be empty")
        
        if not isinstance(circular_region, dict):
            raise ValueError("Circular region must be a dictionary")
        
        if not dates:
            raise ValueError("Dates cannot be empty")
        
        if not isinstance(dates, dict):
            raise ValueError("Dates must be a dictionary")
        
        if not occupancy:
            raise ValueError("Occupancy cannot be empty")
        
        if not isinstance(occupancy, dict):
            raise ValueError("Occupancy must be a dictionary")
        
        # Handle filters parameter - allow None or empty dict
        if filters is None:
            filters = {}
        elif not isinstance(filters, dict):
            raise ValueError("Filters must be a dictionary")
        
        # Allow empty filters - will be handled gracefully in ranking
        if not filters:
            filters = {}
        
        if limit < 1 or limit > 100:
            limit = 3
        
        # Build init request body (exactly as expected by the API)
        init_body = {
            "currency": "USD",
            "culture": "en-US",
            "checkIn": dates["checkIn"],
            "checkOut": dates["checkOut"],
            "occupancy": {
                "numOfAdults": occupancy["adults"]
            },
            "circularRegion": circular_region,
            "countryOfResidence": "US"
        }
        
        # Add children if present
        if "childAges" in occupancy and occupancy["childAges"]:
            init_body["occupancy"]["childAges"] = occupancy["childAges"]
        
        # Get base URLs from environment variables
        techspian_baseurl = os.getenv("TECHSPIAN_BASEURL")
        tt_baseurl = os.getenv("TT_BASEURL")
        
        if not techspian_baseurl:
            raise ValueError("TECHSPIAN_BASEURL environment variable is required")
        if not tt_baseurl:
            raise ValueError("TT_BASEURL environment variable is required")
        
        # Step 1: Initialize search and get token
        
        # Headers for init API
        init_headers = {
            "Accept-Encoding": "br, gzip",
            "accountId": "test-hotels-account",
            "channelId": "test-hotels-channel", 
            "correlationId": "test123"
        }
        
        async with httpx.AsyncClient(http2=True, headers=init_headers) as client:
            init_resp = await client.post(f"{techspian_baseurl}/api/hotel/availability/init", json=init_body)
            init_resp.raise_for_status()
            token_data = init_resp.json()
            token = token_data["token"]
        
        # Step 2: Poll results until complete (optimized for voice-to-voice latency)
        max_retries = 8
        base_delay = 0.5
        max_delay = 3.0
        
        # Store the last response for processing partial results
        last_results_data = None
        last_results_resp = None
        
        for attempt in range(max_retries):
            try:
                # Get auth headers for results API
                auth_headers = get_auth_headers()
                
                # Create new client for results API call
                async with httpx.AsyncClient(http2=True) as results_client:
                    # Make GET request to results endpoint
                    results_resp = await results_client.get(
                        f"{tt_baseurl}/api/hotel/availability/{token}/results",
                        headers=auth_headers
                    )
                    results_resp.raise_for_status()
                    
                    # Check if complete
                    results_data = results_resp.json()
                    status = results_data.get("status", "").lower()
                    
                    # Store the last response for potential partial processing
                    last_results_data = results_data
                    last_results_resp = results_resp
                    
                    if status == "complete":
                        # Process results immediately when complete
                        # Build params for ranking (include original search params)
                        ranking_params = {
                            "circularRegion": circular_region,
                            "dates": dates,
                            "occupancy": occupancy,
                            "filters": filters,
                            "limit": limit
                        }
                        
                        # Try typed decode first (fastest), fallback to dict decode if schema changed
                        try:
                            env = decode_hotels(results_resp.content)  # msgspec Envelope
                            res = rank_hotels_typed(env, params=ranking_params, source="hotel_search", top_k=limit)
                        except Exception as e:
                            # Fallback to dict mode if typed decode fails
                            import msgspec
                            payload = msgspec.json.decode(results_resp.content)  # dict/list
                            res = rank_hotels(payload, params=ranking_params, top_k=limit, source="hotel.results")
                        
                        # Format top slice response
                        top_slice_response = {
                            "hotels": res["hotels"],
                            "nextCursor": res["nextCursor"],
                            "token": res.get("meta", {}).get("provenance", {}).get("token")
                        }
                        
                        # Extract searchKey for VFS filename and state management
                        search_key = res.get("meta", {}).get("searchKey", "unknown")
                        vfs_filename = f"hotels_{search_key}.json"
                        token = res.get("meta", {}).get("provenance", {}).get("token", "")
                        next_cursor = res.get("nextCursor", "")
                        
                        # Build hotel params for potential re-fetch
                        hotel_params = {
                            "circularRegion": circular_region,
                            "dates": dates,
                            "occupancy": occupancy,
                            "filters": filters,
                            "limit": limit
                        }
                        
                        # Build metadata
                        from ava.utils.ranking.policies import DEFAULT_TTLS
                        hotel_meta = {
                            "fetchedAt": int(time.time()),
                            "ttlSec": DEFAULT_TTLS.get("hotel_search", 600),
                            "status": "complete"
                        }
                        
                        # Return Command with top slice to LLM, full results to VFS, and state updates
                        return Command(
                            update={
                                "messages": [
                                    ToolMessage(
                                        content=json.dumps(top_slice_response, indent=2),
                                        tool_call_id=tool_call_id
                                    )
                                ],
                                "files": {
                                    vfs_filename: json.dumps(res, indent=2)
                                },
                                # State updates for VFS pagination
                                "hotelSearchKey": search_key,
                                "hotelToken": token,
                                "hotelCursor": next_cursor,
                                "hotelParams": hotel_params,
                                "hotelMeta": hotel_meta
                            }
                        )
                
                # Skip the ranking logic for now - we'll add a simple completion check
                if status == "complete":
                    break  # Exit if we completed successfully
                elif status == "error":
                    raise Exception(f"Search failed with error status: {results_data}")
                else:
                    # Still processing, wait with exponential backoff + jitter
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        jitter = random.uniform(0.1, 0.3) * delay
                        await asyncio.sleep(delay + jitter)
                    else:
                        # For voice-to-voice, use partial results if available instead of failing
                        if "hotels" in results_data and results_data["hotels"]:
                            # Decode partial response and rank hotels
                            env = decode_hotels(results_resp.content)  # msgspec Envelope
                            
                            # Build params for ranking (include original search params)
                            ranking_params = {
                                "circularRegion": circular_region,
                                "dates": dates,
                                "occupancy": occupancy,
                                "filters": filters,
                                "limit": limit
                            }
                            
                            res = rank_hotels_typed(env, params=ranking_params, source="hotel_search", top_k=limit)
                            break
                        else:
                            raise Exception(f"Search timed out after {max_retries} attempts with no results")
                        
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and attempt < max_retries - 1:
                    # Token not ready yet, continue polling
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0.1, 0.3) * delay
                    await asyncio.sleep(delay + jitter)
                    continue
                else:
                    raise Exception(f"HTTP error during polling: {e}")
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    jitter = random.uniform(0.1, 0.3) * delay
                    await asyncio.sleep(delay + jitter)
                    continue
                else:
                    raise Exception(f"Failed to get results after {max_retries} attempts: {e}")
        
        # If we reach here, polling didn't complete but we should process whatever we got
        # Use the last response we got (which should have the most hotels)
        if last_results_data and last_results_data.get("hotels"):
            # Build params for ranking (include original search params)
            ranking_params = {
                "circularRegion": circular_region,
                "dates": dates,
                "occupancy": occupancy,
                "filters": filters,
                "limit": limit
            }
            
            # Try typed decode first (fastest), fallback to dict decode if schema changed
            try:
                env = decode_hotels(last_results_resp.content)  # msgspec Envelope
                res = rank_hotels_typed(env, params=ranking_params, source="hotel_search", top_k=limit)
            except Exception as e:
                # Fallback to dict mode if typed decode fails
                import msgspec
                payload = msgspec.json.decode(last_results_resp.content)  # dict/list
                res = rank_hotels(payload, params=ranking_params, top_k=limit, source="hotel.results")
            
            # Format top slice response
            top_slice_response = {
                "hotels": res["hotels"],
                "nextCursor": res["nextCursor"],
                "token": res.get("meta", {}).get("provenance", {}).get("token")
            }
            
            # Extract searchKey for VFS filename and state management
            search_key = res.get("meta", {}).get("searchKey", "unknown")
            vfs_filename = f"hotels_{search_key}.json"
            token = res.get("meta", {}).get("provenance", {}).get("token", "")
            next_cursor = res.get("nextCursor", "")
            
            # Build hotel params for potential re-fetch
            hotel_params = {
                "circularRegion": circular_region,
                "dates": dates,
                "occupancy": occupancy,
                "filters": filters,
                "limit": limit
            }
            
            # Build metadata
            from ava.utils.ranking.policies import DEFAULT_TTLS
            hotel_meta = {
                "fetchedAt": int(time.time()),
                "ttlSec": DEFAULT_TTLS.get("hotel_search", 600),
                "status": "complete"
            }
            
            # Return Command with top slice to LLM, full results to VFS, and state updates
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps(top_slice_response, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ],
                    "files": {
                        vfs_filename: json.dumps(res, indent=2)
                    },
                    # State updates for VFS pagination
                    "hotelSearchKey": search_key,
                    "hotelToken": token,
                    "hotelCursor": next_cursor,
                    "hotelParams": hotel_params,
                    "hotelMeta": hotel_meta
                }
            )
        else:
            raise Exception("Failed to get results after 8 attempts: No hotels found")
        
    except Exception as e:
        # Handle any errors gracefully
        error_response = {
            "error": str(e),
            "hotels": [],
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
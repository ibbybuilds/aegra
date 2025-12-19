"""Hotel details tool for fetching detailed property information."""

import json
import logging
import os
from typing import Annotated

import httpx
from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from ava_v1.shared_libraries.context_helpers import prepare_hotel_details_push

# Import redis_client
from ava_v1.shared_libraries.redis_client import (
    redis_get_json_compressed,
    redis_set_json_compressed,
)
from ava_v1.shared_libraries.redis_helpers import _filter_hotel_details

logger = logging.getLogger(__name__)


def _wrap_response(
    result: dict, hotel_id: str, runtime: ToolRuntime | None
) -> Command | str:
    """Wrap response in Command with context management or return JSON string.

    Args:
        result: Result dictionary
        hotel_id: Hotel ID
        runtime: Tool runtime

    Returns:
        Command with context update or JSON string
    """
    result_json = json.dumps(result, indent=2)

    if runtime is None:
        return result_json

    # Auto-manage context stack: push HotelDetails
    context_stack = runtime.state.get("context_stack", [])
    context_to_push, new_stack = prepare_hotel_details_push(hotel_id, context_stack)

    update_dict = {
        "messages": [
            ToolMessage(content=result_json, tool_call_id=runtime.tool_call_id)
        ]
    }

    if context_to_push:
        # Need to push - replace stack and append new context
        update_dict["context_stack"] = {"__replace__": new_stack + [context_to_push]}
        logger.info(
            f"[HOTEL_DETAILS] Pushing HotelDetails({hotel_id}) to context stack"
        )

    return Command(update=update_dict)


@tool(description="Retrieve detailed information about a specific hotel")
async def hotel_details(
    hotel_id: str,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Retrieve detailed information about a specific hotel.

    Fetches comprehensive property details including descriptions, facilities,
    policies, location, and reviews. Response is filtered to include only
    relevant fields for the agent.

    Args:
        hotel_id: Hotel ID from query_vfs results (the 'id' field)
        runtime: Injected tool runtime (unused, no state access needed)

    Returns:
        JSON string containing:
        - status: "success" or "error"
        - hotelId: str - The hotel ID
        - details: dict - Filtered hotel details (only if success)
        - cached: bool - Whether result was from cache (only if success)
        - error: dict - Error details (only if error)

    Example Success Response:
        {
            "status": "success",
            "hotelId": "39615853",
            "cached": False,
            "details": {
                "id": 39615853,
                "name": "Marriott Downtown Miami",
                "chainName": "Marriott",
                "brandName": "Marriott Hotels & Resorts",
                "starRating": 4,
                "propertyType": "Hotel",
                "geocode": {"lat": 25.7743, "long": -80.1937},
                "address": {...},
                "descriptions": [...],
                "facilities": [...],
                "policies": [...],
                "review": {"rating": 4, "count": 1250},
                "timezone": "America/New_York"
            }
        }

    Example Error Response:
        {
            "status": "error",
            "hotelId": "39615853",
            "error": {
                "type": "invalid_hotel_id" | "api_error" | "not_found" | "timeout" | "unexpected_error",
                "message": "..."
            }
        }
    """
    logger.info("=" * 80)
    logger.info("[HOTEL_DETAILS] Tool called with:")
    logger.info(f"  hotel_id: {hotel_id}")
    logger.info("=" * 80)

    # Validate hotel_id
    if not hotel_id or not isinstance(hotel_id, str) or not hotel_id.strip():
        result = {
            "status": "error",
            "error": {
                "type": "invalid_hotel_id",
                "message": "hotel_id must be a non-empty string",
            },
        }
        return _wrap_response(result, hotel_id, runtime)

    try:
        # Check Redis cache first
        redis_key = f"details:{hotel_id}"
        cached_details = await redis_get_json_compressed(redis_key)

        if cached_details is not None:
            result = {
                "status": "success",
                "hotelId": hotel_id,
                "details": cached_details,
                "cached": True,
            }
            return _wrap_response(result, hotel_id, runtime)

        # Cache miss - fetch from API
        base_url = os.getenv("HOTEL_DETAIL_API_URL", "http://54.198.17.253:6001")
        endpoint = f"{base_url}/api/hotelcontent/{hotel_id}/detail"

        # Make async GET request
        async with httpx.AsyncClient() as client:
            response = await client.get(endpoint, timeout=30.0)
            response.raise_for_status()
            raw_data = response.json()

        # Filter response to include only relevant fields
        filtered_data = _filter_hotel_details(raw_data)

        # Store in Redis cache with 1 hour TTL
        TTL_SECONDS = 3600  # 1 hour
        await redis_set_json_compressed(redis_key, filtered_data, TTL_SECONDS)

        result = {
            "status": "success",
            "hotelId": hotel_id,
            "details": filtered_data,
            "cached": False,
        }
        return _wrap_response(result, hotel_id, runtime)

    except httpx.HTTPStatusError as e:
        # Handle 404 (not found) specifically
        if e.response.status_code == 404:
            result = {
                "status": "error",
                "hotelId": hotel_id,
                "error": {
                    "type": "not_found",
                    "message": f"Hotel {hotel_id} not found",
                },
            }
            return _wrap_response(result, hotel_id, runtime)

        result = {
            "status": "error",
            "hotelId": hotel_id,
            "error": {
                "type": "api_error",
                "message": f"HTTP error {e.response.status_code}: {str(e)}",
            },
        }
        return _wrap_response(result, hotel_id, runtime)

    except httpx.TimeoutException:
        result = {
            "status": "error",
            "hotelId": hotel_id,
            "error": {
                "type": "timeout",
                "message": "Request to hotel details API timed out",
            },
        }
        return _wrap_response(result, hotel_id, runtime)

    except Exception as e:
        result = {
            "status": "error",
            "hotelId": hotel_id,
            "error": {
                "type": "unexpected_error",
                "message": f"Unexpected error: {str(e)}",
            },
        }
        return _wrap_response(result, hotel_id, runtime)

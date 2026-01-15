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

    Triggers cache-worker to cache hotel details. The agent must then call
    query_vfs to retrieve the actual data from Redis.

    Args:
        hotel_id: Hotel ID from query_vfs results (the 'id' field)
        runtime: Injected tool runtime for context management

    Returns:
        JSON string or Command with status metadata

    Example Success Response:
        {
            "status": "success",
            "hotelId": "39615853",
            "message": "Hotel details cached. Call query_vfs(destination=\"details:39615853\") to retrieve full details.",
            "cached": True
        }

    Example Error Response:
        {
            "status": "error",
            "hotelId": "39615853",
            "error": {
                "type": "hotel_not_found" | "api_error" | "unexpected_error",
                "message": "..."
            }
        }
    """
    logger.info("=" * 80)
    logger.info("[DEBUG] hotel_details() ENTRY POINT - Tool called")
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

    cache_worker_url = os.getenv("CACHE_WORKER_URL", "http://localhost:8080")
    endpoint = f"{cache_worker_url}/v1/search/details/{hotel_id}"

    logger.info(f"[DEBUG] CACHE_WORKER_URL: {cache_worker_url}")
    logger.info(f"[HOTEL_DETAILS] Calling cache-worker for hotel_id: {hotel_id}")

    try:
        logger.info(f"[DEBUG] Creating httpx.AsyncClient for hotel details")
        async with httpx.AsyncClient() as client:
            logger.info(f"[DEBUG] Sending GET request to {endpoint}")
            response = await client.get(endpoint, timeout=10.0)
            logger.info(f"[DEBUG] Received response with status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            logger.info(f"[DEBUG] Parsed response JSON successfully")

            logger.info(f"[HOTEL_DETAILS] Status: {data['status']}")

            result = {
                "status": "success",
                "hotelId": hotel_id,
                "message": f"Hotel details cached. Call query_vfs(destination=\"details:{hotel_id}\") to retrieve full details.",
                "cached": True
            }

            logger.info(f"[DEBUG] hotel_details() returning successfully")
            return _wrap_response(result, hotel_id, runtime)

    except httpx.HTTPStatusError as e:
        logger.error(f"[DEBUG] HTTPStatusError in hotel_details: {type(e).__name__}: {str(e)}")
        logger.error(f"[DEBUG] Response status: {e.response.status_code}, body: {e.response.text[:200]}")
        if e.response.status_code == 404:
            result = {
                "status": "error",
                "hotelId": hotel_id,
                "error": {
                    "type": "hotel_not_found",
                    "message": f"Hotel with ID '{hotel_id}' not found"
                }
            }
        else:
            result = {
                "status": "error",
                "hotelId": hotel_id,
                "error": {
                    "type": "api_error",
                    "message": f"Hotel details API error: {str(e)}"
                }
            }
        return _wrap_response(result, hotel_id, runtime)

    except Exception as e:
        logger.error(f"[DEBUG] Unexpected exception in hotel_details: {type(e).__name__}: {str(e)}")
        logger.error(f"[DEBUG] Exception traceback:", exc_info=True)
        result = {
            "status": "error",
            "hotelId": hotel_id,
            "error": {
                "type": "unexpected_error",
                "message": f"Unexpected error: {str(e)}"
            }
        }
        return _wrap_response(result, hotel_id, runtime)

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
from ava_v1.shared_libraries.lookup_id import lookup_id

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


@tool(description="Retrieve detailed information about a specific hotel by ID or name")
async def hotel_details(
    hotel_id: str | None = None,
    hotel_name: str | None = None,
    destination: str | None = None,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Retrieve detailed information about a specific hotel.

    Triggers cache-worker to cache hotel details. The agent must then call
    query_vfs to retrieve the actual data from Redis.

    Supports both hotel ID and hotel name lookups. If hotel_name is provided,
    it will be resolved to an ID via Pinecone search before fetching details.

    Args:
        hotel_id: Hotel ID from query_vfs results (the 'id' field). Required if hotel_name not provided.
        hotel_name: Hotel name for lookup (e.g., "JW Marriott"). Optional alternative to hotel_id.
        destination: Destination/city hint for name resolution (e.g., "Miami"). Required if hotel_name provided.
        runtime: Injected tool runtime for context management

    Returns:
        JSON string or Command with status metadata

    Example Success Response:
        {
            "status": "success",
            "hotelId": "39615853",
            "hotelName": "JW Marriott Miami",
            "message": "Hotel details cached. Call query_vfs(destination=\"details:39615853\") to retrieve full details.",
            "cached": True
        }

    Example Name Resolution Response (multiple matches):
        {
            "status": "clarification_needed",
            "hotels": [
                {"id": "123", "name": "JW Marriott Miami", "address": "..."},
                {"id": "456", "name": "JW Marriott Downtown Miami", "address": "..."}
            ],
            "message": "Found 2 hotels matching 'JW Marriott'."
        }

    Example Error Response:
        {
            "status": "error",
            "error": {
                "type": "hotel_not_found" | "api_error" | "name_lookup_failed" | "unexpected_error",
                "message": "..."
            }
        }
    """
    logger.info("=" * 80)
    logger.info("[DEBUG] hotel_details() ENTRY POINT - Tool called")
    logger.info("[HOTEL_DETAILS] Tool called with:")
    logger.info(f"  hotel_id: {hotel_id}")
    logger.info(f"  hotel_name: {hotel_name}")
    logger.info(f"  destination: {destination}")
    logger.info("=" * 80)

    # Validate that either hotel_id or hotel_name is provided
    if not hotel_id and not hotel_name:
        result = {
            "status": "error",
            "error": {
                "type": "invalid_input",
                "message": "Either hotel_id or hotel_name must be provided",
            },
        }
        return _wrap_response(result, "", runtime)

    # If hotel_name is provided, resolve it first
    resolved_hotel_id = hotel_id
    resolved_hotel_name = None

    if hotel_name and not hotel_id:
        logger.info(f"[HOTEL_DETAILS] Resolving hotel name: {hotel_name}")

        # Destination is required for name lookup
        if not destination:
            result = {
                "status": "error",
                "error": {
                    "type": "invalid_input",
                    "message": "destination parameter is required when using hotel_name",
                },
            }
            return _wrap_response(result, "", runtime)

        # Extract city hint from destination
        city_hint = destination.split(",")[0].strip()

        # Call lookup_id to resolve hotel name
        lookup_result = await lookup_id(query=hotel_name, city_hint=city_hint)

        # Handle lookup errors
        if "error" in lookup_result:
            result = {
                "status": "error",
                "error": {
                    "type": "name_lookup_failed",
                    "message": lookup_result.get(
                        "message", "Failed to lookup hotel by name"
                    ),
                },
            }
            return _wrap_response(result, "", runtime)

        # Check confidence level
        confidence = lookup_result.get("confidence")

        if confidence == "high":
            # Single high-confidence match
            hotels = lookup_result.get("hotels", [])
            if hotels and len(hotels) > 0:
                resolved_hotel_id = hotels[0].get("id")
                resolved_hotel_name = hotels[0].get("name")
                logger.info(
                    f"[HOTEL_DETAILS] Resolved '{hotel_name}' to hotel_id={resolved_hotel_id} ({resolved_hotel_name})"
                )
            else:
                result = {
                    "status": "error",
                    "error": {
                        "type": "name_lookup_failed",
                        "message": f"No hotels found matching '{hotel_name}'",
                    },
                }
                return _wrap_response(result, "", runtime)

        elif confidence == "low":
            # Multiple matches - return for clarification
            hotels = lookup_result.get("hotels", [])
            result = {
                "status": "clarification_needed",
                "hotels": hotels,
                "message": f"Found {len(hotels)} hotels matching '{hotel_name}'. Please specify which one:",
            }
            return _wrap_response(result, "", runtime)

        else:
            result = {
                "status": "error",
                "error": {
                    "type": "name_lookup_failed",
                    "message": f"Unexpected confidence level: {confidence}",
                },
            }
            return _wrap_response(result, "", runtime)

    # Validate resolved hotel_id
    if (
        not resolved_hotel_id
        or not isinstance(resolved_hotel_id, str)
        or not resolved_hotel_id.strip()
    ):
        result = {
            "status": "error",
            "error": {
                "type": "invalid_hotel_id",
                "message": "hotel_id must be a non-empty string",
            },
        }
        return _wrap_response(result, resolved_hotel_id or "", runtime)

    cache_worker_url = os.getenv("CACHE_WORKER_URL", "http://localhost:8080")
    endpoint = f"{cache_worker_url}/v1/search/details/{resolved_hotel_id}"

    logger.info(f"[DEBUG] CACHE_WORKER_URL: {cache_worker_url}")
    logger.info(
        f"[HOTEL_DETAILS] Calling cache-worker for hotel_id: {resolved_hotel_id}"
    )

    try:
        logger.info(f"[DEBUG] Creating httpx.AsyncClient for hotel details")
        async with httpx.AsyncClient() as client:
            logger.info(f"[DEBUG] Sending GET request to {endpoint}")
            response = await client.get(endpoint, timeout=10.0)
            logger.info(
                f"[DEBUG] Received response with status: {response.status_code}"
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"[DEBUG] Parsed response JSON successfully")

            logger.info(f"[HOTEL_DETAILS] Status: {data['status']}")

            result = {
                "status": "success",
                "hotelId": resolved_hotel_id,
                "message": f'Hotel details cached. Call query_vfs(destination="details:{resolved_hotel_id}") to retrieve full details.',
                "cached": True,
            }

            # Include hotel name if it was resolved
            if resolved_hotel_name:
                result["hotelName"] = resolved_hotel_name

            logger.info(f"[DEBUG] hotel_details() returning successfully")
            return _wrap_response(result, resolved_hotel_id, runtime)

    except httpx.HTTPStatusError as e:
        logger.error(
            f"[DEBUG] HTTPStatusError in hotel_details: {type(e).__name__}: {str(e)}"
        )
        logger.error(
            f"[DEBUG] Response status: {e.response.status_code}, body: {e.response.text[:200]}"
        )
        if e.response.status_code == 404:
            result = {
                "status": "error",
                "hotelId": resolved_hotel_id,
                "error": {
                    "type": "hotel_not_found",
                    "message": f"Hotel with ID '{resolved_hotel_id}' not found",
                },
            }
        else:
            result = {
                "status": "error",
                "hotelId": resolved_hotel_id,
                "error": {
                    "type": "api_error",
                    "message": f"Hotel details API error: {str(e)}",
                },
            }
        return _wrap_response(result, resolved_hotel_id, runtime)

    except Exception as e:
        logger.error(
            f"[DEBUG] Unexpected exception in hotel_details: {type(e).__name__}: {str(e)}"
        )
        logger.error(f"[DEBUG] Exception traceback:", exc_info=True)
        result = {
            "status": "error",
            "hotelId": resolved_hotel_id,
            "error": {
                "type": "unexpected_error",
                "message": f"Unexpected error: {str(e)}",
            },
        }
        return _wrap_response(result, resolved_hotel_id, runtime)

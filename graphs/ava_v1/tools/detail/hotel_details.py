"""Hotel details tool for fetching detailed property information."""

import json
import logging
import os
from typing import Annotated

import httpx
from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

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


class HotelDetailsInput(BaseModel):
    """Input schema for retrieving hotel details."""

    hotel_id: str | None = Field(
        default=None,
        description="Hotel ID from query_vfs results (the 'id' field). Required if hotel_name not provided.",
    )
    hotel_name: str | None = Field(
        default=None,
        description="Hotel name for lookup (e.g., 'JW Marriott'). Optional alternative to hotel_id.",
    )
    destination: str | None = Field(
        default=None,
        description="Destination/city hint for name resolution (e.g., 'Miami'). Required if hotel_name provided.",
    )


@tool(
    args_schema=HotelDetailsInput,
    description="""Retrieve detailed information about a specific hotel (two-step process).

TWO-STEP PROCESS:
Step 1: This tool triggers cache-worker to cache hotel details in Redis
Step 2: Call query_vfs(destination="details:{hotel_id}") to retrieve the cached data

This tool returns immediately with status. You MUST call query_vfs after to get the actual hotel details (amenities, photos, description, reviews, policies, etc.).

Supports Both Lookups:
- By hotel_id: Direct lookup using ID from query_vfs results (e.g., hotel_id="39615853")
- By hotel_name: Requires destination hint (e.g., hotel_name="JW Marriott", destination="Miami")

Name Resolution:
If hotel_name provided, tool resolves it via Pinecone search before caching.
- High confidence (single match): Returns success with hotelId for next step
- Low confidence (multiple matches): Returns clarification_needed with hotel list

Next Action:
After success response, always call query_vfs(destination="details:{hotelId}") to retrieve full details.

Example Flow:
1. hotel_details(hotel_id="39615853")
2. Response: {"status": "success", "hotelId": "39615853", "message": "...call query_vfs..."}
3. query_vfs(destination="details:39615853")
4. Response: Full hotel details with amenities, photos, policies, etc.""",
)
async def hotel_details(
    hotel_id: str | None = None,
    hotel_name: str | None = None,
    destination: str | None = None,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Retrieve detailed hotel information in two steps: cache trigger + query_vfs retrieval.

    Triggers cache-worker to cache hotel details, then requires query_vfs call to retrieve data.

    Args:
        hotel_id: Hotel ID from query_vfs results. Required if hotel_name not provided.
        hotel_name: Hotel name for lookup (e.g., "JW Marriott"). Optional alternative to hotel_id.
        destination: City hint for name resolution (e.g., "Miami"). Required if hotel_name provided.
        runtime: Injected tool runtime for context management

    Returns:
        JSON string or Command with status (always call query_vfs after for actual details)
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
        logger.info("[DEBUG] Creating httpx.AsyncClient for hotel details")
        async with httpx.AsyncClient() as client:
            logger.info(f"[DEBUG] Sending GET request to {endpoint}")
            response = await client.get(endpoint, timeout=10.0)
            logger.info(
                f"[DEBUG] Received response with status: {response.status_code}"
            )
            response.raise_for_status()
            data = response.json()
            logger.info("[DEBUG] Parsed response JSON successfully")

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

            logger.info("[DEBUG] hotel_details() returning successfully")
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
        logger.error("[DEBUG] Exception traceback:", exc_info=True)
        result = {
            "status": "error",
            "hotelId": resolved_hotel_id,
            "error": {
                "type": "unexpected_error",
                "message": f"Unexpected error: {str(e)}",
            },
        }
        return _wrap_response(result, resolved_hotel_id, runtime)

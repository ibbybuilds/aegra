"""Tool for updating search parameters in staging area."""

import json
import logging
from datetime import datetime
from typing import Annotated, Literal

from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


def _validate_date_format(date_str: str) -> bool:
    """Validate date is in YYYY-MM-DD format.

    Args:
        date_str: Date string to validate

    Returns:
        True if valid format, False otherwise
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _validate_date_range(check_in: str, check_out: str) -> bool:
    """Validate that checkOut is after checkIn.

    Args:
        check_in: Check-in date in YYYY-MM-DD format
        check_out: Check-out date in YYYY-MM-DD format

    Returns:
        True if check_out > check_in, False otherwise
    """
    try:
        check_in_date = datetime.strptime(check_in, "%Y-%m-%d")
        check_out_date = datetime.strptime(check_out, "%Y-%m-%d")
        return check_out_date > check_in_date
    except ValueError:
        return False


@tool(
    description=(
        "Update search parameters (dates, occupancy) one field at a time. "
        "Use this immediately after user confirms each field value. "
        "These params are staged temporarily and will be copied to active_searches "
        "when hotel_search or room_search is called. "
        "REQUIRED: checkIn, checkOut, numOfAdults. "
        "OPTIONAL: numOfRooms (default: 1), childAges (default: [])."
    )
)
def update_search_params(
    field: Literal[
        "checkIn",
        "checkOut",
        "numOfAdults",
        "numOfRooms",
        "childAges",
    ],
    value: str | int | list[int],
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Update search_params state with validated field value.

    USAGE PATTERN:
        Call this tool immediately after user confirms each search parameter.
        This updates the staging area incrementally.

    FIELD VALIDATION:
        - checkIn: Must be YYYY-MM-DD format
        - checkOut: Must be YYYY-MM-DD format and after checkIn
        - numOfAdults: Must be >= 1
        - numOfRooms: Must be >= 1
        - childAges: Must be list of integers (ages 0-17)

    EXAMPLES:
        User: "I want to check in on February 1st"
        Agent: update_search_params(field="checkIn", value="2026-02-01")

        User: "2 adults"
        Agent: update_search_params(field="numOfAdults", value=2)

        User: "with a 5 year old child"
        Agent: update_search_params(field="childAges", value=[5])

    Args:
        field: The field name to update
        value: The value to set (type depends on field)
        runtime: Injected tool runtime for accessing agent state

    Returns:
        Command with state update on success, or error string on failure
    """
    logger.info("=" * 80)
    logger.info("[UPDATE_SEARCH_PARAMS] Tool called with:")
    logger.info(f"  field: {field}")
    logger.info(f"  value: {value}")

    # Get current search_params (may be None or empty dict)
    current_params = runtime.state.get("search_params", {}) if runtime else {}
    if current_params is None:
        current_params = {}

    logger.info(f"  current search_params BEFORE update: {current_params}")
    logger.info("=" * 80)

    # Validate field-specific constraints
    if field == "checkIn":
        if not isinstance(value, str):
            return json.dumps({
                "error": "invalid_type",
                "message": "checkIn must be a string in YYYY-MM-DD format"
            }, indent=2)
        if not _validate_date_format(value):
            return json.dumps({
                "error": "invalid_date_format",
                "message": f"checkIn must be in YYYY-MM-DD format, got: {value}"
            }, indent=2)
        # If checkOut exists, validate date range
        if "checkOut" in current_params:
            if not _validate_date_range(value, current_params["checkOut"]):
                return json.dumps({
                    "error": "invalid_date_range",
                    "message": f"checkIn ({value}) must be before checkOut ({current_params['checkOut']})"
                }, indent=2)

    elif field == "checkOut":
        if not isinstance(value, str):
            return json.dumps({
                "error": "invalid_type",
                "message": "checkOut must be a string in YYYY-MM-DD format"
            }, indent=2)
        if not _validate_date_format(value):
            return json.dumps({
                "error": "invalid_date_format",
                "message": f"checkOut must be in YYYY-MM-DD format, got: {value}"
            }, indent=2)
        # If checkIn exists, validate date range
        if "checkIn" in current_params:
            if not _validate_date_range(current_params["checkIn"], value):
                return json.dumps({
                    "error": "invalid_date_range",
                    "message": f"checkOut ({value}) must be after checkIn ({current_params['checkIn']})"
                }, indent=2)

    elif field == "numOfAdults":
        if not isinstance(value, int):
            return json.dumps({
                "error": "invalid_type",
                "message": "numOfAdults must be an integer"
            }, indent=2)
        if value < 1:
            return json.dumps({
                "error": "invalid_value",
                "message": "numOfAdults must be at least 1"
            }, indent=2)

    elif field == "numOfRooms":
        if not isinstance(value, int):
            return json.dumps({
                "error": "invalid_type",
                "message": "numOfRooms must be an integer"
            }, indent=2)
        if value < 1:
            return json.dumps({
                "error": "invalid_value",
                "message": "numOfRooms must be at least 1"
            }, indent=2)

    elif field == "childAges":
        if not isinstance(value, list):
            return json.dumps({
                "error": "invalid_type",
                "message": "childAges must be a list of integers"
            }, indent=2)
        if not all(isinstance(age, int) and 0 <= age <= 17 for age in value):
            return json.dumps({
                "error": "invalid_value",
                "message": "childAges must contain integers between 0 and 17"
            }, indent=2)

    # Success - update search_params
    updated_params = {**current_params, field: value}
    success_result = {
        "status": "success",
        "message": f"Updated search_params.{field} = {value}",
        "search_params": updated_params
    }

    logger.info("=" * 80)
    logger.info(f"[UPDATE_SEARCH_PARAMS] Successfully updated {field}")
    logger.info(f"  search_params AFTER update (merged view): {updated_params}")
    logger.info(f"  Returning Command update: {{{field}: {value}}}")
    logger.info("=" * 80)

    if runtime is None:
        return json.dumps(success_result, indent=2)

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(success_result, indent=2),
                    tool_call_id=runtime.tool_call_id,
                )
            ],
            "search_params": {field: value}  # Will be merged by merge_dicts reducer
        }
    )

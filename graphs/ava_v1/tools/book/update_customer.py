"""Tool for updating verified customer details in the agent state."""

import json
import logging
import re
from typing import Annotated, Literal

from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


@tool(
    description="Update verified customer details (first name, last name, email) in the system state"
)
def update_customer_details(
    field: Literal["first_name", "last_name", "email"],
    value: str,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Update a specific field in the customer's verified details.

    Use this tool immediately after the user confirms the spelling of their
    first name, last name, or email address during the verification phase.

    Args:
        field: The field to update ("first_name", "last_name", or "email")
        value: The verified value (e.g., "John", "Smith", "john@example.com")
        runtime: Injected runtime for state updates

    Returns:
        Confirmation message
    """
    logger.info(f"[UPDATE_CUSTOMER] Updating {field} = {value}")

    # Basic validation
    if not value or not value.strip():
        return json.dumps({"status": "error", "message": "Value cannot be empty"})

    if field == "email":
        # Simple regex for email validation
        email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_pattern, value.strip()):
            return json.dumps({
                "status": "error",
                "message": f"Invalid email format: {value}. Please verify spelling.",
            })

    # Prepare state update
    update = {field: value.strip()}
    
    logger.info(f"[UPDATE_CUSTOMER] State update committed for {field}: {update}")

    if runtime is None:
        return json.dumps({"status": "success", "updated": update})

    return Command(
        update={
            "customer_details": update,
            "messages": [
                ToolMessage(
                    content=json.dumps(
                        {"status": "success", "field": field, "value": value}
                    ),
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )

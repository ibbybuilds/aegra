"""Tool for updating verified customer details in the agent state."""

import json
import logging
import re
from typing import Annotated, Literal

from langchain.tools import InjectedToolArg, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UpdateCustomerDetailsInput(BaseModel):
    """Input schema for updating customer details."""

    field: Literal["first_name", "last_name", "email"] = Field(
        description="Field to update: 'first_name', 'last_name', or 'email'"
    )
    value: str = Field(description="Verified value for the field")


@tool(
    args_schema=UpdateCustomerDetailsInput,
    description="CRITICAL: Save verified customer details (first_name, last_name, or email) IMMEDIATELY after spelling confirmation. Call this tool RIGHT AFTER the user confirms each field - do NOT wait to collect all three fields. Save first_name, THEN last_name, THEN email in separate sequential calls.",
)
async def update_customer_details(
    field: Literal["first_name", "last_name", "email"],
    value: str,
    runtime: Annotated[ToolRuntime | None, InjectedToolArg()] = None,
) -> Command | str:
    """Save verified customer detail to persistent state immediately after user confirms spelling.

    Args:
        field: Field to update ("first_name", "last_name", or "email")
        value: Verified value (e.g., "John", "Smith", "john@example.com")
        runtime: Injected runtime for state updates

    Returns:
        Command with state update or JSON string with confirmation
    """
    logger.info(f"[UPDATE_CUSTOMER] Updating {field} = {value}")

    # Basic validation
    if not value or not value.strip():
        return json.dumps({"status": "error", "message": "Value cannot be empty"})

    # Validate first_name and last_name: only letters, spaces, hyphens, apostrophes
    if field in ["first_name", "last_name"]:
        # Allow: letters (a-z, A-Z), spaces, hyphens (-), apostrophes (')
        # Reject: numbers (0-9), special characters (!@#$%^&*, etc.)
        name_pattern = r"^[a-zA-Z\s\-']+$"
        if not re.match(name_pattern, value.strip()):
            field_display = field.replace("_", " ")
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Invalid {field_display}: contains numbers or special characters. Only letters, spaces, hyphens, and apostrophes are allowed. Please ask the customer to spell their name again.",
                }
            )

    if field == "email":
        # Simple regex for email validation
        email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_pattern, value.strip()):
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Invalid email format: {value}. Please verify spelling.",
                }
            )

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

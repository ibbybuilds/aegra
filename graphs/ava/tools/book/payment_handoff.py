import json
from typing import Annotated, Union, Dict, Any
from langchain_core.tools import tool, InjectedToolCallId
from langchain.tools import InjectedState
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer


def safe_get_state_value(state: dict, key: str, default=None):
    """Safely get a value from state, returning default if key doesn't exist"""
    try:
        return state.get(key, default)
    except (KeyError, AttributeError):
        return default


@tool(description="Transfers the call to a secure payment processing line where the customer can complete their payment for hotel booking. This tool initiates a handoff from the AI conversation to a dedicated payment processing system, ensuring secure payment data handling and clean separation from the conversation flow.")
def payment_handoff(
    summary: str,
    token: str,
    rateId: str,
    billingContact: Dict[str, str],
    price: float,
    hotelId: str,
    currency: str = "USD",
    description: str = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    state: Annotated[dict, InjectedState] = None,
) -> Union[Command, str]:
    """
    Transfers the call to a secure payment processing line for hotel booking payment.
    
    Args:
        summary: A summary of the call and reason for payment handoff
        token: Booking token/confirmation token
        rateId: Rate ID for the booking
        billingContact: Customer billing information containing firstName, lastName, and email
        price: The payment amount to be processed
        hotelId: Hotel identifier
        currency: The currency code for the payment (default: "USD")
        description: Description of what the payment is for
        tool_call_id: Tool call ID for tracking
        state: Agent state (auto-injected, required - contains roomParams or hotelParams with dates)
    
    Returns:
        Command with ToolMessage containing payment handoff response
    """
    try:
        # Validation
        if not summary or not summary.strip():
            raise ValueError("Summary is required for payment handoff")
        
        if not token or not token.strip():
            raise ValueError("Token is required for payment handoff")
        
        if not rateId or not rateId.strip():
            raise ValueError("Rate ID is required for payment handoff")
        
        if not billingContact or not isinstance(billingContact, dict):
            raise ValueError("Billing contact information is required for payment handoff")

        # Extract dates from state (required)
        # Prefer roomParams (since payment happens after room selection), fallback to hotelParams
        roomParams = safe_get_state_value(state, "roomParams")
        hotelParams = safe_get_state_value(state, "hotelParams")
        
        dates = None
        # Prefer dates from roomParams
        if roomParams and isinstance(roomParams, dict):
            dates = roomParams.get("dates")
        # Fallback to hotelParams if not in roomParams
        if not dates and hotelParams and isinstance(hotelParams, dict):
            dates = hotelParams.get("dates")
        
        # Extract checkIn and checkOut from dates dict
        if not dates or not isinstance(dates, dict):
            raise ValueError("Dates are required for payment handoff. Ensure roomParams or hotelParams with dates are available in state.")
        
        final_checkIn = dates.get("checkIn")
        final_checkOut = dates.get("checkOut")
        
        # Validate dates are present and in correct format
        if not final_checkIn or not isinstance(final_checkIn, str) or not final_checkIn.strip():
            raise ValueError("checkIn date is required and must be a non-empty string in YYYY-MM-DD format")
        if not final_checkOut or not isinstance(final_checkOut, str) or not final_checkOut.strip():
            raise ValueError("checkOut date is required and must be a non-empty string in YYYY-MM-DD format")

        # Custom stream writer for payment handoff
        stream_writer = get_stream_writer()
        stream_data = {
            "type": "payment-handoff",
            "summary": summary,
            "token": token,
            "rateId": rateId,
            "billingContact": billingContact,
            "price": price,
            "hotelId": hotelId,
            "currency": currency,
            "description": description,
            "checkIn": final_checkIn,
            "checkOut": final_checkOut,
        }
        stream_writer(stream_data)
        
        # Validate billing contact structure
        required_billing_fields = ["firstName", "lastName", "email"]
        for field in required_billing_fields:
            if field not in billingContact:
                raise ValueError(f"Billing contact {field} is required for payment handoff")
            
            field_value = billingContact[field]
            if not field_value or not isinstance(field_value, str) or not field_value.strip():
                raise ValueError(f"Billing contact {field} must be a non-empty string")
        
        if not isinstance(price, (int, float)) or price <= 0:
            raise ValueError("Valid payment amount is required for payment handoff")
        
        if not hotelId or not hotelId.strip():
            raise ValueError("Hotel ID is required for payment handoff")
        
        # Set defaults
        if not currency:
            currency = "USD"
        
        if not description:
            description = "Hotel booking payment"
        
        # Build payment data
        payment_data = {
            "token": token,
            "rateId": rateId,
            "price": float(price),
            "hotelId": hotelId,
            "currency": currency,
            "description": description,
            "checkIn": final_checkIn,
            "checkOut": final_checkOut,
        }
        
        # Build handoff data for outgoing message
        handoff_data = {
            "reasonCode": "payment-handoff",
            "reason": summary,
            "paymentData": payment_data,
            "billingContact": billingContact
        }
        
        # Build success response
        response = {
            "success": True,
            "message": f"Payment handoff initiated for {currency} {price:.2f}",
            "summary": summary,
            "paymentData": payment_data,
            "outgoingMessage": {
                "type": "end",
                "handoffData": json.dumps(handoff_data)
            }
        }
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(response, indent=2),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
        
    except Exception as e:
        # Build error response
        error_response = {
            "success": False,
            "message": str(e),
            "summary": summary if summary else "Customer wants to book hotel"
        }
        
        # Include dates in error response if available
        try:
            if 'final_checkIn' in locals() and final_checkIn:
                error_response["checkIn"] = final_checkIn
            if 'final_checkOut' in locals() and final_checkOut:
                error_response["checkOut"] = final_checkOut
        except:
            pass  # Ignore errors when trying to include dates
        
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

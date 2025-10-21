import httpx
import json
import os
from typing import Annotated, Union, Any, Optional
from langchain.tools import InjectedState
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from ava.utils.jwt import get_auth_headers

def safe_get_state_value(state: dict, key: str, default=None):
    """Safely get a value from state, returning default if key doesn't exist"""
    try:
        return state.get(key, default)
    except (KeyError, AttributeError):
        return default

def _sum_taxes(taxes_field: Any) -> float:
    """
    Support list-of-objects [{'amount': ...}, ...] or numeric or None.
    """
    if taxes_field is None:
        return 0.0
    if isinstance(taxes_field, (int, float)):
        return float(taxes_field)
    if isinstance(taxes_field, list):
        total = 0.0
        for t in taxes_field:
            try:
                amt = t.get("amount")
                if isinstance(amt, (int, float)):
                    total += float(amt)
            except Exception:
                continue
        return total
    return 0.0

def _compute_est_all_in(
    published: Optional[float],
    total: Optional[float],
    base: Optional[float],
    taxes_any: Any,
    fee: Optional[float],
) -> Optional[float]:
    """
    estAllInPrice = parity + ourServiceFee + taxes_if_needed
      - publishedRate (parity) is pre-tax -> add taxes + fee
      - totalRate is usually tax-inclusive -> add fee only
      - baseRate is pre-tax -> add taxes + fee
    """
    fee_f = float(fee) if isinstance(fee, (int, float)) else 0.0
    taxes_f = _sum_taxes(taxes_any)

    if isinstance(published, (int, float)) and published > 0:
        return float(published) + fee_f + taxes_f
    if isinstance(total, (int, float)) and total > 0:
        return float(total) + fee_f
    if isinstance(base, (int, float)) and base > 0:
        return float(base) + fee_f + taxes_f
    return None

def _extract_additional_charges(additional_charges: Any) -> float:
    """
    Sum up additional charges like resort fees.
    """
    if not isinstance(additional_charges, list):
        return 0.0
    
    total = 0.0
    for charge in additional_charges:
        if isinstance(charge, dict):
            amount = charge.get("amount")
            if isinstance(amount, (int, float)):
                total += float(amount)
    return total

@tool(description="Check the price of a given rate ID for a hotel.")
def price_check(
    rate_id: str = None,
    hotel_id: str = None,
    token: str = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    # State injection parameters (fallback) - using safe injection
    state: Annotated[dict, InjectedState] = None,
    ) -> Union[Command, str]:
    """
    Check the price of a given rate ID for a hotel.

    Args:
        rate_id: Rate ID to check the price for
        hotel_id: Hotel ID (explicit parameter, falls back to roomParams.hotelId if not provided)
        token: API token (can be explicit or auto-injected from state)
        tool_call_id: Tool call ID for tracking
    
    Returns:
        Command with ToolMessage containing the latest price
    """
    try:
        # Use explicit parameters or fallback to state injection
        final_rate_id = rate_id
        
        # Safely extract state values
        final_token = token
        if not final_token:
            final_token = safe_get_state_value(state, "hotelToken")
        
        # Get hotel_id with proper fallback logic
        final_hotel_id = hotel_id
        if not final_hotel_id:
            room_params = safe_get_state_value(state, "roomParams")
            if room_params and isinstance(room_params, dict):
                final_hotel_id = room_params.get("hotelId")
        
        # Validate inputs
        if not final_rate_id or not final_rate_id.strip():
            raise ValueError("Rate ID is required. Please provide the rateId from the room search results.")
            
        if not final_hotel_id or not final_hotel_id.strip():
            raise ValueError("Hotel ID is required. Either provide explicitly or ensure room search has been completed first.")
            
        if not final_token or not final_token.strip():
            raise ValueError("Token is required. Either provide explicitly or ensure room search has been completed first.")
            
        # Get base URL from environment variable
        tt_baseurl = os.getenv("TT_BASEURL")
        techspian_baseurl = os.getenv("TECHSPIAN_BASEURL")
        
        if not tt_baseurl:
            raise ValueError("TT_BASEURL environment variable is required")
        if not techspian_baseurl:
            raise ValueError("TECHSPIAN_BASEURL environment variable is required")
        # Make API request
        auth_headers = get_auth_headers()
        
        with httpx.Client(http2=True) as client:
            response = client.get(
                f"{techspian_baseurl}/api/hotel/{final_hotel_id}/{final_token}/price/{final_rate_id}",
                headers=auth_headers
            )
            
            response.raise_for_status()
            price_data = response.json()
            
            # Extract the rate data from the nested response
            hotel_data = price_data.get("hotel", {})
            room_data = hotel_data.get("room", {})
            rates = room_data.get("rates", [])
            
            # Find the matching rate by ID
            matching_rate = None
            for rate in rates:
                if rate.get("id") == final_rate_id:
                    matching_rate = rate
                    break
            
            if not matching_rate:
                raise ValueError(f"Rate ID {final_rate_id} not found in response")
            
            # Extract pricing information
            base_rate = matching_rate.get("baseRate")
            total_rate = matching_rate.get("totalRate")
            taxes = matching_rate.get("taxes")
            additional_charges = matching_rate.get("additionalCharges", [])
            currency = matching_rate.get("currency", "USD")
            
            # Calculate priceAllIn using the same logic as ranking utilities
            # First try to use margin-based calculation if available
            engine_markup = matching_rate.get("ourTotalMarkup")
            engine_fee = matching_rate.get("ourServiceFee")
            
            price_all_in = None
            
            # Try margin-based calculation first
            if engine_markup is not None and isinstance(engine_markup, (int, float)) and engine_markup >= 0:
                # If we have engine markup, use base rate + markup
                if isinstance(base_rate, (int, float)) and base_rate > 0:
                    price_all_in = float(base_rate) + float(engine_markup)
            elif engine_fee is not None and isinstance(engine_fee, (int, float)) and engine_fee >= 0:
                # If we have engine fee, add it to total rate
                if isinstance(total_rate, (int, float)) and total_rate > 0:
                    price_all_in = float(total_rate) + float(engine_fee)
            
            # Fallback to _compute_est_all_in method
            if price_all_in is None:
                price_all_in = _compute_est_all_in(
                    published=None,  # Not available in this response
                    total=total_rate,
                    base=base_rate,
                    taxes_any=taxes,
                    fee=engine_fee
                )
            
            # Add additional charges (like resort fees)
            if price_all_in is not None:
                additional_fees = _extract_additional_charges(additional_charges)
                price_all_in += additional_fees
            
            # If still no price, use total rate as fallback
            if price_all_in is None and isinstance(total_rate, (int, float)):
                price_all_in = float(total_rate)
            
            if price_all_in is None:
                raise ValueError("Unable to calculate priceAllIn from response data")
            
            # Build flattened response
            flattened_response = {
                "ok": True,
                "rate_id": final_rate_id,
                "holdExpiresAt": None,  # Not available in this API response
                "priceAllIn": round(price_all_in, 2),
                "currency": currency
            }
            
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps(flattened_response, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
            
    except Exception as e:
        # Safely get values for error response
        error_rate_id = rate_id
        error_hotel_id = hotel_id
        
        # Try to get the processed values if they exist
        try:
            if 'final_rate_id' in locals() and final_rate_id:
                error_rate_id = final_rate_id
            if 'final_hotel_id' in locals() and final_hotel_id:
                error_hotel_id = final_hotel_id
        except:
            pass  # Use original values if anything goes wrong
        
        error_response = {
            "ok": False,
            "error": str(e),
            "rate_id": error_rate_id,
            "hotel_id": error_hotel_id
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
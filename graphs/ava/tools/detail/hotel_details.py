import httpx
import json
import os
from typing import Annotated, Union, Dict, List, Any
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage

@tool(description="Get hotel details for a given hotel ID.")
async def hotel_details(hotelId: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> Union[Command, str]:
    """
    Get hotel details for a given hotel ID.
    
    Args:
        hotelId: Hotel ID to fetch details for
        tool_call_id: Tool call ID for tracking

    Returns:
        Command with ToolMessage containing hotel details
    """
    try:
        # Validate inputs
        if not hotelId or not hotelId.strip():
            raise ValueError("Hotel ID is required. Please provide the hotelId from the hotel search results.")
        
        # Get base URL from environment variable
        techspian_baseurl = os.getenv("TECHSPIAN_BASEURL")
        
        if not techspian_baseurl:
            raise ValueError("TECHSPIAN_BASEURL environment variable is required")
        
        # Make API request
        auth_headers = {
            "Accept-Encoding": "br, gzip",
            "accountId": "test-hotels-account",
            "channelId": "test-hotels-channel", 
            "correlationId": "test123"
        }
        
        async with httpx.AsyncClient(http2=True) as client:
            results_resp = await client.get(f"{techspian_baseurl}/api/hotelcontent/{hotelId}/detail", headers=auth_headers)
            results_resp.raise_for_status()
            
            # Get the response data
            results_data = results_resp.json()
            
            # Flatten the response into the desired format
            flattened_result = {
                "name": results_data.get("name", ""),
                "brand": results_data.get("chainName", "Independent"),
                "starRating": results_data.get("starRating", 0),
                "amenities": [],
                "policies": {}
            }
            
            # Extract amenities from facilities
            facilities = results_data.get("facilities", [])
            for facility in facilities:
                if isinstance(facility, dict) and "name" in facility:
                    amenity_name = facility["name"].lower().replace(" ", "").replace("/", "")
                    if amenity_name not in flattened_result["amenities"]:
                        flattened_result["amenities"].append(amenity_name)
            
            # Extract check-in/check-out times
            checkin_info = results_data.get("checkinInfo", {})
            checkout_info = results_data.get("checkoutInfo", {})
            
            if checkin_info.get("beginTime"):
                flattened_result["policies"]["checkIn"] = checkin_info["beginTime"]
            if checkout_info.get("time"):
                flattened_result["policies"]["checkOut"] = checkout_info["time"]
            
            # Extract all policies (agnostic approach)
            policies = results_data.get("policies", [])
            for policy in policies:
                if isinstance(policy, dict) and "type" in policy and "text" in policy:
                    policy_type = policy["type"]
                    policy_text = policy["text"]
                    
                    # Convert policy type to camelCase for consistency
                    policy_key = policy_type
                    if policy_type == "areChildrenAllowed":
                        policy_key = "childrenAllowed"
                        policy_text = policy_text.lower() == "true"
                    elif policy_type == "doChildrenStayFree":
                        policy_key = "childrenStayFree"
                        policy_text = policy_text.lower() == "true"
                    
                    flattened_result["policies"][policy_key] = policy_text
            
            # Return the flattened result
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps(flattened_result, indent=2),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )
            
    except Exception as e:
        # Handle any errors gracefully
        error_response = {
            "error": f"Failed to fetch hotel details: {str(e)}",
            "name": "",
            "brand": "",
            "starRating": 0,
            "amenities": [],
            "policies": {}
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
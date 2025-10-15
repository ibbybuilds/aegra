import httpx
import json
import os
from typing import Annotated, Union, Dict, List, Any
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.types import Command
from langchain_core.messages import ToolMessage
from ava.utils.ranking.rank_rooms import rank_rooms
from ava.utils.jwt import get_auth_headers

@tool(description="Query hotel names to resolve natural-language hotel names to hotel IDs. Takes a query string and city hint, returns hotel information including ID, name, and city.")
async def query_hotel_name(
    query: str,
    cityHint: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Union[Command, str]:
    """
    Query hotel names to resolve natural-language hotel names to hotel IDs. Takes a query string and city hint, returns hotel information including ID, name, and city.
    
    Args:
        query: Query string to search for hotel names
        cityHint: City hint to use for the search
        tool_call_id: Tool call ID for tracking
    
    Returns:
        Command with ToolMessage containing hotel information
    """
    try:
        # Validate inputs
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        if not cityHint or not cityHint.strip():
            raise ValueError("City hint cannot be empty")
        
        # Construct the search query by concatenating query and cityHint
        search_query = f"{query.strip()} — {cityHint.strip()}"
        
        # Prepare request body
        request_body = {
            "query": search_query,
            "limit": 3,
            "indexName": "hotels"
        }
        
        # Get Pinecone service URL from environment variables
        railway_baseurl = os.getenv("RAILWAY_BASEURL", "https://pinecone-service-local-staging-4870.up.railway.app")
        
        # Make POST request to Pinecone service
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{railway_baseurl}/search",
                json=request_body,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        
        # Extract and format results
        results = data.get("results", [])
        total = data.get("total", 0)
        
        # Check if top result has high confidence (score > 0.9)
        high_confidence_threshold = 0.9
        top_score = results[0].get("score", 0) if results else 0
        
        if top_score > high_confidence_threshold and results:
            # High confidence: return only the top match
            top_hotel = results[0]
            formatted_hotels = [{
                "id": top_hotel.get("id"),
                "name": top_hotel.get("name")
            }]
            message = f"Found high-confidence match: '{top_hotel.get('name')}' (score: {round(top_score, 3)})"
        else:
            # Low confidence: return all 3 matches for LLM to choose
            formatted_hotels = []
            for hotel in results:
                formatted_hotels.append({
                    "id": hotel.get("id"),
                    "name": hotel.get("name")
                })
            message = f"Found {len(results)} hotels matching '{query}' in {cityHint} (top score: {round(top_score, 3)})"
        
        # Create response for LLM
        response_data = {
            "query": search_query,
            "hotels": formatted_hotels,
            "message": message
        }
        
        # Return Command with results
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(response_data, indent=2),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
        
    except Exception as e:
        # Handle errors gracefully
        error_response = {
            "error": str(e),
            "query": query,
            "cityHint": cityHint,
            "hotels": [],
            "total": 0
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

@tool(description="Get geo coordinates for a given location query using Google Places API.")
async def get_geo_coordinates(
    query: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Union[Command, str]:
    """
    Get geo coordinates for a given query using Google Places API.

    Args:
        query: Query string to get geo coordinates for
        tool_call_id: Tool call ID for tracking
    
    Returns:
        Command with ToolMessage containing geo coordinates
    """
    try:
        # Validate inputs
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")
        
        # Get Google API key from environment variables
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is required")
        
        # Prepare request body
        request_body = {
            "textQuery": query.strip(),
            "pageSize": 1
        }
        
        # Prepare headers
        headers = {
            "X-Goog-Api-Key": google_api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
            "Content-Type": "application/json"
        }
        
        # Make POST request to Google Places API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=request_body,
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        
        # Extract and format results
        places = data.get("places", [])
        
        if not places:
            # No places found
            response_data = {
                "query": query,
                "places": [],
                "message": f"No places found for '{query}'"
            }
        else:
            # Format the first place result
            place = places[0]
            location = place.get("location", {})
            
            formatted_place = {
                "displayName": place.get("displayName", {}).get("text", "N/A"),
                "formattedAddress": place.get("formattedAddress", "N/A"),
                "latitude": location.get("latitude"),
                "longitude": location.get("longitude")
            }
            
            response_data = {
                "query": query,
                "places": [formatted_place],
                "message": f"Found coordinates for '{formatted_place['displayName']}'"
            }
        
        # Return Command with results
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(response_data, indent=2),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
        
    except Exception as e:
        # Handle errors gracefully
        error_response = {
            "error": str(e),
            "query": query,
            "places": [],
            "message": f"Failed to get coordinates for '{query}'"
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
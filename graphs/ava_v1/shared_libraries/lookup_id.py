"""Hotel ID lookup utility for resolving natural-language hotel names to hotel IDs."""

from typing import Any

import httpx


async def lookup_id(query: str, city_hint: str) -> dict[str, Any]:
    """Query hotel names to resolve natural-language hotel names to hotel IDs.

    Takes a query string (hotel name) and city string, returns hotel information
    including ID, name, and city with confidence scoring.

    Args:
        query: Hotel name query (e.g., "Marriott Downtown")
        city_hint: City name for context (e.g., "Miami")

    Returns:
        Dictionary with query results:

        High confidence (score > 0.9):
        {
            "query": str,
            "hotels": [{"id": str, "name": str}],  # Single match
            "message": str,
            "confidence": "high"
        }

        Low confidence (score <= 0.9):
        {
            "query": str,
            "hotels": [{"id": str, "name": str}, ...],  # Multiple matches
            "message": str,
            "confidence": "low",
            "top_score": float
        }

        Error:
        {
            "error": str,
            "message": str
        }
    """
    # Build search query
    search_query = f"{query} {city_hint}"

    # API endpoint
    pinecone_url = "https://pinecone-service-local-staging-4870.up.railway.app/search"

    # Request body
    request_body = {"query": search_query, "limit": 3, "indexName": "hotels"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(pinecone_url, json=request_body, timeout=10.0)
            response.raise_for_status()
            response_data = response.json()

            # Extract results array from response
            results = (
                response_data.get("results", [])
                if isinstance(response_data, dict)
                else response_data
            )

    except httpx.HTTPStatusError as e:
        return {
            "error": "api_error",
            "message": f"Pinecone API error {e.response.status_code}: {str(e)}",
        }

    except httpx.TimeoutException:
        return {"error": "timeout", "message": "Request to Pinecone service timed out"}

    except Exception as e:
        return {
            "error": "unexpected_error",
            "message": f"Failed to lookup hotel ID: {str(e)}",
        }

    # Handle empty results
    if not results or not isinstance(results, list) or len(results) == 0:
        return {
            "error": "no_results",
            "message": f"No hotels found matching '{query}' in {city_hint}",
        }

    # Check if top result has high confidence (score > 0.9)
    high_confidence_threshold = 0.9
    top_score = results[0].get("score", 0) if results else 0

    if top_score > high_confidence_threshold and results:
        # High confidence: return only the top match
        top_hotel = results[0]
        formatted_hotels = [
            {"id": str(top_hotel.get("id")), "name": top_hotel.get("name")}
        ]
        message = f"Found high-confidence match: '{top_hotel.get('name')}' (score: {round(top_score, 3)})"

        return {
            "query": search_query,
            "hotels": formatted_hotels,
            "message": message,
            "confidence": "high",
        }
    else:
        # Low confidence: return all 3 matches for LLM to choose
        formatted_hotels = []
        for hotel in results:
            formatted_hotels.append(
                {"id": str(hotel.get("id")), "name": hotel.get("name")}
            )

        message = f"Found {len(results)} hotels matching '{query}' in {city_hint} (top score: {round(top_score, 3)})"

        return {
            "query": search_query,
            "hotels": formatted_hotels,
            "message": message,
            "confidence": "low",
            "top_score": round(top_score, 3),
        }

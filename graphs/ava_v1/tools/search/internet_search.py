"""Internet search tool using Tavily API."""

import json
import logging
import os

from langchain.tools import tool
from pydantic import BaseModel, Field
from tavily import TavilyClient

logger = logging.getLogger(__name__)


def _get_tavily_client() -> TavilyClient:
    """Get or create Tavily client (lazy initialization).

    Returns:
        TavilyClient instance

    Raises:
        ValueError: If TAVILY_API_KEY is not set
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError(
            "TAVILY_API_KEY environment variable is required for internet search. "
            "Please set it in your .env file or environment."
        )
    return TavilyClient(api_key=api_key)


class InternetSearchInput(BaseModel):
    """Input schema for internet search."""

    query: str = Field(
        description="Search query for hotel booking related information"
    )
    max_results: int = Field(
        default=3,
        description="Maximum number of search results to return (max 5)",
        ge=1,
        le=5,
    )


@tool(
    args_schema=InternetSearchInput,
    description="Search the internet for hotel booking related information such as weather, events, or hotel reviews",
)
def internet_search(
    query: str,
    max_results: int = 3,
) -> str:
    """Search the internet for hotel booking related information.

    Use for: weather during travel dates, major events affecting hotel availability,
    hotel reviews, or area disruptions. Only use when information directly affects
    hotel booking decisions.

    Args:
        query: Specific search query (e.g., "Miami weather December 15-18 2025")
        max_results: Number of results to return (default: 3, max: 5)

    Returns:
        JSON string with search results containing title, url, content, and score
    """
    logger.info("=" * 80)
    logger.info("[INTERNET_SEARCH] Tool called with:")
    logger.info(f"  query: {query}")
    logger.info(f"  max_results: {max_results}")
    logger.info("=" * 80)

    # Validate parameters
    if not query or not isinstance(query, str) or not query.strip():
        error_result = {
            "status": "error",
            "error": {
                "type": "invalid_query",
                "message": "query must be a non-empty string",
            },
        }
        return json.dumps(error_result, indent=2)

    # Limit max_results to reasonable range
    if max_results < 1:
        max_results = 1
    elif max_results > 5:
        max_results = 5

    try:
        # Get Tavily client
        tavily_client = _get_tavily_client()

        # Perform search
        logger.info(f"[INTERNET_SEARCH] Searching Tavily for: {query}")
        search_response = tavily_client.search(
            query=query,
            max_results=max_results,
            include_raw_content=False,  # Don't include full HTML content
        )

        # Extract results
        results = search_response.get("results", [])

        # Format response
        result = {
            "query": query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0.0),
                }
                for r in results
            ],
            "count": len(results),
            "hint": (
                f"Found {len(results)} search results for '{query}'. Review the content and "
                "synthesize the key information to answer the user's question. Cite sources "
                "when presenting important facts."
            ),
        }

        logger.info(f"[INTERNET_SEARCH] Found {len(results)} results")
        return json.dumps(result, indent=2)

    except ValueError as e:
        # API key not configured
        error_result = {
            "status": "error",
            "error": {
                "type": "configuration_error",
                "message": str(e),
            },
        }
        logger.error(f"[INTERNET_SEARCH] Configuration error: {e}")
        return json.dumps(error_result, indent=2)

    except Exception as e:
        # General error
        error_result = {
            "status": "error",
            "error": {
                "type": "search_failed",
                "message": f"Failed to perform search: {str(e)}",
            },
        }
        logger.error(f"[INTERNET_SEARCH] Search failed: {e}", exc_info=True)
        return json.dumps(error_result, indent=2)

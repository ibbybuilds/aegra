"""This module provides tools for the agent.

Includes:
- Web search functionality
- Student profile information retrieval from LMS
- Long-term memory storage and retrieval

These tools are intended as examples to get started. For production use,
consider implementing more robust and specialized tools tailored to your needs.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import httpx
from langchain_tavily import TavilyExtract, TavilySearch
from langgraph.runtime import get_runtime

from react_agent.context import Context
from react_agent.memory import get_user_memory, save_user_memory, search_user_memories

logger = logging.getLogger(__name__)


async def search(query: str) -> dict[str, Any]:
    """Search the web for general information and current events.

    This function performs a search using the Tavily search engine, which provides
    comprehensive, accurate, and trusted results. It's particularly useful for
    answering questions about current events, general knowledge, and research.

    Args:
        query: The search query string
    """
    runtime = get_runtime(Context)
    max_results = runtime.context.max_search_results

    try:
        logger.info(f"Searching web for: {query}")

        # Initialize Tavily search with max results from context
        web_search = TavilySearch(max_results=max_results, topic="general")

        # Execute search in thread to avoid blocking
        search_results = await asyncio.to_thread(web_search.invoke, {"query": query})

        # Handle different response formats
        if isinstance(search_results, list):
            results_list = search_results
        elif isinstance(search_results, dict):
            results_list = search_results.get("results", [])
        else:
            logger.warning(f"Unexpected response type: {type(search_results)}")
            return {
                "query": query,
                "results": [],
                "error": f"Unexpected response type: {type(search_results)}",
            }

        # Process and format results
        processed_results = {"query": query, "results": []}

        for result in results_list:
            if isinstance(result, dict):
                processed_results["results"].append(
                    {
                        "title": result.get("title", "No title"),
                        "url": result.get("url", ""),
                        "content_preview": result.get("content", ""),
                    }
                )
            else:
                logger.warning(f"Unexpected result type: {type(result)}")

        logger.info(
            f"Found {len(processed_results['results'])} search results for '{query}'"
        )
        return processed_results

    except Exception as e:
        logger.error(f"Error in web search: {str(e)}", exc_info=True)
        return {"query": query, "results": [], "error": f"Search failed: {str(e)}"}


async def extract_webpage_content(urls: list[str]) -> list[dict[str, Any]]:
    """Extract full content from webpages for detailed analysis.

    Use this after the search tool to get complete information from promising results.
    Extracts the main content, title, and other relevant information from web pages.

    Args:
        urls: List of URLs to extract content from (max 3 recommended)
    """
    try:
        logger.info(f"Extracting content from {len(urls)} URLs")

        # Initialize Tavily extract
        web_extract = TavilyExtract()

        # Execute extraction in thread to avoid blocking
        results = await asyncio.to_thread(web_extract.invoke, {"urls": urls})

        # Extract results from response
        extracted_results = (
            results.get("results", []) if isinstance(results, dict) else []
        )

        # Process results to ensure they have content
        processed_results = []
        for result in extracted_results:
            if isinstance(result, dict):
                # Tavily uses 'raw_content' not 'content'
                content = result.get("raw_content", "")
                processed_results.append(
                    {
                        "url": result.get("url", ""),
                        "title": result.get("title", ""),
                        "content": content,
                        "content_length": len(content),
                    }
                )
            else:
                processed_results.append(result)

        logger.info(
            f"Successfully extracted content from {len(processed_results)} pages"
        )
        return processed_results

    except Exception as e:
        logger.error(f"Error extracting webpage content: {str(e)}", exc_info=True)
        return [{"error": f"Extraction failed: {str(e)}"}]


async def get_student_profile() -> dict[str, Any]:
    """Get the current student's profile information from the LMS.

    Retrieves the authenticated student's profile including their name, role,
    onboarding status, and other relevant information. Returns a dict with:
    - name: Student's full name
    - role: User role (typically 'student')
    - onboardingComplete: Whether student completed onboarding
    - onboardingSkipped: Whether student skipped onboarding
    """
    runtime = get_runtime(Context)

    # Get the user token from context
    token = runtime.context.user_token
    if not token:
        logger.error("No user token available in context")
        return {
            "error": "Authentication required",
            "message": "Unable to fetch student profile without authentication token",
        }

    # Get LMS API URL from context
    lms_url = runtime.context.lms_api_url
    profile_endpoint = f"{lms_url}/api/v1/user/profile"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.info(f"Fetching student profile from {profile_endpoint}")

            response = await client.get(
                profile_endpoint,
                headers={"accept": "*/*", "Authorization": f"Bearer {token}"},
            )

            response.raise_for_status()
            data = response.json()

            # Extract only the required fields
            profile = {
                "name": data.get("name"),
                "role": data.get("role"),
                "onboardingComplete": data.get("onboardingComplete"),
                "onboardingSkipped": data.get("onboardingSkipped"),
            }

            logger.info(
                f"Successfully fetched profile for student: {profile.get('name')}"
            )
            return profile

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error fetching student profile: {e.response.status_code}")
        return {
            "error": "API request failed",
            "status_code": e.response.status_code,
            "message": str(e),
        }
    except httpx.TimeoutException:
        logger.error("Timeout while fetching student profile")
        return {
            "error": "Request timeout",
            "message": "The LMS API took too long to respond",
        }
    except Exception as e:
        logger.error(f"Unexpected error fetching student profile: {e}", exc_info=True)
        return {"error": "Unexpected error", "message": str(e)}


async def get_student_onboarding() -> dict[str, Any]:
    """Get the current student's onboarding information from the LMS.

    Retrieves detailed onboarding data including learning track, preferences,
    technical background, and time commitment information. Returns a dict with:
    - learningTrack: Selected learning track (e.g., 'data-science')
    - timeCommitment: Schedule and hours per week
    - learningPreferences: Learning style, problem-solving approach, etc.
    - technicalBackground: Tools, experience level, tasks performed
    - completed: Whether onboarding is completed
    - completedSteps: List of completed onboarding steps
    """
    runtime = get_runtime(Context)

    # Get the user token from context
    token = runtime.context.user_token
    if not token:
        logger.error("No user token available in context")
        return {
            "error": "Authentication required",
            "message": "Unable to fetch student onboarding without authentication token",
        }

    # Get LMS API URL from context
    lms_url = runtime.context.lms_api_url
    onboarding_endpoint = f"{lms_url}/api/v1/onboarding"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.info(f"Fetching student onboarding from {onboarding_endpoint}")

            response = await client.get(
                onboarding_endpoint,
                headers={"accept": "*/*", "Authorization": f"Bearer {token}"},
            )

            response.raise_for_status()
            data = response.json()

            # Extract the onboarding data
            onboarding_data = data.get("onboarding", {})

            # Structure the response with relevant fields
            onboarding = {
                "learningTrack": onboarding_data.get("learningTrack"),
                "timeCommitment": onboarding_data.get("timeCommitment", {}),
                "learningPreferences": onboarding_data.get("learningPreferences", {}),
                "technicalBackground": onboarding_data.get("technicalBackground", {}),
                "completed": onboarding_data.get("completed"),
                "completedSteps": onboarding_data.get("completedSteps", []),
            }

            logger.info(
                f"Successfully fetched onboarding for learning track: {onboarding.get('learningTrack')}"
            )
            return onboarding

    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error fetching student onboarding: {e.response.status_code}"
        )
        return {
            "error": "API request failed",
            "status_code": e.response.status_code,
            "message": str(e),
        }
    except httpx.TimeoutException:
        logger.error("Timeout while fetching student onboarding")
        return {
            "error": "Request timeout",
            "message": "The LMS API took too long to respond",
        }
    except Exception as e:
        logger.error(
            f"Unexpected error fetching student onboarding: {e}", exc_info=True
        )
        return {"error": "Unexpected error", "message": str(e)}


async def get_student_ai_mentor_onboarding() -> dict[str, Any]:
    """Get the student's comprehensive AI mentor onboarding information from the LMS.

    Retrieves detailed onboarding data collected through the AI mentor setup flow,
    including:
    - Professional situation and experience (s1: situation, weeklyTime, learningStyle)
    - Employment details (s2: employmentStatus, roleTitle, industry, yearsExperience, etc.)
    - Educational background (s3: highestEducation, fieldOfStudy, discoveredAI)
    - Career goals and timeline (s4: primaryGoal, targetRole, timeline, goalWhy)
    - Skills assessment and profiles (s5: LinkedIn, GitHub, confidentSkills, needHelpAreas)
    - Job search status (s6: appsSubmitted, interviews, biggestChallenge)
    - Learning track specialization (s_track: analytics, dataScience, dataEngineering, aiEngineering)
    - Mentoring preferences (s7: feedbackStyle, availability, motivators, riskTolerance)
    - Transformational outcomes (s8: transformationalOutcome, otherNotes)
    """
    runtime = get_runtime(Context)

    # Get the user token from context
    token = runtime.context.user_token
    if not token:
        logger.error("No user token available in context")
        return {
            "error": "Authentication required",
            "message": "Unable to fetch AI mentor onboarding without authentication token",
        }

    # Get LMS API URL from context
    lms_url = runtime.context.lms_api_url
    mentor_endpoint = f"{lms_url}/api/v1/ai-mentor/onboarding/me"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.info(f"Fetching AI mentor onboarding from {mentor_endpoint}")

            response = await client.get(
                mentor_endpoint,
                headers={"accept": "*/*", "Authorization": f"Bearer {token}"},
            )

            response.raise_for_status()
            data = response.json()

            # Extract the onboarding data
            onboarding_data = data.get("onboarding", {})

            # Structure the response with all onboarding sections
            mentor_onboarding = {
                "s1": onboarding_data.get("s1", {}),
                "s2": onboarding_data.get("s2", {}),
                "s3": onboarding_data.get("s3", {}),
                "s4": onboarding_data.get("s4", {}),
                "s5": onboarding_data.get("s5", {}),
                "s6": onboarding_data.get("s6", {}),
                "s_track": onboarding_data.get("s_track", {}),
                "s7": onboarding_data.get("s7", {}),
                "s8": onboarding_data.get("s8", {}),
                "learningTrack": onboarding_data.get("learningTrack"),
                "completedSteps": onboarding_data.get("completedSteps", []),
                "completed": onboarding_data.get("completed"),
            }

            logger.info(
                f"Successfully fetched AI mentor onboarding, completed: {mentor_onboarding.get('completed')}"
            )
            return mentor_onboarding

    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error fetching AI mentor onboarding: {e.response.status_code}"
        )
        return {
            "error": "API request failed",
            "status_code": e.response.status_code,
            "message": str(e),
        }
    except httpx.TimeoutException:
        logger.error("Timeout while fetching AI mentor onboarding")
        return {
            "error": "Request timeout",
            "message": "The LMS API took too long to respond",
        }
    except Exception as e:
        logger.error(
            f"Unexpected error fetching AI mentor onboarding: {e}", exc_info=True
        )
        return {"error": "Unexpected error", "message": str(e)}


TOOLS: list[Callable[..., Any]] = [
    search,
    extract_webpage_content,
    get_student_profile,
    get_student_onboarding,
    get_student_ai_mentor_onboarding,
    get_user_memory,
    save_user_memory,
    search_user_memories,
]

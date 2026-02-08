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
from langchain_community.tools import BraveSearch
from langgraph.runtime import get_runtime

from react_agent.context import Context
from react_agent.memory import get_user_memory, save_user_memory, search_user_memories

logger = logging.getLogger(__name__)

# Import RAG course retriever
try:
    import sys
    from pathlib import Path

    # Add src to path if needed
    project_root = Path(__file__).parent.parent.parent
    src_path = project_root / "libs" / "aegra-api" / "src"
    if src_path.exists() and str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

    from aegra_api.tools.rag import CourseRetriever

    RAG_AVAILABLE = True
    logger.info("RAG course search module loaded successfully")
except ImportError as e:
    RAG_AVAILABLE = False
    logger.warning(
        f"RAG CourseRetriever not available: {e}. Course search will be disabled."
    )


async def brave_search(query: str) -> str:
    """Search the web for general information and current events using Brave Search.

    Args:
        query: The search query string
    """
    runtime = get_runtime(Context)
    api_key = runtime.context.brave_search_api_key

    try:
        logger.info(f"Searching web with Brave for: {query}")

        if api_key:
            tool = BraveSearch.from_api_key(api_key=api_key, search_kwargs={"count": 3})
        else:
            # Fallback to environment variable if not in context
            tool = BraveSearch.from_search_kwargs(search_kwargs={"count": 3})

        # Execute search in thread to avoid blocking
        search_results = await asyncio.to_thread(tool.run, query)

        return search_results

    except Exception as e:
        logger.error(f"Error in Brave search: {str(e)}", exc_info=True)
        return f"Search failed: {str(e)}"


# async def search(query: str) -> dict[str, Any]:
#     """Search the web for general information and current events.
#
#     This function performs a search using the Tavily search engine, which provides
#     comprehensive, accurate, and trusted results. It's particularly useful for
#     answering questions about current events, general knowledge, and research.
#
#     Args:
#         query: The search query string
#     """
#     runtime = get_runtime(Context)
#     max_results = runtime.context.max_search_results
#
#     try:
#         logger.info(f"Searching web for: {query}")
#
#         # Initialize Tavily search with max results from context
#         web_search = TavilySearch(max_results=max_results, topic="general")
#
#         # Execute search in thread to avoid blocking
#         search_results = await asyncio.to_thread(web_search.invoke, {"query": query})
#
#         # Handle different response formats
#         if isinstance(search_results, list):
#             results_list = search_results
#         elif isinstance(search_results, dict):
#             results_list = search_results.get("results", [])
#         else:
#             logger.warning(f"Unexpected response type: {type(search_results)}")
#             return {
#                 "query": query,
#                 "results": [],
#                 "error": f"Unexpected response type: {type(search_results)}",
#             }
#
#         # Process and format results
#         processed_results = {"query": query, "results": []}
#
#         for result in results_list:
#             if isinstance(result, dict):
#                 processed_results["results"].append(
#                     {
#                         "title": result.get("title", "No title"),
#                         "url": result.get("url", ""),
#                         "content_preview": result.get("content", ""),
#                     }
#                 )
#             else:
#                 logger.warning(f"Unexpected result type: {type(result)}")
#
#         logger.info(
#             f"Found {len(processed_results['results'])} search results for '{query}'"
#         )
#         return processed_results
#
#     except Exception as e:
#         logger.error(f"Error in web search: {str(e)}", exc_info=True)
#         return {"query": query, "results": [], "error": f"Search failed: {str(e)}"}


# async def extract_webpage_content(urls: list[str]) -> list[dict[str, Any]]:
#     """Extract full content from webpages for detailed analysis.
#
#     Use this after the search tool to get complete information from promising results.
#     Extracts the main content, title, and other relevant information from web pages.
#
#     Args:
#         urls: List of URLs to extract content from (max 3 recommended)
#     """
#     try:
#         logger.info(f"Extracting content from {len(urls)} URLs")
#
#         # Initialize Tavily extract
#         web_extract = TavilyExtract()
#
#         # Execute extraction in thread to avoid blocking
#         results = await asyncio.to_thread(web_extract.invoke, {"urls": urls})
#
#         # Extract results from response
#         extracted_results = (
#             results.get("results", []) if isinstance(results, dict) else []
#         )
#
#         # Process results to ensure they have content
#         processed_results = []
#         for result in extracted_results:
#             if isinstance(result, dict):
#                 # Tavily uses 'raw_content' not 'content'
#                 content = result.get("raw_content", "")
#                 processed_results.append(
#                     {
#                         "url": result.get("url", ""),
#                         "title": result.get("title", ""),
#                         "content": content,
#                         "content_length": len(content),
#                     }
#                 )
#             else:
#                 processed_results.append(result)
#
#         logger.info(
#             f"Successfully extracted content from {len(processed_results)} pages"
#         )
#         return processed_results
#
#     except Exception as e:
#         logger.error(f"Error extracting webpage content: {str(e)}", exc_info=True)
#         return [{"error": f"Extraction failed: {str(e)}"}]


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


async def get_student_ai_career_advisor_onboarding() -> dict[str, Any]:
    """Get the student's comprehensive AI career advisor onboarding information from the LMS.

    Retrieves detailed onboarding data collected through the AI career advisor setup flow,
    including:
    - Professional situation and experience (s1: situation, weeklyTime, learningStyle)
    - Employment details (s2: employmentStatus, roleTitle, industry, yearsExperience, etc.)
    - Educational background (s3: highestEducation, fieldOfStudy, discoveredAI)
    - Career goals and timeline (s4: primaryGoal, targetRole, timeline, goalWhy)
    - Skills assessment and profiles (s5: LinkedIn, GitHub, confidentSkills, needHelpAreas)
    - Job search status (s6: appsSubmitted, interviews, biggestChallenge)
    - Learning track specialization (s_track: analytics, dataScience, dataEngineering, aiEngineering)
    - Career guidance preferences (s7: feedbackStyle, availability, motivators, riskTolerance)
    - Transformational outcomes (s8: transformationalOutcome, otherNotes)
    """
    runtime = get_runtime(Context)

    # Get the user token from context
    token = runtime.context.user_token
    if not token:
        logger.error("No user token available in context")
        return {
            "error": "Authentication required",
            "message": "Unable to fetch AI career advisor onboarding without authentication token",
        }

    # Get LMS API URL from context
    lms_url = runtime.context.lms_api_url
    career_advisor_endpoint = f"{lms_url}/api/v1/ai-mentor/onboarding/me"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.info(
                f"Fetching AI career advisor onboarding from {career_advisor_endpoint}"
            )

            response = await client.get(
                career_advisor_endpoint,
                headers={"accept": "*/*", "Authorization": f"Bearer {token}"},
            )

            response.raise_for_status()
            data = response.json()

            # Extract the onboarding data
            onboarding_data = data.get("onboarding", {})

            # Structure the response with all onboarding sections
            career_advisor_onboarding = {
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
                f"Successfully fetched AI career advisor onboarding, completed: {career_advisor_onboarding.get('completed')}"
            )
            return career_advisor_onboarding

    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error fetching AI career advisor onboarding: {e.response.status_code}"
        )
        return {
            "error": "API request failed",
            "status_code": e.response.status_code,
            "message": str(e),
        }
    except httpx.TimeoutException:
        logger.error("Timeout while fetching AI career advisor onboarding")
        return {
            "error": "Request timeout",
            "message": "The LMS API took too long to respond",
        }
    except Exception as e:
        logger.error(
            f"Unexpected error fetching AI career advisor onboarding: {e}",
            exc_info=True,
        )
        return {"error": "Unexpected error", "message": str(e)}


async def search_course_content(
    query: str,
    course_id: str | None = None,
    max_results: int = 5,
) -> dict[str, Any]:
    """Search for relevant course content using semantic similarity.

    This tool searches through indexed course materials, lessons, and descriptions
    to find the most relevant information based on your query. Use this when:
    - Students ask about specific course topics or concepts
    - Looking for explanations from course materials
    - Finding relevant lessons or modules
    - Retrieving course-specific information

    Args:
        query: The search query (e.g., "What is machine learning?", "SQL joins tutorial")
        course_id: Optional course ID to search within a specific course
        max_results: Maximum number of results to return (default: 5)

    Returns:
        A dict containing:
        - query: The original search query
        - results: List of relevant course content chunks with:
            - content: The relevant text content
            - title: Title of the lesson/material
            - course_id: ID of the course
            - content_type: Type (lesson, material, course_description)
            - metadata: Additional context (level, module, etc.)
        - error: Error message if search fails
    """
    if not RAG_AVAILABLE:
        logger.error("RAG system not available")
        return {
            "query": query,
            "results": [],
            "error": "Course search is not available. RAG system not initialized.",
        }

    try:
        logger.info(f"Searching course content for: {query}")
        if course_id:
            logger.info(f"Filtering by course_id: {course_id}")

        # Initialize retriever
        retriever = CourseRetriever()

        # Perform semantic search
        results = await retriever.search(
            query=query,
            course_id=course_id,
            k=max_results,
        )

        if not results:
            logger.info(f"No course content found for query: {query}")
            return {
                "query": query,
                "results": [],
                "message": "No relevant course content found. The course may not be indexed yet.",
            }

        logger.info(f"Found {len(results)} relevant course content chunks")
        return {
            "query": query,
            "results": results,
            "total_results": len(results),
        }

    except Exception as e:
        logger.error(f"Error searching course content: {str(e)}", exc_info=True)
        return {
            "query": query,
            "results": [],
            "error": f"Course search failed: {str(e)}",
        }


# Build tools list dynamically based on availability
TOOLS: list[Callable[..., Any]] = [
    # search,
    # extract_webpage_content,
    brave_search,
    get_student_profile,
    get_student_onboarding,
    get_student_ai_career_advisor_onboarding,
    get_user_memory,
    save_user_memory,
    search_user_memories,
]

# Add RAG tool if available
if RAG_AVAILABLE:
    TOOLS.append(search_course_content)
    logger.info("RAG course search tool enabled")

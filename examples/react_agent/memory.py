"""Long-term memory tools for the agent.

This module provides tools for reading and writing user-specific long-term memories
using LangGraph's persistence layer.
"""

import logging
from typing import Any

from langgraph.runtime import get_runtime

from react_agent.context import Context

logger = logging.getLogger(__name__)


async def get_user_memory(memory_key: str) -> dict[str, Any]:
    """
    Retrieve user-specific long-term memory from the store.

    This tool allows the agent to recall information about the user that has been
    saved in previous conversations, such as:
    - User preferences and settings
    - Learning goals and progress
    - Communication style preferences
    - Personal context and background

    Common memory keys: "preferences", "goals", "notes"

    Args:
        memory_key: The specific memory to retrieve (e.g., "preferences", "goals", "notes")
    """
    runtime = get_runtime(Context)
    store = runtime.store

    if not store:
        logger.warning("No store available for memory retrieval")
        return {
            "error": "Memory store not configured",
            "message": "Long-term memory is not available",
        }

    # Get user_id from the runtime context (injected from JWT token)
    user_id = runtime.context.user_id

    if not user_id:
        logger.warning("No user_id in context, user not authenticated")
        return {
            "error": "User not authenticated",
            "message": "Cannot retrieve memory without authentication",
        }

    namespace = (user_id, "memories")

    try:
        logger.info(f"Retrieving memory for user {user_id}, key: {memory_key}")
        memory_item = await store.aget(namespace, memory_key)

        if memory_item:
            logger.info(f"Found memory for {user_id}/{memory_key}")
            return memory_item.value
        else:
            logger.info(f"No memory found for {user_id}/{memory_key}")
            return {}

    except Exception as e:
        logger.error(f"Error retrieving memory: {e}", exc_info=True)
        return {"error": "Failed to retrieve memory", "message": str(e)}


async def save_user_memory(memory_key: str, memory_data: dict[str, Any]) -> str:
    """
    Save user-specific information to long-term memory.

    This tool allows the agent to remember important information about the user
    across conversations. Use this when the user shares:
    - Preferences (communication style, learning preferences, etc.)
    - Goals (career goals, learning objectives, milestones)
    - Personal context (background, interests, constraints)
    - Important notes from the conversation

    Args:
        memory_key: The category/key for this memory (e.g., "preferences", "goals", "notes")
        memory_data: The information to save (must be a dictionary)
    """
    runtime = get_runtime(Context)
    store = runtime.store

    if not store:
        logger.warning("No store available for memory storage")
        return "Error: Memory store not configured. Long-term memory is not available."

    # Get user_id from runtime context (injected from JWT token)
    user_id = runtime.context.user_id

    if not user_id:
        logger.warning("No user_id in context, user not authenticated")
        return (
            "Error: User not authenticated. Cannot save memory without authentication."
        )

    namespace = (user_id, "memories")

    try:
        logger.info(f"Saving memory for user {user_id}, key: {memory_key}")
        logger.debug(f"Memory data: {memory_data}")

        # Save to store
        await store.aput(namespace, memory_key, memory_data)

        logger.info(f"Successfully saved memory for {user_id}/{memory_key}")
        return f"Successfully saved {memory_key} to your long-term memory."

    except Exception as e:
        logger.error(f"Error saving memory: {e}", exc_info=True)
        return f"Error: Failed to save memory. {str(e)}"


async def search_user_memories(query: str) -> list[dict[str, Any]]:
    """
    Search through user's long-term memories using semantic search.

    This tool allows the agent to find relevant information from past conversations
    by searching through all stored memories for the user.

    Args:
        query: Natural language query to search for (e.g., "user's career goals", "learning preferences")
    """
    runtime = get_runtime(Context)
    store = runtime.store

    if not store:
        logger.warning("No store available for memory search")
        return [
            {
                "error": "Memory store not configured",
                "message": "Long-term memory search is not available",
            }
        ]

    user_id = runtime.context.user_id

    if not user_id:
        logger.warning("No user_id in context, user not authenticated")
        return [
            {
                "error": "User not authenticated",
                "message": "Cannot search memories without authentication",
            }
        ]

    namespace = (user_id, "memories")

    try:
        logger.info(f"Searching memories for user {user_id}, query: {query}")

        # Search memories using semantic search
        results = await store.asearch(namespace, query=query, limit=5)

        memories = []
        for item in results:
            memories.append(
                {
                    "key": item.key,
                    "value": item.value,
                    "created_at": item.created_at.isoformat()
                    if item.created_at
                    else None,
                    "updated_at": item.updated_at.isoformat()
                    if item.updated_at
                    else None,
                }
            )

        logger.info(f"Found {len(memories)} matching memories")
        return memories

    except Exception as e:
        logger.error(f"Error searching memories: {e}", exc_info=True)
        return [{"error": "Failed to search memories", "message": str(e)}]

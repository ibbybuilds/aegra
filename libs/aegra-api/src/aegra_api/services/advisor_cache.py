"""Caching service for student learning tracks and career advisors.

This module provides caching to avoid repeatedly hitting the LMS API for
learning track information. Uses Redis when available, falls back to in-memory cache.

Cache Strategy:
1. Redis (distributed) - TTL of 1 hour for learning track
2. In-memory (fallback) - TTL of 1 hour for learning track
3. Thread metadata - Persists advisor for the conversation lifetime
"""

import asyncio
import json
import time
from typing import Any, cast

import httpx
import structlog

from aegra_api.core.redis import redis_manager
from aegra_api.data.career_advisors import (
    get_advisor_by_track,
    get_default_advisor,
)
from aegra_api.settings import settings

logger = structlog.getLogger(__name__)

# Cache TTL in seconds (1 hour)
LEARNING_TRACK_CACHE_TTL = 3600

# In-memory cache fallback (user_id -> (learning_track, expiry_timestamp))
_memory_cache: dict[str, tuple[str | None, float]] = {}
_cache_lock = asyncio.Lock()

# LMS API URL from settings
LMS_API_URL = settings.app.LMS_URL


def _get_cache_key(user_id: str) -> str:
    """Generate Redis cache key for user's learning track."""
    return f"dedatahub:learning_track:{user_id}"


def _get_advisor_cache_key(user_id: str) -> str:
    """Generate Redis cache key for user's advisor."""
    return f"dedatahub:advisor:{user_id}"


async def _get_from_redis(key: str) -> str | None:
    """Get value from Redis cache."""
    if not redis_manager.is_available():
        return None

    try:
        client = redis_manager.get_client()
        value = await client.get(key)
        return cast(str | None, value)
    except Exception as e:
        logger.warning("Redis get failed", error=str(e))
        return None


async def _set_in_redis(
    key: str, value: str, ttl: int = LEARNING_TRACK_CACHE_TTL
) -> bool:
    """Set value in Redis cache with TTL."""
    if not redis_manager.is_available():
        return False

    try:
        client = redis_manager.get_client()
        await client.setex(key, ttl, value)
        return True
    except Exception as e:
        logger.warning("Redis set failed", error=str(e))
        return False


async def _get_from_memory(user_id: str) -> str | None:
    """Get learning track from in-memory cache."""
    async with _cache_lock:
        if user_id in _memory_cache:
            track, expiry = _memory_cache[user_id]
            if time.time() < expiry:
                return cast(str | None, track)
            else:
                # Expired, remove from cache
                del _memory_cache[user_id]
    return None


async def _set_in_memory(user_id: str, track: str | None) -> None:
    """Set learning track in in-memory cache."""
    async with _cache_lock:
        expiry = time.time() + LEARNING_TRACK_CACHE_TTL
        _memory_cache[user_id] = (track, expiry)


async def _fetch_learning_track_from_lms(token: str) -> str | None:
    """Fetch the student's learning track from the LMS API."""
    onboarding_endpoint = f"{LMS_API_URL}/api/v1/onboarding"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                onboarding_endpoint,
                headers={"accept": "*/*", "Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            data = response.json()

            # Extract learning track from onboarding data
            onboarding_data = data.get("onboarding", {})
            learning_track = cast(str | None, onboarding_data.get("learningTrack"))

            logger.info(
                "Fetched learning track from LMS", learning_track=learning_track
            )
            return learning_track

    except httpx.HTTPStatusError as e:
        logger.error(
            "HTTP error fetching learning track", status_code=e.response.status_code
        )
        return None
    except httpx.TimeoutException:
        logger.error("Timeout while fetching learning track")
        return None
    except Exception as e:
        logger.error("Unexpected error fetching learning track", error=str(e))
        return None


async def get_cached_learning_track(user_id: str, token: str) -> str | None:
    """Get the student's learning track, using cache when available.

    Cache lookup order:
    1. Redis (if available)
    2. In-memory cache
    3. LMS API (then cache the result)

    Args:
        user_id: The user's unique identifier
        token: JWT bearer token for LMS API authentication

    Returns:
        The learning track string or None if not found
    """
    cache_key = _get_cache_key(user_id)

    # Try Redis first
    cached = await _get_from_redis(cache_key)
    if cached is not None:
        logger.debug("Learning track cache hit (Redis)", user_id=user_id)
        return cached if cached != "__none__" else None

    # Try in-memory cache
    cached = await _get_from_memory(user_id)
    if cached is not None:
        logger.debug("Learning track cache hit (memory)", user_id=user_id)
        return cached

    # Cache miss - fetch from LMS
    logger.info("Learning track cache miss, fetching from LMS", user_id=user_id)
    learning_track = await _fetch_learning_track_from_lms(token)

    # Cache the result (even if None, to avoid repeated failed lookups)
    cache_value = learning_track if learning_track else "__none__"
    await _set_in_redis(cache_key, cache_value)
    await _set_in_memory(user_id, learning_track)

    return learning_track


async def get_cached_advisor(
    user_id: str, token: str
) -> tuple[dict[str, Any], str | None]:
    """Get the student's career advisor, using cache when available.

    Args:
        user_id: The user's unique identifier
        token: JWT bearer token for LMS API authentication

    Returns:
        Tuple of (advisor_dict, learning_track)
    """
    advisor_cache_key = _get_advisor_cache_key(user_id)

    # Try to get cached advisor from Redis
    cached_advisor = await _get_from_redis(advisor_cache_key)
    if cached_advisor:
        try:
            advisor_data = json.loads(cached_advisor)
            logger.debug("Advisor cache hit (Redis)", user_id=user_id)
            return advisor_data["advisor"], advisor_data.get("learning_track")
        except (json.JSONDecodeError, KeyError):
            pass

    # Get learning track (which has its own caching)
    learning_track = await get_cached_learning_track(user_id, token)

    # Get advisor based on track
    if learning_track:
        advisor = get_advisor_by_track(learning_track)
        if not advisor:
            advisor = get_default_advisor()
    else:
        advisor = get_default_advisor()

    # Cache the advisor in Redis
    advisor_data = {
        "advisor": advisor,
        "learning_track": learning_track,
    }
    await _set_in_redis(advisor_cache_key, json.dumps(advisor_data))

    return advisor, learning_track


async def invalidate_user_cache(user_id: str) -> None:
    """Invalidate all cached data for a user.

    Call this when:
    - User updates their learning track
    - User completes onboarding
    - Admin resets user data
    """
    track_key = _get_cache_key(user_id)
    advisor_key = _get_advisor_cache_key(user_id)

    # Clear Redis cache
    if redis_manager.is_available():
        try:
            client = redis_manager.get_client()
            await client.delete(track_key, advisor_key)
            logger.info("Invalidated Redis cache", user_id=user_id)
        except Exception as e:
            logger.warning("Failed to invalidate Redis cache", error=str(e))

    # Clear in-memory cache
    async with _cache_lock:
        _memory_cache.pop(user_id, None)

    logger.info("Invalidated all caches", user_id=user_id)


def clear_memory_cache() -> None:
    """Clear the entire in-memory cache. Useful for testing."""
    global _memory_cache
    _memory_cache = {}

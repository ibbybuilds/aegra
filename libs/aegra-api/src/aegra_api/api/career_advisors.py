"""Career advisors API endpoints.

Provides endpoints for:
- GET /career-advisors - Get all career advisors
- GET /career-advisors/me - Get the student's assigned career advisor based on their learning track
- POST /career-advisors/refresh - Invalidate cache and refresh advisor assignment
"""

import structlog
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from aegra_api.core.auth_deps import get_current_user
from aegra_api.data.career_advisors import get_all_advisors
from aegra_api.models import User
from aegra_api.services.advisor_cache import get_cached_advisor, invalidate_user_cache

router = APIRouter()
logger = structlog.getLogger(__name__)


class CareerAdvisor(BaseModel):
    """Career advisor response model."""

    id: str
    track: str
    name: str
    title: str
    experience: str
    personality: str
    expertise_areas: list[str]
    communication_style: str
    background: str


class CareerAdvisorListResponse(BaseModel):
    """Response model for listing all career advisors."""

    advisors: list[CareerAdvisor]
    total: int


class StudentAdvisorResponse(BaseModel):
    """Response model for getting the student's assigned advisor."""

    advisor: CareerAdvisor
    learning_track: str | None
    message: str
    cached: bool = True  # Indicates if the response came from cache


class CacheInvalidationResponse(BaseModel):
    """Response model for cache invalidation."""

    success: bool
    message: str


@router.get("/career-advisors", response_model=CareerAdvisorListResponse)
async def list_career_advisors(
    _user: User = Depends(get_current_user),
) -> CareerAdvisorListResponse:
    """Get all available career advisors.

    Returns a list of all career advisors with their profiles and expertise areas.
    Each advisor is specialized for a specific learning track.
    """
    advisors = get_all_advisors()
    return CareerAdvisorListResponse(
        advisors=[CareerAdvisor(**advisor) for advisor in advisors],
        total=len(advisors),
    )


@router.get("/career-advisor/me", response_model=StudentAdvisorResponse)
async def get_my_career_advisor(
    user: User = Depends(get_current_user),
    authorization: str | None = Header(None),
) -> StudentAdvisorResponse:
    """Get the career advisor assigned to the current student.

    The advisor is determined by the student's enrolled learning track.
    Uses caching (Redis + in-memory) to avoid repeated LMS API calls.
    If no track is found, returns the default advisor (Alex Chen - Data Analytics).
    """
    # Extract token from authorization header
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ", 1)[1]
        advisor, learning_track = await get_cached_advisor(user.identity, token)

        track_display = (
            learning_track.replace("-", " ").title() if learning_track else None
        )
        message = (
            f"Your career advisor is {advisor['name']}, specialized in {track_display}."
            if learning_track
            else "Your career advisor is Alex Chen. Complete your onboarding to get a specialized advisor for your learning track."
        )

        return StudentAdvisorResponse(
            advisor=CareerAdvisor(**advisor),
            learning_track=learning_track,
            message=message,
        )

    # No authorization - return default advisor
    from aegra_api.data.career_advisors import get_default_advisor

    default_advisor = get_default_advisor()
    return StudentAdvisorResponse(
        advisor=CareerAdvisor(**default_advisor),
        learning_track=None,
        message="Your career advisor is Alex Chen. Complete your onboarding to get a specialized advisor for your learning track.",
        cached=False,
    )


@router.post("/career-advisors/refresh", response_model=CacheInvalidationResponse)
async def refresh_advisor_cache(
    user: User = Depends(get_current_user),
) -> CacheInvalidationResponse:
    """Invalidate the cached advisor data for the current user.

    Call this endpoint when:
    - User updates their learning track
    - User completes onboarding
    - User wants to refresh their advisor assignment

    After invalidation, the next call to /career-advisors/me will fetch fresh data from the LMS.
    """
    await invalidate_user_cache(user.identity)
    logger.info(f"Cache invalidated for user {user.identity}")

    return CacheInvalidationResponse(
        success=True,
        message="Advisor cache invalidated. Your next request will fetch fresh data.",
    )

"""API endpoints for Opportunity Discovery."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth_deps import get_current_user
from ..core.orm import get_session
from ..models import User
from ..core.accountability_orm import DiscoveredOpportunity
from ..services.opportunity_service import OpportunityService
from ..services.opportunity_discovery import opportunity_engine

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


# ============================================================================
# Pydantic Models
# ============================================================================


class OpportunityResponse(BaseModel):
    id: str
    opportunity_type: str  # 'event' or 'job'
    title: str
    description: str | None
    url: str | None
    location: str | None
    event_date: str | None
    company: str | None
    salary_range: str | None
    match_score: float | None
    matched_track: str | None
    status: str
    discovered_at: str
    expires_at: str | None
    metadata: dict

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_model(cls, opp: DiscoveredOpportunity) -> "OpportunityResponse":
        return cls(
            id=opp.id,
            opportunity_type=opp.opportunity_type,
            title=opp.title,
            description=opp.description,
            url=opp.url,
            location=opp.location,
            event_date=opp.event_date.isoformat() if opp.event_date else None,
            company=opp.company,
            salary_range=opp.salary_range,
            match_score=float(opp.match_score) if opp.match_score else None,
            matched_track=opp.matched_track,
            status=opp.status,
            discovered_at=opp.discovered_at.isoformat(),
            expires_at=opp.expires_at.isoformat() if opp.expires_at else None,
            metadata=opp.metadata_json or {},
        )


class OpportunityListResponse(BaseModel):
    opportunities: list[OpportunityResponse]
    total: int
    has_more: bool


class DiscoverRequest(BaseModel):
    auth_token: str  # LMS auth token for fetching enrollments


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("", response_model=OpportunityListResponse)
async def list_opportunities(
    opportunity_type: str | None = Query(None, description="Filter by type: 'event' or 'job'"),
    status: str = Query("new", description="Filter by status: new, notified, dismissed, applied"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List discovered opportunities for the current user."""
    opportunities, total, has_more = await OpportunityService.list_opportunities(
        session=session,
        user_id=user.identity,
        opportunity_type=opportunity_type,
        status=status,
        limit=limit,
        offset=offset,
    )

    return {
        "opportunities": [OpportunityResponse.from_orm_model(o) for o in opportunities],
        "total": total,
        "has_more": has_more,
    }


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> OpportunityResponse:
    """Get a single opportunity by ID."""
    opportunity = await OpportunityService.get_opportunity(
        session, opportunity_id, user.identity
    )

    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")

    return OpportunityResponse.from_orm_model(opportunity)


@router.post("/{opportunity_id}/dismiss")
async def dismiss_opportunity(
    opportunity_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Mark an opportunity as dismissed (not interested)."""
    try:
        return await OpportunityService.dismiss_opportunity(
            session, opportunity_id, user.identity
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{opportunity_id}/applied")
async def mark_applied(
    opportunity_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Mark an opportunity as applied (for jobs)."""
    try:
        return await OpportunityService.mark_opportunity_applied(
            session, opportunity_id, user.identity
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/discover")
async def trigger_discovery(
    request: DiscoverRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Manually trigger opportunity discovery for the current user.

    This endpoint searches for events and jobs matching the user's
    enrolled courses and location.

    Note: Normally this runs as a scheduled background job, but this
    endpoint allows manual triggering.
    """
    discovered = await opportunity_engine.discover_for_user(
        session=session,
        user_id=user.identity,
        auth_token=request.auth_token,
    )

    # Create notifications for new opportunities
    for opp in discovered:
        await opportunity_engine.create_opportunity_notification(session, opp)

    return {
        "status": "success",
        "discovered_count": len(discovered),
        "events": len([o for o in discovered if o.opportunity_type == "event"]),
        "jobs": len([o for o in discovered if o.opportunity_type == "job"]),
    }

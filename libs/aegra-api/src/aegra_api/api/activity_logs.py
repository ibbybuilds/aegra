"""Activity log endpoints for retrieving student activity and metrics"""

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.auth_deps import get_current_user
from aegra_api.core.orm import get_session
from aegra_api.models import User
from aegra_api.models.activity_logs import (
    ActivityLogListResponse,
    ActivityLogResponse,
)
from aegra_api.services.activity_service import ActivityService

router = APIRouter(prefix="/api/v1/activity-logs", tags=["Activity Logs"])

logger = structlog.getLogger(__name__)


def require_admin_role(user: User = Depends(get_current_user)) -> User:
    """
    Dependency to ensure user has admin or superadmin role.
    Raises 403 Forbidden if user doesn't have required role.
    """
    user_role = getattr(user, "role", None) or (
        getattr(user, "permissions", [])[0]
        if getattr(user, "permissions", None)
        else None
    )

    if user_role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=403,
            detail=f"Admin access required. Your role: {user_role or 'user'}",
        )

    return user


@router.get(
    "/user/{user_id}",
    response_model=ActivityLogListResponse,
    description="Retrieve activity logs for a specific user (Admin only)",
)
async def get_user_activity_logs(
    user_id: str,
    limit: int = Query(50, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    action_type: str | None = Query(None, description="Filter by action type"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> ActivityLogListResponse:
    """
    Get activity logs for a specific user/student.

    **Query Parameters:**
    - `limit`: Maximum number of results (default: 50, max: 1000)
    - `offset`: Pagination offset (default: 0)
    - `action_type`: Filter by action type (e.g., 'prompt', 'query', 'run_started')
    - `start_date`: Filter logs from this date onwards (ISO format)
    - `end_date`: Filter logs up to this date (ISO format)

    **Returns:**
    - `logs`: List of activity log entries
    - `total`: Total number of matching logs
    - `limit`: The limit used
    - `offset`: The offset used
    """
    logs, total = await ActivityService.get_user_activity_logs(
        session=session,
        user_id=user_id,
        limit=limit,
        offset=offset,
        action_type=action_type,
        start_date=start_date,
        end_date=end_date,
    )

    return ActivityLogListResponse(
        logs=[ActivityLogResponse(**log.model_dump()) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/",
    response_model=ActivityLogListResponse,
    description="Retrieve activity logs with filters (Admin only)",
)
async def get_activity_logs(
    user_id: str | None = Query(None, description="Filter by user ID"),
    assistant_id: str | None = Query(None, description="Filter by assistant ID"),
    action_type: str | None = Query(None, description="Filter by action type"),
    action_status: str | None = Query(None, description="Filter by action status"),
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results offset"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> ActivityLogListResponse:
    """
    Get activity logs with multiple filter options.

    **Query Parameters:**
    - `user_id`: Filter by specific user
    - `assistant_id`: Filter by specific assistant
    - `action_type`: Filter by action type
    - `action_status`: Filter by action status
    - `start_date`: Start date filter (ISO format)
    - `end_date`: End date filter (ISO format)
    - `limit`: Maximum results (default: 50, max: 1000)
    - `offset`: Pagination offset (default: 0)

    **Returns:**
    - `logs`: List of matching activity log entries
    - `total`: Total number of matching logs
    - `limit`: The limit used
    - `offset`: The offset used
    """
    logs, total = await ActivityService.get_activity_logs(
        session=session,
        user_id=user_id,
        assistant_id=assistant_id,
        action_type=action_type,
        action_status=action_status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    return ActivityLogListResponse(
        logs=[ActivityLogResponse(**log.model_dump()) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/user/{user_id}/summary",
    description="Get activity summary for a user (Admin only)",
)
async def get_user_activity_summary(
    user_id: str,
    start_date: datetime | None = Query(None, description="Filter by start date"),
    end_date: datetime | None = Query(None, description="Filter by end date"),
    session: AsyncSession = Depends(get_session),
    _current_user: User = Depends(require_admin_role),
) -> dict:
    """
    Get activity summary statistics for a specific user.

    **Query Parameters:**
    - `start_date`: Start date for filtering (ISO format)
    - `end_date`: End date for filtering (ISO format)

    **Returns:**
    - `total_activities`: Total number of activities
    - `action_counts`: Dictionary with counts per action type
    - `status_counts`: Dictionary with counts per action status
    - `assistant_counts`: Dictionary with counts per assistant
    """
    summary = await ActivityService.get_user_activity_summary(
        session=session,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )

    return summary

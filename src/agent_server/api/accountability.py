"""API Router for Accountability features."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth_deps import get_current_user
from ..core.orm import get_session
from ..models import User
from ..services.accountability_service import AccountabilityService

router = APIRouter(tags=["Accountability"])


# Pydantic models for API
class ActionItemResponse(BaseModel):
    id: str
    description: str
    status: str
    due_date: datetime | None = None
    priority: str
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationResponse(BaseModel):
    id: str
    title: str
    content: str
    priority: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/action-items", response_model=list[ActionItemResponse])
async def list_action_items(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
) -> Any:
    """List active action items for the current user."""
    return await AccountabilityService.list_action_items(session, user.identity)


@router.post("/action-items/{item_id}")
async def update_action_item(
    item_id: str,
    status: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await AccountabilityService.update_action_item_status(
            session, item_id, user.identity, status
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Any:
    """List pending notifications for the current user."""
    return await AccountabilityService.list_notifications(session, user.identity, limit)


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return await AccountabilityService.mark_notification_read(
            session, notification_id, user.identity
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

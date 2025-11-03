"""Activity log-related Pydantic models"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActivityLogCreate(BaseModel):
    """Request model for creating activity logs"""

    user_id: str = Field(..., description="User/student ID")
    assistant_id: str | None = Field(None, description="Associated assistant ID")
    thread_id: str | None = Field(None, description="Associated thread ID")
    run_id: str | None = Field(None, description="Associated run ID")
    action_type: str = Field(
        ...,
        description="Type of action (e.g., 'prompt', 'query', 'run_started', 'run_completed', 'run_failed')",
    )
    action_status: str = Field("success", description="Status of the action")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional details about the action"
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict, description="Metadata for the action"
    )


class ActivityLog(BaseModel):
    """Activity log entity model"""

    activity_id: str
    user_id: str
    assistant_id: str | None
    thread_id: str | None
    run_id: str | None
    action_type: str
    action_status: str
    details: dict[str, Any] = {}
    metadata_json: dict[str, Any] = {}
    created_at: datetime

    class Config:
        from_attributes = True


class ActivityLogResponse(BaseModel):
    """Response model for activity log endpoints"""

    activity_id: str
    user_id: str
    assistant_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None
    action_type: str
    action_status: str
    details: dict[str, Any] = {}
    metadata_json: dict[str, Any] = {}
    created_at: datetime


class ActivityLogListResponse(BaseModel):
    """Response model for listing activity logs"""

    logs: list[ActivityLogResponse]
    total: int
    limit: int
    offset: int


class ActivityLogFilterRequest(BaseModel):
    """Request model for filtering activity logs"""

    user_id: str | None = Field(None, description="Filter by user ID")
    assistant_id: str | None = Field(None, description="Filter by assistant ID")
    action_type: str | None = Field(None, description="Filter by action type")
    action_status: str | None = Field(None, description="Filter by action status")
    start_date: datetime | None = Field(None, description="Filter by start date")
    end_date: datetime | None = Field(None, description="Filter by end date")
    limit: int = Field(50, ge=1, le=1000, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Results offset")
    sort_by: str = Field("created_at", description="Field to sort by")
    sort_order: str = Field("DESC", description="Sort order: ASC or DESC")

"""Thread-related Pydantic models for Agent Protocol"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    """Request model for creating threads"""

    metadata: dict[str, Any] | None = Field(None, description="Thread metadata")
    initial_state: dict[str, Any] | None = Field(
        None, description="LangGraph initial state"
    )


class Thread(BaseModel):
    """Thread entity model"""

    thread_id: str
    status: str = "idle"
    metadata: dict[str, Any] = Field(default_factory=dict)
    user_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class ThreadList(BaseModel):
    """Response model for listing threads"""

    threads: list[Thread]
    total: int


class ThreadSearchRequest(BaseModel):
    """Request model for thread search"""

    metadata: dict[str, Any] | None = Field(None, description="Metadata filters")
    status: str | None = Field(None, description="Thread status filter")
    limit: int | None = Field(20, le=100, ge=1, description="Maximum results")
    offset: int | None = Field(0, ge=0, description="Results offset")
    order_by: str | None = Field("created_at DESC", description="Sort order")


class ThreadSearchResponse(BaseModel):
    """Response model for thread search"""

    threads: list[Thread]
    total: int
    limit: int
    offset: int


class ThreadCheckpoint(BaseModel):
    """Checkpoint identifier for thread history"""

    checkpoint_id: str | None = None
    thread_id: str | None = None
    checkpoint_ns: str | None = ""


class ThreadCheckpointPostRequest(BaseModel):
    """Request model for fetching thread checkpoint"""

    checkpoint: ThreadCheckpoint = Field(description="Checkpoint to fetch")
    subgraphs: bool | None = Field(False, description="Include subgraph states")


class ThreadState(BaseModel):
    """Thread state model for history endpoint"""

    values: dict[str, Any] = Field(description="Channel values (messages, etc.)")
    next: list[str] = Field(default_factory=list, description="Next nodes to execute")
    tasks: list[dict[str, Any]] = Field(
        default_factory=list, description="Tasks to execute"
    )
    interrupts: list[dict[str, Any]] = Field(
        default_factory=list, description="Interrupt data"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Checkpoint metadata"
    )
    created_at: datetime | None = Field(None, description="Timestamp of state creation")
    checkpoint: ThreadCheckpoint = Field(description="Current checkpoint")
    parent_checkpoint: ThreadCheckpoint | None = Field(
        None, description="Parent checkpoint"
    )
    checkpoint_id: str | None = Field(
        None, description="Checkpoint ID (for backward compatibility)"
    )
    parent_checkpoint_id: str | None = Field(
        None, description="Parent checkpoint ID (for backward compatibility)"
    )


class ThreadHistoryRequest(BaseModel):
    """Request model for thread history endpoint"""

    limit: int | None = Field(
        10, ge=1, le=1000, description="Number of states to return"
    )
    before: str | None = Field(
        None, description="Return states before this checkpoint ID"
    )
    metadata: dict[str, Any] | None = Field(None, description="Filter by metadata")
    checkpoint: dict[str, Any] | None = Field(
        None, description="Checkpoint for subgraph filtering"
    )
    subgraphs: bool | None = Field(False, description="Include states from subgraphs")
    checkpoint_ns: str | None = Field(None, description="Checkpoint namespace")

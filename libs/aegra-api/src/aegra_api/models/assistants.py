"""Assistant-related Pydantic models for Agent Protocol"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AssistantCreate(BaseModel):
    """Request model for creating assistants"""

    assistant_id: str | None = Field(None, description="Unique assistant identifier (auto-generated if not provided)")
    name: str | None = Field(
        None,
        description="Human-readable assistant name (auto-generated if not provided)",
    )
    description: str | None = Field(None, description="Assistant description")
    config: dict[str, Any] | None = Field({}, description="Assistant configuration")
    context: dict[str, Any] | None = Field({}, description="Assistant context")
    graph_id: str = Field(..., description="LangGraph graph ID from aegra.json")
    metadata: dict[str, Any] | None = Field({}, description="Metadata to use for searching and filtering assistants.")
    if_exists: str | None = Field("error", description="What to do if assistant exists: error or do_nothing")


class Assistant(BaseModel):
    """Assistant entity model"""

    assistant_id: str
    name: str
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    graph_id: str
    user_id: str
    version: int = Field(..., description="The version of the assistant.")
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_dict")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AssistantUpdate(BaseModel):
    """Request model for creating assistants"""

    name: str | None = Field(None, description="The name of the assistant (auto-generated if not provided)")
    description: str | None = Field(None, description="The description of the assistant. Defaults to null.")
    config: dict[str, Any] | None = Field({}, description="Configuration to use for the graph.")
    graph_id: str = Field("agent", description="The ID of the graph")
    context: dict[str, Any] | None = Field(
        {},
        description="The context to use for the graph. Useful when graph is configurable.",
    )
    metadata: dict[str, Any] | None = Field({}, description="Metadata to use for searching and filtering assistants.")


class AssistantList(BaseModel):
    """Response model for listing assistants"""

    assistants: list[Assistant]
    total: int


class AssistantSearchRequest(BaseModel):
    """Request model for assistant search"""

    name: str | None = Field(None, description="Filter by assistant name")
    description: str | None = Field(None, description="Filter by assistant description")
    graph_id: str | None = Field(None, description="Filter by graph ID")
    limit: int | None = Field(20, le=100, ge=1, description="Maximum results")
    offset: int | None = Field(0, ge=0, description="Results offset")
    metadata: dict[str, Any] | None = Field({}, description="Metadata to use for searching and filtering assistants.")


class AgentSchemas(BaseModel):
    """Agent schema definitions for client integration"""

    input_schema: dict[str, Any] = Field(..., description="JSON Schema for agent inputs")
    output_schema: dict[str, Any] = Field(..., description="JSON Schema for agent outputs")
    state_schema: dict[str, Any] = Field(..., description="JSON Schema for agent state")
    config_schema: dict[str, Any] = Field(..., description="JSON Schema for agent config")

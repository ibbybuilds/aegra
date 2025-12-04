"""Run-related Pydantic models for Agent Protocol"""

from datetime import datetime
from typing import Any, Self

from pydantic import (
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from ..utils.status_compat import validate_run_status


class RunCreate(BaseModel):
    """Request model for creating runs"""

    assistant_id: str = Field(..., description="Assistant to execute")
    input: dict[str, Any] | None = Field(
        None,
        description="Input data for the run. Optional when resuming from a checkpoint.",
    )
    config: dict[str, Any] | None = Field({}, description="Execution config")
    context: dict[str, Any] | None = Field({}, description="Execution context")
    checkpoint: dict[str, Any] | None = Field(
        None,
        description="Checkpoint configuration (e.g., {'checkpoint_id': '...', 'checkpoint_ns': ''})",
    )
    stream: bool = Field(False, description="Enable streaming response")
    stream_mode: str | list[str] | None = Field(
        None, description="Requested stream mode(s)"
    )
    on_disconnect: str | None = Field(
        None,
        description="Behavior on client disconnect: 'cancel' or 'continue' (default).",
    )

    multitask_strategy: str | None = Field(
        None,
        description="Strategy for handling concurrent runs on same thread: 'reject', 'interrupt', 'rollback', or 'enqueue'.",
    )

    # Human-in-the-loop fields (core HITL functionality)
    command: dict[str, Any] | None = Field(
        None,
        description="Command for resuming interrupted runs with state updates or navigation",
    )
    interrupt_before: str | list[str] | None = Field(
        None,
        description="Nodes to interrupt immediately before they get executed. Use '*' for all nodes.",
    )
    interrupt_after: str | list[str] | None = Field(
        None,
        description="Nodes to interrupt immediately after they get executed. Use '*' for all nodes.",
    )

    # Subgraph configuration
    stream_subgraphs: bool | None = Field(
        False,
        description="Whether to include subgraph events in streaming. When True, includes events from all subgraphs. When False (default when None), excludes subgraph events. Defaults to False for backwards compatibility.",
    )

    # Request metadata (top-level in payload)
    metadata: dict[str, Any] | None = Field(
        None,
        description="Request metadata (e.g., from_studio flag)",
    )

    @model_validator(mode="after")
    def validate_input_command_exclusivity(self) -> Self:
        """Ensure input and command are mutually exclusive"""
        # Allow empty input dict when command is present (frontend compatibility)
        if self.input is not None and self.command is not None:
            # If input is just an empty dict, treat it as None for compatibility
            if self.input == {}:
                self.input = None
            else:
                raise ValueError(
                    "Cannot specify both 'input' and 'command' - they are mutually exclusive"
                )
        if self.input is None and self.command is None:
            raise ValueError("Must specify either 'input' or 'command'")
        return self


class Run(BaseModel):
    """Run entity model

    Status values: pending, running, error, success, timeout, interrupted
    """

    run_id: str
    thread_id: str
    assistant_id: str
    status: str = "pending"  # Valid values: pending, running, error, success, timeout, interrupted
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error_message: str | None = None
    config: dict[str, Any] | None = {}
    context: dict[str, Any] | None = {}
    user_id: str
    created_at: datetime
    updated_at: datetime

    @field_validator("context", mode="before")
    @classmethod
    def normalize_context(cls, v: Any) -> dict[str, Any] | None:
        """Ensure context is always a dict or None, never a CallContext object."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        # Convert CallContext or other objects to dict
        if hasattr(v, "model_dump"):
            return v.model_dump()  # type: ignore[no-any-return]
        if hasattr(v, "__dict__"):
            return v.__dict__  # type: ignore[no-any-return]
        # Fallback: try to convert to dict
        try:
            return dict(v) if v else None
        except (TypeError, ValueError):
            return None

    @field_serializer("context")
    def serialize_context(self, value: Any) -> dict[str, Any] | None:
        """Ensure context is serialized as a dict or None, never as a CallContext object.

        This serializer handles cases where CallContext objects might leak through
        from database deserialization or other sources during response serialization.
        """
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        # Convert CallContext or other objects to dict during serialization
        if hasattr(value, "model_dump"):
            return value.model_dump()  # type: ignore[no-any-return]
        if hasattr(value, "dict"):
            return value.dict()  # type: ignore[no-any-return]
        if hasattr(value, "__dict__"):
            return value.__dict__  # type: ignore[no-any-return]
        # Fallback: try to convert to dict
        try:
            return dict(value) if value else None
        except (TypeError, ValueError):
            # Last resort: return empty dict instead of failing
            return {}

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status conforms to API specification."""
        if not isinstance(v, str):
            raise ValueError(f"Status must be a string, got {type(v)}")
        return validate_run_status(v)

    class Config:
        from_attributes = True


class RunStatus(BaseModel):
    """Simple run status response"""

    run_id: str
    status: str  # Standard status value

    message: str | None = None

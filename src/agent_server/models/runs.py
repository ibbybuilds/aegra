"""Run-related Pydantic models for Agent Protocol"""

from datetime import datetime
from typing import Any, Self

from pydantic import (
    BaseModel,
    Field,
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

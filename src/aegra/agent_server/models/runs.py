"""Run-related Pydantic models for Agent Protocol"""

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


class RunCreate(BaseModel):
    """Request model for creating runs"""

    assistant_id: str = Field(..., description="Assistant to execute")
    input: dict[str, Any] | None = Field(
        None,
        description="Input data for the run. Optional when resuming from a checkpoint.",
    )
    config: dict[str, Any] | None = Field({}, description="LangGraph execution config")
    context: dict[str, Any] | None = Field(
        {}, description="LangGraph execution context"
    )
    checkpoint: dict[str, Any] | None = Field(
        None,
        description="Checkpoint configuration (e.g., {'checkpoint_id': '...', 'checkpoint_ns': ''})",
    )
    stream: bool = Field(False, description="Enable streaming response")
    stream_mode: str | list[str] | None = Field(
        None, description="Requested stream mode(s) as per LangGraph"
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
    """Run entity model"""

    run_id: str
    thread_id: str
    assistant_id: str
    status: str = "pending"  # pending, running, completed, failed, cancelled
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    error_message: str | None = None
    config: dict[str, Any] | None = {}
    context: dict[str, Any] | None = {}
    user_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RunStatus(BaseModel):
    """Simple run status response"""

    run_id: str
    status: str
    message: str | None = None

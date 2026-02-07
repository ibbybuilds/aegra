"""Define the state structures for the agent."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages
from langgraph.managed import IsLastStep


def merge_tool_counts(existing: dict[str, int], new: dict[str, int]) -> dict[str, int]:
    """Merge tool call counts by taking the maximum value for each tool.

    This ensures that when state updates happen, we preserve the highest count
    seen for each tool, preventing the counter from resetting.
    """
    if not existing:
        return new
    if not new:
        return existing

    merged = existing.copy()
    for tool_name, count in new.items():
        merged[tool_name] = max(merged.get(tool_name, 0), count)
    return merged


@dataclass
class InputState:
    """Defines the input state for the agent, representing a narrower interface to the outside world.

    This class is used to define the initial state and structure of incoming data.
    """

    messages: Annotated[Sequence[AnyMessage], add_messages] = field(default_factory=list)
    """
    Messages tracking the primary execution state of the agent.

    Typically accumulates a pattern of:
    1. HumanMessage - user input
    2. AIMessage with .tool_calls - agent picking tool(s) to use to collect information
    3. ToolMessage(s) - the responses (or errors) from the executed tools
    4. AIMessage without .tool_calls - agent responding in unstructured format to the user
    5. HumanMessage - user responds with the next conversational turn

    Steps 2-5 may repeat as needed.

    The `add_messages` annotation ensures that new messages are merged with existing ones,
    updating by ID to maintain an "append-only" state unless a message with the same ID is provided.
    """


@dataclass
class State(InputState):
    """Represents the complete state of the agent, extending InputState with additional attributes.

    This class can be used to store any information needed throughout the agent's lifecycle.
    """

    is_last_step: IsLastStep = field(default=False)
    """
    Indicates whether the current step is the last one before the graph raises an error.

    This is a 'managed' variable, controlled by the state machine rather than user code.
    It is set to 'True' when the step count reaches recursion_limit - 1.
    """

    tool_call_counts: Annotated[dict[str, int], merge_tool_counts] = field(
        default_factory=dict
    )
    """
    Tracks the number of times each tool has been called in this run.

    Used to enforce limits on expensive or data-heavy tools like get_student_ai_career_advisor_onboarding.
    The merge_tool_counts reducer ensures counts are preserved across state updates.
    """

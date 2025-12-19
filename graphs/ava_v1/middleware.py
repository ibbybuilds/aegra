"""Middleware configuration for ava_v1 agent."""

from typing import Any, cast

from langchain.agents.middleware import ModelRequest, dynamic_prompt

from ava_v1.context import CallContext
from ava_v1.prompts.template import get_customized_prompt


def extract_call_context(request: ModelRequest) -> CallContext | None:
    """Extract CallContext from ModelRequest, preferring runtime.context over state.

    This helper function extracts call context from the ModelRequest object.
    It's separated for testability and clarity.

    Args:
        request: ModelRequest-like object with runtime and/or state attributes

    Returns:
        CallContext instance, dict converted to CallContext, or None
    """
    call_context: CallContext | dict[str, Any] | None = None

    # PREFERRED: Access context via runtime.context (proper LangGraph pattern)
    if (
        hasattr(request, "runtime")
        and request.runtime is not None
        and hasattr(request.runtime, "context")
        and request.runtime.context is not None
    ):
        call_context = request.runtime.context

    # FALLBACK: Access context from state (for backward compatibility with aegra)
    if (
        call_context is None
        and hasattr(request, "state")
        and isinstance(request.state, dict)
    ):
        raw_context = request.state.get("call_context")
        if raw_context is not None:
            call_context = raw_context

    # Convert dict to CallContext if needed
    if isinstance(call_context, dict):
        # Filter out unknown keys to avoid TypeErrors
        valid_keys = {
            "type",
            "property",
            "payment",
            "session",
            "booking",
            "abandoned_payment",
            "user_phone",
            "thread_id",
            "call_reference",
            "dial_map_session_id",
        }
        filtered_context = {k: v for k, v in call_context.items() if k in valid_keys}
        return CallContext(**filtered_context)

    return cast("CallContext | None", call_context)


@dynamic_prompt
def customize_agent_prompt(request: ModelRequest) -> str:
    """Dynamically customize system prompt based on runtime context.

    This middleware accesses call_context from runtime.context (preferred) or state (fallback)
    and uses it to customize the agent's system prompt according to the 8-level priority system.

    According to LangChain docs:
    - @dynamic_prompt REPLACES the entire system prompt
    - Access context via request.runtime.context (preferred) or request.state (fallback)
    - Must return the FULL prompt string (base + customization or standalone)

    Args:
        request: ModelRequest containing state, runtime, and system_prompt

    Returns:
        Customized system prompt string
    """
    # Extract context using helper function (enables testing)
    call_context = extract_call_context(request)

    # Get customized prompt using priority system and template rendering
    return get_customized_prompt(call_context)


__all__ = ["customize_agent_prompt"]

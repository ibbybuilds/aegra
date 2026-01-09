"Middleware configuration for ava_v1 agent."

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    dynamic_prompt,
)
from langchain_core.messages import SystemMessage, ToolMessage

from ava_v1.context import CallContext
from ava_v1.prompts.template import get_customized_prompt

# Error types that trigger a forced silent retry
# These are errors where the agent can self-correct parameters
FIXABLE_ERRORS = {
    "invalid_input",
    "validation_error",
    "missing_parameter",
    "format_error",
    "api_timeout",
    "rate_limit",
    "server_error",
    "invalid_hotel_id",
    "invalid_payment_type",
    "name_lookup_failed",
    "token_mismatch",
}


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


class ForcedRetryMiddleware(AgentMiddleware):
    """Middleware to force silent retries on fixable tool errors.

    Inspects the last message before the model runs. If it's a ToolMessage
    with a fixable error (e.g., validation error, missing param), it injects
    a system instruction to force the agent to retry SILENTLY (no text generation).
    """

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Intercept model call to check for retryable errors."""
        # Get the last message in the history
        messages = request.messages
        if not messages:
            return await handler(request)

        last_msg = messages[-1]

        # Check if it's a ToolMessage with an error
        if isinstance(last_msg, ToolMessage) and last_msg.content:
            try:
                # Parse tool content (usually JSON string)
                content_str = str(last_msg.content)
                # Handle potential non-JSON content gracefully
                if content_str.strip().startswith("{"):
                    data = json.loads(content_str)
                    
                    # Check for error status
                    if isinstance(data, dict) and data.get("status") == "error":
                        error_info = data.get("error", {})
                        error_type = error_info.get("type") if isinstance(error_info, dict) else None
                        
                        # Check if this is a "fixable" error
                        if error_type in FIXABLE_ERRORS:
                            error_msg = error_info.get("message", "Unknown error")
                            
                            # Construct the strict silent-retry instruction
                            retry_instruction = (
                                f"\n\nSYSTEM INSTRUCTION: The previous tool call failed with error type '{error_type}': {error_msg}. "
                                "You must immediately RETRY the tool call with corrected parameters. "
                                "DO NOT output any text, apology, or explanation. "
                                "Output ONLY the corrected Tool Call."
                            )
                            
                            # Append to system message (ephemeral override)
                            current_system = request.system_message
                            if current_system:
                                new_content = current_system.content + retry_instruction
                                request = request.override(
                                    system_message=SystemMessage(content=new_content),
                                    # Force tool use to discourage chatter
                                    tool_choice="any" 
                                )
            except Exception:
                # If parsing fails or any other error, pass through normally
                pass

        return await handler(request)


__all__ = ["customize_agent_prompt", "ForcedRetryMiddleware"]
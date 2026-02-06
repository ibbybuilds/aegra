"""Model Armor middleware for content policy enforcement on LLM calls."""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    after_model,
    hook_config,
)
from langchain_core.messages import AIMessage, HumanMessage

from ava_v1.shared_libraries.model_armor_client import (
    ModelArmorConfigError,
    ModelArmorViolationError,
    _get_model_armor_config,
    sanitize_model_response,
    sanitize_user_prompt,
)

logger = logging.getLogger(__name__)

# Marker for blocked messages
MODEL_ARMOR_BLOCKED_MARKER = "MODEL_ARMOR_BLOCKED"


@after_model
def check_for_model_armor_block(state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
    """After-model hook to emit proper messages/partial events for Model Armor violations.

    When Model Armor blocks a request, the middleware returns a clean message which gets
    streamed as an "updates" event. This hook detects that message and emits it again
    as a "messages/partial" event for proper TTS support in conversation-relay.

    Args:
        state: Current agent state with messages
        runtime: Runtime context

    Returns:
        None (we emit streaming events but don't modify state to avoid duplicates)
    """
    messages = state.get("messages")
    if not messages:
        return None

    # Get the last message from the state
    last_message = messages[-1]

    # Check if this is the Model Armor violation message
    # (We recognize it by the content since we no longer use a marker)
    if isinstance(last_message, AIMessage) and last_message.content == "I'm sorry, I cannot assist with that request.":
        logger.debug("[MODEL_ARMOR] Detected violation message, emitting as messages/partial event")

        # Emit as messages/partial event for TTS support
        try:
            if hasattr(runtime, "stream_writer") and runtime.stream_writer:
                runtime.stream_writer(("messages/partial", [last_message.model_dump()]))
                logger.debug("[MODEL_ARMOR] Emitted messages/partial event for TTS")
        except Exception as e:
            logger.warning(f"[MODEL_ARMOR] Failed to emit messages event: {e}")

        # Don't return state update - message is already in state, we just emitted the event
        return None

    return None


class ModelArmorMiddleware(AgentMiddleware):
    """Middleware to enforce content policy using Google Model Armor.

    This middleware intercepts LLM calls to:
    1. Check user prompts before sending to the model (pre-call sanitization)
    2. Check model responses before returning to the user (post-call sanitization)

    If content violates policy, the middleware blocks the request/response
    and returns a safe error message to the user.

    Configuration is validated at initialization (fail-fast).
    """

    def __init__(self):
        """Initialize middleware and validate configuration.

        Raises:
            ModelArmorConfigError: If configuration is invalid
        """
        # Validate config at startup (fail fast)
        self.config = _get_model_armor_config()

        if self.config["enabled"]:
            logger.info(
                f"[MODEL_ARMOR] Middleware enabled "
                f"(project={self.config['project_id']}, "
                f"location={self.config['location']}, "
                f"template={self.config['template_id']}, "
                f"timeout={self.config['timeout']}s, "
                f"fail_open={self.config['fail_open']})"
            )
        else:
            logger.info("[MODEL_ARMOR] Middleware disabled")

    def _extract_last_user_message(self, request: ModelRequest) -> str | None:
        """Extract the last user message from the request.

        Args:
            request: ModelRequest containing messages

        Returns:
            Last HumanMessage content as string, or None if not found
        """
        messages = request.messages
        if not messages:
            return None

        # Find last HumanMessage
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = msg.content

                # Handle string content
                if isinstance(content, str):
                    return content

                # Handle multimodal content (list of dicts)
                if isinstance(content, list):
                    # Extract text parts from multimodal content
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    return " ".join(text_parts) if text_parts else None

        return None

    def _extract_model_response_text(self, response: ModelResponse) -> str | None:
        """Extract model response text from ModelResponse.

        Args:
            response: ModelResponse containing result messages

        Returns:
            AIMessage content as string, or None if not found
        """
        # ModelResponse.result is a list of messages
        if not response.result:
            return None

        # Get the last message (usually the AI response)
        last_message = response.result[-1]
        if isinstance(last_message, AIMessage):
            content = last_message.content
            if isinstance(content, str):
                return content

        return None

    def _create_violation_response(
        self, request: ModelRequest
    ) -> ModelResponse:
        """Create a ModelResponse with clean violation message for policy violations.

        Note: Middleware responses are streamed as "updates" events, but conversation-relay
        needs "messages" events for TTS. We emit a manual messages/partial event via
        stream_writer if available (handled by after_model hook).

        Args:
            request: Original ModelRequest

        Returns:
            ModelResponse with AIMessage containing the violation message
        """
        # Return the clean message directly
        ai_message = AIMessage(content="I'm sorry, I cannot assist with that request.")

        return ModelResponse(
            result=[ai_message],
        )

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Intercept model call to enforce content policy.

        Flow:
        1. Skip if middleware is disabled
        2. Extract last user message from request
        3. Sanitize user prompt (pre-call check)
        4. If violation: return error response (don't call model)
        5. Call model via handler
        6. Extract model response text
        7. Sanitize model response (post-call check)
        8. If violation: return safe generic response
        9. Return response

        Args:
            request: ModelRequest containing messages and config
            handler: Function to call the actual model

        Returns:
            ModelResponse from model or safe error response

        Raises:
            ModelArmorConfigError: If API unavailable and fail_open=false
        """
        # Skip if disabled
        if not self.config["enabled"]:
            return await handler(request)

        # Extract last user message
        user_message = self._extract_last_user_message(request)
        if not user_message:
            logger.debug(
                "[MODEL_ARMOR] No user message found in request, skipping sanitization"
            )
            return await handler(request)

        # Sanitize user prompt (pre-call)
        try:
            await sanitize_user_prompt(user_message)
        except ModelArmorViolationError as e:
            # User prompt violated policy - block request
            logger.warning(
                f"[MODEL_ARMOR] User prompt blocked: {e.filter_results.get('reason', 'Unknown')}"
            )
            return self._create_violation_response(request)
        except ModelArmorConfigError as e:
            # API error - fail closed by default (already logged in client)
            # Re-raise to abort request (don't call model)
            raise

        # Call model
        response = await handler(request)

        # Extract model response text
        response_text = self._extract_model_response_text(response)
        if not response_text:
            logger.debug(
                "[MODEL_ARMOR] No model response text found, skipping sanitization"
            )
            return response

        # Sanitize model response (post-call)
        try:
            await sanitize_model_response(response_text)
        except ModelArmorViolationError as e:
            # Model response violated policy - block response
            logger.warning(
                f"[MODEL_ARMOR] Model response blocked: {e.filter_results.get('reason', 'Unknown')}"
            )
            return self._create_violation_response(request)
        except ModelArmorConfigError as e:
            # API error - fail closed by default (already logged in client)
            # Re-raise to abort response
            raise

        return response


__all__ = ["ModelArmorMiddleware", "check_for_model_armor_block"]

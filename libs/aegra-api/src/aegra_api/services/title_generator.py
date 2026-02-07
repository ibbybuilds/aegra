"""Service for generating AI-powered thread titles."""

from typing import Any

import structlog
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage

from aegra_api.settings import settings

logger = structlog.getLogger(__name__)

# Default model for title generation (lightweight and fast)
DEFAULT_TITLE_MODEL = settings.app.TITLE_GENERATOR_MODEL


def extract_first_user_message(input_data: dict[str, Any]) -> str | None:
    """Extract the first user message from input data.

    Args:
        input_data: The input data containing messages

    Returns:
        The content of the first human message, or None if not found
    """
    messages = input_data.get("messages", [])
    if not messages:
        return None

    # Find the first human/user message
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type", "")
            if role in ("human", "user"):
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    # Handle multimodal content - extract text parts
                    text_parts = []
                    for part in content:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                    return " ".join(text_parts) if text_parts else None
        elif hasattr(msg, "type") and msg.type in ("human", "user"):
            # Handle LangChain message objects
            content = msg.content
            if isinstance(content, str):
                return content

    return None


async def generate_thread_title(
    user_message: str, model_name: str | None = None
) -> str:
    """Generate a concise title for a thread based on the user's first message.

    Args:
        user_message: The user's first message in the thread
        model_name: Optional model name in format 'provider/model'

    Returns:
        A concise title (max 50 characters)
    """
    if not user_message:
        return "New conversation"

    model_name = model_name or DEFAULT_TITLE_MODEL

    try:
        # Parse provider and model from the fully specified name
        if "/" in model_name:
            provider, model = model_name.split("/", maxsplit=1)
        else:
            provider = "openai"
            model = model_name

        llm = init_chat_model(model, model_provider=provider)

        system_prompt = """You are a title generator. Given a user's message, generate a very short,
concise title (3-6 words, max 50 characters) that captures the main topic or intent.

Rules:
- Be concise and descriptive
- Use title case
- No quotes or punctuation at the end
- No prefixes like "Title:" or "Topic:"
- If the message is a greeting, generate something like "New Chat" or "Getting Started"
- Focus on the main subject or action

Examples:
- "How do I reset my password?" → "Password Reset Help"
- "Can you explain photosynthesis?" → "Understanding Photosynthesis"
- "Hello!" → "New Conversation"
- "Write a poem about the ocean" → "Ocean Poetry Request"
- "Debug this Python code" → "Python Code Debugging"
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Generate a title for: {user_message[:500]}"),
        ]

        response = await llm.ainvoke(messages)
        title = str(response.content).strip()

        # Ensure title is not too long
        if len(title) > 50:
            title = title[:47] + "..."

        logger.info(
            "Generated thread title", title=title, message_preview=user_message[:100]
        )
        return title

    except Exception as e:
        logger.warning("Failed to generate thread title, using fallback", error=str(e))
        # Fallback: use truncated first message
        fallback = user_message[:47] + "..." if len(user_message) > 50 else user_message
        return fallback


async def maybe_generate_title_for_thread(
    input_data: dict[str, Any],
    current_title: str | None = None,
) -> str | None:
    """Generate a title if one doesn't exist and there's a user message.

    Args:
        input_data: The input data containing messages
        current_title: The current thread title (if any)

    Returns:
        A new title if generated, or None if not needed
    """
    # Skip if title already exists
    if current_title and current_title.strip():
        return None

    # Extract first user message
    user_message = extract_first_user_message(input_data)
    if not user_message:
        return None

    # Generate title
    return await generate_thread_title(user_message)

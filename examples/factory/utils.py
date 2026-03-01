"""Utilities for the unified factory example."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


def load_chat_model(model_name: str) -> BaseChatModel:
    """Load a chat model by provider/model-name string.

    Args:
        model_name: Model identifier in ``provider/model-name`` format
            (e.g. ``openai/gpt-4o-mini``, ``anthropic/claude-sonnet-4-20250514``).

    Returns:
        An initialised chat model instance.
    """
    parts = model_name.split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid model_name {model_name!r}: expected 'provider/model' format (e.g. 'openai/gpt-4o-mini')"
        )
    provider, model = parts
    return init_chat_model(model, model_provider=provider)

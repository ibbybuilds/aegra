"""Utilities for the MCP factory example."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


def load_chat_model(model_name: str) -> BaseChatModel:
    """Load a chat model by provider/model-name string.

    Args:
        model_name: Model identifier in ``provider/model-name`` format.

    Returns:
        An initialised chat model instance.
    """
    return init_chat_model(model_name)

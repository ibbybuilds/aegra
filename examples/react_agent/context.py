"""Define the configurable parameters for the agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Annotated, Any

from react_agent import prompts


@dataclass(kw_only=True)
class Context:
    """The context for the agent."""

    system_prompt: str = field(
        default="",  # Will be dynamically generated based on advisor
        metadata={
            "description": "The system prompt to use for the agent's interactions. "
            "This prompt sets the context and behavior for the agent."
        },
    )

    advisor: dict[str, Any] | None = field(
        default=None,
        metadata={
            "description": "The career advisor assigned to the student based on their learning track. "
            "Contains name, title, experience, personality, expertise_areas, communication_style, background."
        },
    )

    learning_track: str | None = field(
        default=None,
        metadata={
            "description": "The student's current learning track (e.g., 'data-analytics', 'data-science')."
        },
    )

    model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        # default="openai/gpt-5-mini-2025-08-07",  # noqa: ERA001
        default="anthropic/claude-sonnet-4-5-20250929",
        metadata={
            "description": "The name of the language model to use for the agent's main interactions. "
            "Should be in the form: provider/model-name."
        },
    )

    enable_thinking: bool = field(
        default=True,
        metadata={
            "description": "Enable extended thinking (reasoning) for Claude models. "
            "When enabled, the AI will show its reasoning process."
        },
    )

    thinking_budget: int = field(
        default=10000,
        metadata={
            "description": "Token budget for extended thinking (min 1024, max 128000). "
            "Higher values allow more thorough reasoning but cost more."
        },
    )

    max_search_results: int = field(
        default=10,
        metadata={"description": "The maximum number of search results to return for each search query."},
    )

    user_token: str | None = field(
        default=None,
        metadata={
            "description": "JWT access token for authenticating with external LMS API."
        },
    )

    user_id: str | None = field(
        default=None,
        metadata={
            "description": "User ID extracted from JWT token for memory namespacing."
        },
    )

    lms_api_url: str = field(
        default="https://dedatahub-api.vercel.app",
        metadata={
            "description": "Base URL for the LMS API to fetch student information."
        },
    )

    brave_search_api_key: str | None = field(
        default=None,
        metadata={"description": "The API key for Brave Search."},
    )

    def __post_init__(self) -> None:
        """Fetch env vars for attributes that were not passed as args and generate dynamic prompt."""
        for f in fields(self):
            if not f.init:
                continue

            if getattr(self, f.name) == f.default:
                setattr(self, f.name, os.environ.get(f.name.upper(), f.default))

        # Generate dynamic system prompt based on advisor
        if not self.system_prompt:
            self.system_prompt = prompts.get_dynamic_system_prompt(self.advisor)

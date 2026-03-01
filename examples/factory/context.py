"""Typed factory context — drives model selection, graph structure, and MCP lifecycle."""

from dataclasses import dataclass


@dataclass(kw_only=True)
class FactoryContext:
    """Request context for the unified factory example.

    Callers pass this as ``context={...}`` when creating a run. The factory
    reads it from ``runtime.execution_runtime.context`` (coerced automatically
    via ``ServerRuntime[FactoryContext]``).

    Attributes:
        model: LLM identifier in ``provider/model-name`` format.
        system_prompt: System message prepended to every LLM call.
        enable_search: When ``False``, the ``search_web`` tool is excluded
            and the graph has no ``tools`` node.
        enable_mcp: When ``True`` (and in an execution context), spins up
            MCP tool servers and adds their tools to the agent.
    """

    model: str = "openai/gpt-4o-mini"
    system_prompt: str = "You are a helpful assistant."
    enable_search: bool = True
    enable_mcp: bool = False

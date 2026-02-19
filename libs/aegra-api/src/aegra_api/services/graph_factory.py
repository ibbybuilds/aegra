"""Graph factory support for runtime-aware and config-aware graph creation.

Provides the types and helpers for callable graph exports that need per-request
arguments (Runtime context or RunnableConfig) to dynamically configure graphs.

Two factory patterns are supported:

1. **Runtime factory** — ``async def make_graph(runtime: Runtime[Ctx]) -> CompiledGraph``
   Receives a ``Runtime`` object with coerced context. Used when the graph
   needs user-specific configuration (system prompt, model selection, etc.).

2. **Config factory** — ``async def make_graph(config: RunnableConfig) -> CompiledGraph``
   Receives the full ``RunnableConfig`` dict built for the run.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, is_dataclass
from typing import Any, Generic, Literal, TypeVar, get_args, get_type_hints

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

Ctx = TypeVar("Ctx")


@dataclass
class Runtime(Generic[Ctx]):  # noqa: UP046
    """Lightweight Runtime object passed to graph factories.

    Mirrors the LangGraph Runtime pattern where factories receive per-request
    context to dynamically configure graphs.

    The generic parameter ``Ctx`` is for type-hint purposes only; at runtime
    ``context`` holds the coerced value (or a plain dict if no schema is set).
    """

    context: Ctx | None = None  # type: ignore[assignment]


@dataclass
class GraphFactory:
    """Wrapper for callable graph factories that require per-request arguments.

    Stored in place of a compiled graph when the factory needs per-request
    context or config. The factory is called on each request.

    ``kind`` determines how the factory is invoked:
    - ``"runtime"``: called with ``Runtime(context=...)``
    - ``"config"``: called with the ``RunnableConfig`` dict
    """

    factory: Callable[..., Any]
    kind: Literal["runtime", "config"]
    context_schema: type | None = None


def coerce_context(context_schema: type | None, context: dict[str, Any] | None) -> Any:
    """Coerce a context dict to the factory's expected context type.

    If the context_schema is a Pydantic BaseModel or a dataclass, instantiate
    it from the dict. Otherwise return the dict as-is.
    """
    if context is None or context_schema is None:
        return context

    if isinstance(context, dict) and (issubclass(context_schema, BaseModel) or is_dataclass(context_schema)):
        return context_schema(**context)
    return context


def build_default_context(context_schema: type | None) -> Any:
    """Build a default context instance from the schema.

    Used when calling the factory with a default Runtime (no user context)
    to produce the base graph for schema extraction. If the schema is a
    Pydantic BaseModel or dataclass where all fields have defaults, we
    instantiate it with no arguments so the factory receives a usable object
    instead of None.
    """
    if context_schema is None:
        return None

    try:
        return context_schema()
    except (TypeError, ValueError):
        # Schema has required fields without defaults — can't build a default
        return None


def extract_context_schema(factory: Callable[..., Any]) -> type | None:
    """Extract the Context type from a factory's ``runtime`` parameter hint.

    Supports ``Runtime[SomeType]`` (generic alias) and plain ``Runtime``.
    Returns the inner type argument or ``None`` if not parameterised.
    """
    try:
        hints = get_type_hints(factory)
    except Exception:
        return None

    runtime_hint = hints.get("runtime")
    if runtime_hint is None:
        return None

    args = get_args(runtime_hint)
    if args:
        schema: type = args[0]
        return schema
    return None


def has_runnable_config_param(factory: Callable[..., Any]) -> bool:
    """Check if the factory has a ``config`` parameter typed as RunnableConfig."""
    try:
        sig = inspect.signature(factory)
    except (ValueError, TypeError):
        return False

    if "config" not in sig.parameters:
        return False

    # Verify the type hint is actually RunnableConfig (not some other 'config')
    try:
        hints = get_type_hints(factory)
    except Exception:
        # If we can't resolve hints, fall back to param name alone
        return True

    config_hint = hints.get("config")
    if config_hint is None:
        # No type annotation — require an explicit type to avoid false positives
        return False

    # Accept dict, RunnableConfig, or any dict-like type hint
    if config_hint is dict or (hasattr(config_hint, "__origin__") and config_hint.__origin__ is dict):
        return True

    return config_hint is RunnableConfig


def detect_factory(graph_id: str, graph: Callable[..., Any]) -> GraphFactory | None:
    """Inspect a callable graph export and return a GraphFactory if it needs per-request args.

    Returns ``None`` if the callable is a simple factory (no ``runtime`` or ``config`` param)
    that should be called immediately at load time.

    Detection priority: ``runtime`` param wins over ``config`` param.
    """
    try:
        sig = inspect.signature(graph)
        has_runtime = "runtime" in sig.parameters
    except (ValueError, TypeError):
        has_runtime = False

    if has_runtime:
        context_schema = extract_context_schema(graph)
        return GraphFactory(factory=graph, kind="runtime", context_schema=context_schema)

    if has_runnable_config_param(graph):
        return GraphFactory(factory=graph, kind="config")

    return None

"""Graph factory classification, runtime construction, and dispatch helpers.

Supports four factory signatures:
- 0 params: ``def make_graph() -> Graph``
- 1 param (config): ``def make_graph(config: RunnableConfig) -> Graph``
- 1 param (runtime): ``def make_graph(runtime: ServerRuntime) -> Graph``
- 2 params (either order): ``def make_graph(config, runtime: ServerRuntime)``

Factory detection happens at graph load time via ``classify_factory()``.
Per-request invocation is handled by ``invoke_factory()`` with the appropriate
``ServerRuntime`` variant constructed by ``build_server_runtime()``.
"""

from __future__ import annotations

import asyncio
import inspect
import typing
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal, get_args, get_origin

import structlog
from langgraph.graph import StateGraph
from langgraph.pregel import Pregel
from langgraph.store.base import BaseStore
from langgraph_sdk.auth.types import BaseUser
from langgraph_sdk.runtime import (
    ServerRuntime,
    _ExecutionRuntime,
    _ReadRuntime,
)

from aegra_api.core.auth_ctx import get_auth_ctx

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

AccessContext = Literal[
    "threads.create_run",
    "threads.update",
    "threads.read",
    "assistants.read",
]
"""Why the graph factory is being called.

- ``threads.create_run``: Full graph execution (nodes + edges).
- ``threads.update``: ``aupdate_state`` — applies writes to state channels.
- ``threads.read``: ``aget_state`` / ``aget_state_history`` — formats state snapshots.
- ``assistants.read``: Schema extraction, graph visualization.
"""

_HookType = Callable[["_RunnableConfig", "ServerRuntime"], dict[str, Any]]

# Maps graph_id → a callable that produces kwargs for the factory function.
# Populated by ``classify_factory()`` at graph load time.
_FACTORY_KWARGS: dict[str, _HookType] = {}

# Concrete runtime classes used for ``issubclass`` checks during classification.
_RUNTIME_CLASSES: tuple[type, ...] = (_ExecutionRuntime, _ReadRuntime)

# Type alias for RunnableConfig — LangGraph uses ``dict[str, Any]``.
_RunnableConfig = dict[str, Any]

# Namespace for resolving string annotations in factory functions.
# Lets users import ``ServerRuntime`` inside ``TYPE_CHECKING`` blocks
# and still have the factory classifier resolve it correctly.
_RUNTIME_LOCALNS: dict[str, Any] = {
    "ServerRuntime": ServerRuntime,
    "RunnableConfig": _RunnableConfig,
    "Config": _RunnableConfig,
}


# ---------------------------------------------------------------------------
# Factory classification
# ---------------------------------------------------------------------------


def classify_factory(fn: Callable, graph_id: str) -> None:
    """Inspect *fn*'s signature and register a dispatch hook if it accepts arguments.

    Idempotent — calling twice with the same *graph_id* is a no-op.

    Args:
        fn: The callable graph export (factory function).
        graph_id: The graph identifier from the configuration file.
    """
    if graph_id in _FACTORY_KWARGS:
        return
    hook = _classify_factory(fn)
    if hook is not None:
        _FACTORY_KWARGS[graph_id] = hook


def _is_runtime_annotation(annotation: Any) -> bool:
    """Return ``True`` if *annotation* refers to ``ServerRuntime`` or a concrete subclass.

    Handles:
    - The ``ServerRuntime`` TypeAliasType directly.
    - Parameterized forms like ``ServerRuntime[MyContext]``.
    - Concrete runtime classes (``_ExecutionRuntime``, ``_ReadRuntime``)
      and their subclasses.
    - ``Annotated[ServerRuntime, ...]`` wrappers.
    """
    if annotation is inspect.Parameter.empty:
        return False
    # Identity check against the ServerRuntime TypeAliasType
    if annotation is ServerRuntime:
        return True
    # issubclass check against concrete runtime classes
    if isinstance(annotation, type):
        try:
            return issubclass(annotation, _RUNTIME_CLASSES)
        except TypeError:
            return False
    # Handle parameterized types (ServerRuntime[MyContext], Annotated[...])
    origin = get_origin(annotation)
    if origin is not None:
        if origin is ServerRuntime:
            return True
        # For Annotated[ServerRuntime, ...], recurse on the base type
        args = get_args(annotation)
        if args:
            return _is_runtime_annotation(args[0])
    return False


def _resolve_hints(fn: Callable) -> dict[str, Any]:
    """Resolve string annotations using the function's module globals + runtime types."""
    try:
        return typing.get_type_hints(fn, localns=_RUNTIME_LOCALNS)
    except (NameError, AttributeError) as exc:
        logger.debug("graph_factory_hint_resolution_failed", fn=fn, exc=str(exc))
        return {}


def _classify_factory(fn: Callable) -> _HookType | None:
    """Classify a graph factory by its parameter signature.

    Returns a callable that, given ``(config, server_runtime)``, produces
    the ``**kwargs`` dict to pass to the factory. Returns ``None`` for
    0-arg factories (no dispatch hook needed).

    Raises:
        ValueError: If the factory has 3+ parameters or ambiguous runtime params.
    """
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    hints = _resolve_hints(fn)

    def _annotation(p: inspect.Parameter) -> Any:
        return hints.get(p.name, p.annotation)

    if len(params) == 0:
        # 0-arg factory — no hook needed
        return None
    elif len(params) == 1:
        if _is_runtime_annotation(_annotation(params[0])):
            return lambda config, runtime: {params[0].name: runtime}
        return lambda config, runtime: {params[0].name: config}
    elif len(params) == 2:
        # Detect which param is runtime by annotation; the other is config.
        rt_indices = [i for i, p in enumerate(params) if _is_runtime_annotation(_annotation(p))]
        if len(rt_indices) == 1:
            rt_idx = rt_indices[0]
            cfg_idx = 1 - rt_idx
        elif len(rt_indices) == 0:
            raise ValueError(
                f"Graph factory {fn} has 2 parameters but neither is annotated as "
                f"ServerRuntime. For a 2-param factory, one parameter must be typed as "
                f"ServerRuntime and the other as RunnableConfig."
            )
        else:
            raise ValueError(
                f"Graph factory {fn} has 2 parameters both annotated as ServerRuntime. "
                f"Expected one ServerRuntime and one RunnableConfig."
            )
        return lambda config, runtime: {
            params[rt_idx].name: runtime,
            params[cfg_idx].name: config,
        }
    else:
        raise ValueError(
            f"Graph factory {fn} must take 0, 1, or 2 arguments. "
            f"Got {len(params)} parameters: {[p.name for p in params]}"
        )


# ---------------------------------------------------------------------------
# Factory state queries
# ---------------------------------------------------------------------------


def is_factory(graph_id: str) -> bool:
    """Return ``True`` if *graph_id* was classified as a factory that accepts arguments."""
    return graph_id in _FACTORY_KWARGS


def is_for_execution(access_context: AccessContext) -> bool:
    """Return ``True`` if the access context represents full graph execution."""
    return access_context == "threads.create_run"


# ---------------------------------------------------------------------------
# Runtime construction
# ---------------------------------------------------------------------------


def build_server_runtime(
    *,
    access_context: AccessContext,
    store: BaseStore | None,
    user: BaseUser | None = None,
) -> ServerRuntime:
    """Construct the appropriate ``ServerRuntime`` variant for the access context.

    For ``threads.create_run``, returns an ``_ExecutionRuntime`` (which has
    a ``context`` field). For all other contexts, returns a ``_ReadRuntime``.

    If *user* is ``None``, falls back to the current request's auth context.

    Args:
        access_context: Why the graph factory is being called.
        store: The persistence store for the graph run.
        user: The authenticated user, or ``None`` to auto-detect from auth context.

    Returns:
        A ``ServerRuntime`` instance (either ``_ExecutionRuntime`` or ``_ReadRuntime``).
    """
    if user is None:
        auth_ctx = get_auth_ctx()
        user = auth_ctx.user if auth_ctx else None

    if is_for_execution(access_context):
        return _ExecutionRuntime(
            access_context=access_context,
            user=user,
            store=store,
        )
    return _ReadRuntime(
        access_context=access_context,
        user=user,
        store=store,
    )


# ---------------------------------------------------------------------------
# Factory invocation
# ---------------------------------------------------------------------------


def invoke_factory(
    fn: Callable,
    graph_id: str,
    config: _RunnableConfig,
    server_runtime: ServerRuntime,
) -> Any:
    """Call a graph factory with the correct arguments based on its classification.

    Args:
        fn: The graph factory callable.
        graph_id: The graph identifier (used to look up the dispatch hook).
        config: The ``RunnableConfig`` dict for this request.
        server_runtime: The ``ServerRuntime`` for this request.

    Returns:
        Whatever the factory returns (``Pregel``, ``StateGraph``, coroutine,
        async context manager, etc.).
    """
    hook = _FACTORY_KWARGS.get(graph_id)
    if not hook:
        return fn()
    kwargs = hook(config, server_runtime)
    return fn(**kwargs)


# ---------------------------------------------------------------------------
# Graph result resolution
# ---------------------------------------------------------------------------


@asynccontextmanager
async def generate_graph(value: Any, graph_id: str) -> AsyncIterator[Pregel | StateGraph]:
    """Yield a graph object regardless of the factory's return type.

    Handles:
    - ``Pregel`` / ``StateGraph`` — yield directly.
    - Async context manager — ``async with value as graph: yield graph``.
    - Sync context manager — ``with value as graph: yield graph``.
    - Coroutine — ``yield await value``.
    - Other — yield as-is (likely a ``StateGraph`` or ``Pregel``).

    Args:
        value: The raw return value from a graph factory or a static graph.
        graph_id: The graph identifier (used for logging).

    Yields:
        A graph object (``Pregel`` or ``StateGraph``).
    """
    if isinstance(value, Pregel | StateGraph):
        yield value
    elif hasattr(value, "__aenter__") and hasattr(value, "__aexit__"):
        async with value as ctx_value:
            logger.debug("graph_factory_async_ctx_resolved", graph_id=graph_id)
            yield ctx_value
    elif hasattr(value, "__enter__") and hasattr(value, "__exit__"):
        with value as ctx_value:
            logger.debug("graph_factory_sync_ctx_resolved", graph_id=graph_id)
            yield ctx_value
    elif asyncio.iscoroutine(value):
        result = await value
        logger.debug("graph_factory_coroutine_resolved", graph_id=graph_id)
        yield result
    else:
        yield value


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def clear_factory_registry(graph_id: str | None = None) -> None:
    """Remove factory dispatch hooks.

    Args:
        graph_id: Specific graph to clear, or ``None`` to clear all.
    """
    if graph_id:
        _FACTORY_KWARGS.pop(graph_id, None)
    else:
        _FACTORY_KWARGS.clear()

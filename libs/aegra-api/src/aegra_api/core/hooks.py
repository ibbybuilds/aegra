"""Run lifecycle hooks for aegra-api.

Provides the ``RunHooks`` registry, the immutable ``RunContext`` dataclass,
and the ``RejectRun`` exception used by ``before_run`` hooks to gate
execution.  A module-level singleton + loader round out the public API.
"""

import asyncio
import importlib
import importlib.util
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from aegra_api.models.auth import User

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RunContext:
    """Immutable context passed to all run hook callbacks.

    All hooks receive the same fields.  Fields that are only meaningful for
    specific hook points are ``None`` when not applicable.

    The ``extras`` dict is populated by the server with data collected during
    execution (e.g., token usage metadata).  Hooks should treat it as
    read-only.
    """

    run_id: str
    thread_id: str
    assistant_id: str
    graph_id: str
    user: User
    config: dict[str, Any] = field(default_factory=dict)
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    status: str | None = None
    error: str | None = None
    error_type: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class RejectRun(Exception):
    """Raise inside a ``before_run`` hook to reject execution."""

    def __init__(self, message: str = "Run rejected by hook", status_code: int = 429) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RunHooks:
    """Registry for run lifecycle hook callbacks.

    Hooks are purely observational — they can read run context and gate
    execution (via ``RejectRun``) but cannot modify the run config or
    graph state.
    """

    # Class-level reference for user convenience: ``hooks.RejectRun``
    RejectRun = RejectRun

    def __init__(self) -> None:
        self._before_run: list[Callable[..., Any]] = []
        self._after_run: list[Callable[..., Any]] = []
        self._on_run_error: list[Callable[..., Any]] = []

    def before_run(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register a ``before_run`` hook."""
        self._before_run.append(fn)
        return fn

    def after_run(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register an ``after_run`` hook."""
        self._after_run.append(fn)
        return fn

    def on_run_error(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register an ``on_run_error`` hook."""
        self._on_run_error.append(fn)
        return fn

    async def fire_before_run(self, ctx: RunContext, timeout: float = 10.0) -> None:
        """Fire all ``before_run`` hooks.

        ``RejectRun`` exceptions propagate up.  ``TimeoutError`` becomes
        ``RejectRun(504)``.  Hook return values are ignored.
        """
        for fn in self._before_run:
            try:
                await asyncio.wait_for(fn(ctx), timeout=timeout)
            except TimeoutError:
                raise RejectRun(
                    f"before_run hook '{fn.__name__}' timed out after {timeout}s",
                    status_code=504,
                )

    async def fire_after_run(self, ctx: RunContext, timeout: float = 10.0) -> None:
        """Fire all ``after_run`` hooks.  Errors are logged, not propagated."""
        for fn in self._after_run:
            try:
                await asyncio.wait_for(fn(ctx), timeout=timeout)
            except TimeoutError:
                logger.warning(
                    "after_run hook timed out",
                    hook=fn.__name__,
                    timeout=timeout,
                    run_id=ctx.run_id,
                )
            except Exception:
                logger.exception(
                    "after_run hook failed",
                    hook=fn.__name__,
                    run_id=ctx.run_id,
                )

    async def fire_on_run_error(self, ctx: RunContext, timeout: float = 10.0) -> None:
        """Fire all ``on_run_error`` hooks.  Errors are logged, not propagated.

        Catches ``BaseException`` (not just ``Exception``) because this method
        may be called inside a ``CancelledError`` handler.  If the task is
        being cancelled, the ``await`` inside could itself raise
        ``CancelledError`` — we must not let that escape unhandled.
        """
        for fn in self._on_run_error:
            try:
                await asyncio.wait_for(fn(ctx), timeout=timeout)
            except TimeoutError:
                logger.warning(
                    "on_run_error hook timed out",
                    hook=fn.__name__,
                    timeout=timeout,
                    run_id=ctx.run_id,
                )
            except BaseException:
                logger.exception(
                    "on_run_error hook failed",
                    hook=fn.__name__,
                    run_id=ctx.run_id,
                )


# ---------- Global singleton ----------
_hooks: RunHooks | None = None
_hooks_timeout: float = 10.0


def get_hooks() -> RunHooks | None:
    """Return the globally registered ``RunHooks`` instance (or ``None``)."""
    return _hooks


def get_hooks_timeout() -> float:
    """Return the configured hook timeout in seconds."""
    return _hooks_timeout


def set_hooks(hooks: RunHooks, timeout: float = 10.0) -> None:
    """Register a ``RunHooks`` instance as the global singleton."""
    global _hooks, _hooks_timeout
    _hooks = hooks
    _hooks_timeout = timeout


# ---------- Loader ----------
def load_hooks(hooks_import: str, base_dir: Path | None = None) -> RunHooks:
    """Load ``RunHooks`` instance from an import path.

    Supports ``"./hooks.py:hooks"`` or ``"mypackage.hooks:hooks"``.
    Follows the same pattern as ``core/app_loader.py``.
    """
    if ":" not in hooks_import:
        raise ValueError(
            f"Invalid hooks import path '{hooks_import}'. "
            "Expected format: './file.py:variable' or 'module.path:variable'"
        )

    module_path, attr_name = hooks_import.rsplit(":", 1)

    # Handle relative file paths
    if module_path.startswith("."):
        if base_dir is None:
            base_dir = Path.cwd()
        file_path = (base_dir / module_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Hooks file not found: {file_path}")

        spec = importlib.util.spec_from_file_location("_user_hooks", file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load hooks from {file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_path)

    hooks = getattr(module, attr_name, None)
    if hooks is None:
        raise AttributeError(f"Module '{module_path}' has no attribute '{attr_name}'")
    if not isinstance(hooks, RunHooks):
        raise TypeError(
            f"Expected RunHooks instance, got {type(hooks).__name__}. "
            f"Make sure '{attr_name}' is an instance of RunHooks."
        )

    return hooks

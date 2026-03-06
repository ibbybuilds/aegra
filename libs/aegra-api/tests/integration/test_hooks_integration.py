"""Integration tests for run lifecycle hooks wired through execute_run_async.

These tests verify that hooks fire correctly when execute_run_async is called
with mock graph execution, covering before_run, after_run, on_run_error,
RejectRun gating, and extras propagation.
"""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aegra_api.api.runs import execute_run_async
from aegra_api.core.hooks import RejectRun, RunContext, RunHooks, set_hooks
from aegra_api.models.auth import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user() -> User:
    return User(identity="integration-test-user")


@pytest.fixture
def run_id() -> str:
    return "integration-run-1"


@pytest.fixture
def thread_id() -> str:
    return "integration-thread-1"


@pytest.fixture
def assistant_id() -> str:
    return "integration-assistant-1"


@pytest.fixture
def graph_id() -> str:
    return "test-graph"


@pytest.fixture(autouse=True)
def reset_hooks_singleton() -> Any:
    """Reset hooks singleton before and after each test."""
    from aegra_api.core import hooks as hooks_module

    original_hooks = hooks_module._hooks
    original_timeout = hooks_module._hooks_timeout
    hooks_module._hooks = None
    hooks_module._hooks_timeout = 10.0
    yield
    hooks_module._hooks = original_hooks
    hooks_module._hooks_timeout = original_timeout


def _make_success_stream() -> AsyncIterator[tuple[str, Any]]:
    """Async generator that yields a successful values event."""

    async def gen() -> AsyncIterator[tuple[str, Any]]:
        yield ("values", {"result": "ok"})

    return gen()


def _make_error_stream() -> AsyncIterator[tuple[str, Any]]:
    """Async generator that raises during streaming."""

    async def gen() -> AsyncIterator[tuple[str, Any]]:
        raise ValueError("graph exploded")
        yield  # type: ignore[misc]  # make it a generator

    return gen()


def _make_interrupt_stream() -> AsyncIterator[tuple[str, Any]]:
    """Async generator that yields an interrupt event."""

    async def gen() -> AsyncIterator[tuple[str, Any]]:
        yield ("values", {"result": "partial"})
        yield ("values", {"__interrupt__": [{"reason": "human_input"}]})

    return gen()


def _standard_patches():
    """Context manager stack for mocking out DB/LangGraph dependencies."""
    mock_graph = MagicMock()
    mock_lg_service = MagicMock()
    mock_lg_service.return_value.get_graph.return_value.__aenter__ = AsyncMock(return_value=mock_graph)
    mock_lg_service.return_value.get_graph.return_value.__aexit__ = AsyncMock(return_value=None)

    return (
        patch("aegra_api.api.runs.get_langgraph_service", return_value=mock_lg_service.return_value),
        patch("aegra_api.api.runs.update_run_status", new_callable=AsyncMock),
        patch("aegra_api.api.runs.set_thread_status", new_callable=AsyncMock),
        patch("aegra_api.api.runs._get_session_maker", return_value=lambda: AsyncMock()),
        patch(
            "aegra_api.api.runs.streaming_service",
            MagicMock(
                put_to_broker=AsyncMock(),
                store_event_from_raw=AsyncMock(),
                signal_run_error=AsyncMock(),
                signal_run_cancelled=AsyncMock(),
                cleanup_run=AsyncMock(),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBeforeRunHookIntegration:
    """before_run hooks fire before graph execution."""

    async def test_before_run_called(
        self, mock_user: User, run_id: str, thread_id: str, assistant_id: str, graph_id: str
    ) -> None:
        """before_run hook is called with correct context."""
        received_ctx: list[RunContext] = []
        hooks = RunHooks()

        @hooks.before_run
        async def capture(ctx: RunContext) -> None:
            received_ctx.append(ctx)

        set_hooks(hooks)

        p1, p2, p3, p4, p5 = _standard_patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=_make_success_stream(),
            ),
        ):
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                input_data={"msg": "hello"},
                user=mock_user,
            )

        assert len(received_ctx) == 1
        ctx = received_ctx[0]
        assert ctx.run_id == run_id
        assert ctx.thread_id == thread_id
        assert ctx.assistant_id == assistant_id
        assert ctx.graph_id == graph_id
        assert ctx.user.identity == "integration-test-user"
        assert ctx.input == {"msg": "hello"}

    async def test_reject_run_stops_execution(
        self, mock_user: User, run_id: str, thread_id: str, assistant_id: str, graph_id: str
    ) -> None:
        """RejectRun in before_run prevents graph execution."""
        hooks = RunHooks()

        @hooks.before_run
        async def reject(ctx: RunContext) -> None:
            raise RejectRun("subscription required", status_code=402)

        set_hooks(hooks)

        graph_was_called = False

        async def stream_that_shouldnt_run(*args: Any, **kwargs: Any) -> AsyncIterator[tuple[str, Any]]:
            nonlocal graph_was_called
            graph_was_called = True
            yield ("values", {})

        p1, p2, p3, p4, p5 = _standard_patches()
        with (
            p1,
            p2 as mock_update,
            p3,
            p4,
            p5,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                side_effect=stream_that_shouldnt_run,
            ),
        ):
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
            )

        assert not graph_was_called
        # Run should be set to error status — verify the key arguments
        # (session is a mock so we check positional/keyword args without session identity)
        error_calls = [
            c for c in mock_update.call_args_list if len(c.args) >= 2 and c.args[0] == run_id and c.args[1] == "error"
        ]
        assert len(error_calls) >= 1, "update_run_status should be called with 'error' status"
        assert error_calls[0].kwargs.get("error") == "subscription required"


class TestAfterRunHookIntegration:
    """after_run hooks fire after successful graph execution."""

    async def test_after_run_success(
        self, mock_user: User, run_id: str, thread_id: str, assistant_id: str, graph_id: str
    ) -> None:
        """after_run fires with status='success' on normal completion."""
        received_ctx: list[RunContext] = []
        hooks = RunHooks()

        @hooks.after_run
        async def capture(ctx: RunContext) -> None:
            received_ctx.append(ctx)

        set_hooks(hooks)

        p1, p2, p3, p4, p5 = _standard_patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=_make_success_stream(),
            ),
        ):
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
            )

        assert len(received_ctx) == 1
        ctx = received_ctx[0]
        assert ctx.status == "success"
        assert ctx.output == {"result": "ok"}
        assert ctx.extras == {}

    async def test_after_run_interrupt(
        self, mock_user: User, run_id: str, thread_id: str, assistant_id: str, graph_id: str
    ) -> None:
        """after_run fires with status='interrupted' when graph hits interrupt."""
        received_ctx: list[RunContext] = []
        hooks = RunHooks()

        @hooks.after_run
        async def capture(ctx: RunContext) -> None:
            received_ctx.append(ctx)

        set_hooks(hooks)

        p1, p2, p3, p4, p5 = _standard_patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=_make_interrupt_stream(),
            ),
        ):
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
            )

        assert len(received_ctx) == 1
        assert received_ctx[0].status == "interrupted"

    async def test_after_run_error_does_not_propagate(
        self, mock_user: User, run_id: str, thread_id: str, assistant_id: str, graph_id: str
    ) -> None:
        """If after_run hook raises, the error is logged but doesn't fail the run."""
        hooks = RunHooks()

        @hooks.after_run
        async def explode(ctx: RunContext) -> None:
            raise RuntimeError("hook crashed")

        set_hooks(hooks)

        p1, p2, p3, p4, p5 = _standard_patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=_make_success_stream(),
            ),
        ):
            # Should not raise despite hook error
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
            )


class TestOnRunErrorHookIntegration:
    """on_run_error hooks fire when graph execution fails."""

    async def test_on_run_error_called(
        self, mock_user: User, run_id: str, thread_id: str, assistant_id: str, graph_id: str
    ) -> None:
        """on_run_error fires with error details when graph raises."""
        received_ctx: list[RunContext] = []
        hooks = RunHooks()

        @hooks.on_run_error
        async def capture(ctx: RunContext) -> None:
            received_ctx.append(ctx)

        set_hooks(hooks)

        p1, p2, p3, p4, p5 = _standard_patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=_make_error_stream(),
            ),
        ):
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
            )

        assert len(received_ctx) == 1
        ctx = received_ctx[0]
        assert ctx.error == "graph exploded"
        assert ctx.error_type == "ValueError"


class TestNoHooksConfigured:
    """When no hooks are configured, execution works normally."""

    async def test_no_hooks(
        self, mock_user: User, run_id: str, thread_id: str, assistant_id: str, graph_id: str
    ) -> None:
        """execute_run_async works fine with no hooks set."""
        # hooks singleton is already None from the autouse fixture

        p1, p2, p3, p4, p5 = _standard_patches()
        with (
            p1,
            p2,
            p3,
            p4,
            p5,
            patch(
                "aegra_api.api.runs.stream_graph_events",
                return_value=_make_success_stream(),
            ),
        ):
            await execute_run_async(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                graph_id=graph_id,
                input_data={},
                user=mock_user,
            )
        # No assertion needed — just verifying no exception

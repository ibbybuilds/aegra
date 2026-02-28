"""Unit tests for run lifecycle hooks (core/hooks.py)."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from aegra_api.core.hooks import (
    RejectRun,
    RunContext,
    RunHooks,
    get_hooks,
    get_hooks_timeout,
    load_hooks,
    set_hooks,
)
from aegra_api.models.auth import User

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hooks() -> RunHooks:
    """Fresh RunHooks instance for each test."""
    return RunHooks()


@pytest.fixture
def user() -> User:
    """Minimal User for RunContext construction."""
    return User(identity="test-user")


@pytest.fixture
def base_ctx(user: User) -> RunContext:
    """Base RunContext with required fields filled in."""
    return RunContext(
        run_id="run-1",
        thread_id="thread-1",
        assistant_id="asst-1",
        graph_id="agent",
        user=user,
    )


# ---------------------------------------------------------------------------
# RunContext
# ---------------------------------------------------------------------------


class TestRunContext:
    """Tests for RunContext dataclass."""

    def test_frozen(self, base_ctx: RunContext) -> None:
        """RunContext is immutable."""
        with pytest.raises(AttributeError):
            base_ctx.run_id = "changed"  # type: ignore[misc]

    def test_defaults(self, user: User) -> None:
        """Optional fields default to None / empty dict."""
        ctx = RunContext(
            run_id="r",
            thread_id="t",
            assistant_id="a",
            graph_id="g",
            user=user,
        )
        assert ctx.config == {}
        assert ctx.input is None
        assert ctx.output is None
        assert ctx.status is None
        assert ctx.error is None
        assert ctx.error_type is None
        assert ctx.extras == {}

    def test_extras_populated(self, user: User) -> None:
        """extras dict can be populated at construction time."""
        extras = {"usage_metadata": {"gpt-4o": {"total_tokens": 100}}}
        ctx = RunContext(
            run_id="r",
            thread_id="t",
            assistant_id="a",
            graph_id="g",
            user=user,
            extras=extras,
        )
        assert ctx.extras["usage_metadata"]["gpt-4o"]["total_tokens"] == 100

    def test_extras_default_factory_isolation(self, user: User) -> None:
        """Each RunContext gets its own extras dict (no shared mutable default)."""
        ctx1 = RunContext(run_id="r1", thread_id="t", assistant_id="a", graph_id="g", user=user)
        ctx2 = RunContext(run_id="r2", thread_id="t", assistant_id="a", graph_id="g", user=user)
        assert ctx1.extras is not ctx2.extras


# ---------------------------------------------------------------------------
# RejectRun
# ---------------------------------------------------------------------------


class TestRejectRun:
    """Tests for RejectRun exception."""

    def test_defaults(self) -> None:
        exc = RejectRun()
        assert exc.message == "Run rejected by hook"
        assert exc.status_code == 429

    def test_custom(self) -> None:
        exc = RejectRun("No credits", status_code=402)
        assert exc.message == "No credits"
        assert exc.status_code == 402

    def test_is_exception(self) -> None:
        assert issubclass(RejectRun, Exception)

    def test_class_level_access(self) -> None:
        """RejectRun accessible via RunHooks.RejectRun for user convenience."""
        assert RunHooks.RejectRun is RejectRun


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Tests for hook registration via decorators."""

    def test_register_before_run(self, hooks: RunHooks) -> None:
        @hooks.before_run
        async def my_hook(ctx: RunContext) -> None:
            pass

        assert len(hooks._before_run) == 1
        assert hooks._before_run[0] is my_hook

    def test_register_after_run(self, hooks: RunHooks) -> None:
        @hooks.after_run
        async def my_hook(ctx: RunContext) -> None:
            pass

        assert len(hooks._after_run) == 1

    def test_register_on_run_error(self, hooks: RunHooks) -> None:
        @hooks.on_run_error
        async def my_hook(ctx: RunContext) -> None:
            pass

        assert len(hooks._on_run_error) == 1

    def test_multiple_hooks_per_event(self, hooks: RunHooks) -> None:
        @hooks.before_run
        async def hook1(ctx: RunContext) -> None:
            pass

        @hooks.before_run
        async def hook2(ctx: RunContext) -> None:
            pass

        assert len(hooks._before_run) == 2
        assert hooks._before_run[0] is hook1
        assert hooks._before_run[1] is hook2

    def test_decorator_returns_original_function(self, hooks: RunHooks) -> None:
        async def original(ctx: RunContext) -> None:
            pass

        result = hooks.before_run(original)
        assert result is original


# ---------------------------------------------------------------------------
# fire_before_run
# ---------------------------------------------------------------------------


class TestFireBeforeRun:
    """Tests for fire_before_run behavior."""

    async def test_calls_hooks_in_order(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        call_order: list[str] = []

        @hooks.before_run
        async def first(ctx: RunContext) -> None:
            call_order.append("first")

        @hooks.before_run
        async def second(ctx: RunContext) -> None:
            call_order.append("second")

        await hooks.fire_before_run(base_ctx)
        assert call_order == ["first", "second"]

    async def test_reject_run_propagates(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        @hooks.before_run
        async def reject(ctx: RunContext) -> None:
            raise RejectRun("denied", status_code=402)

        with pytest.raises(RejectRun) as exc_info:
            await hooks.fire_before_run(base_ctx)

        assert exc_info.value.message == "denied"
        assert exc_info.value.status_code == 402

    async def test_reject_stops_subsequent_hooks(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        reached_second = False

        @hooks.before_run
        async def reject(ctx: RunContext) -> None:
            raise RejectRun("stop")

        @hooks.before_run
        async def should_not_run(ctx: RunContext) -> None:
            nonlocal reached_second
            reached_second = True

        with pytest.raises(RejectRun):
            await hooks.fire_before_run(base_ctx)

        assert not reached_second

    async def test_timeout_becomes_reject_run(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        @hooks.before_run
        async def slow(ctx: RunContext) -> None:
            await asyncio.sleep(10)

        with pytest.raises(RejectRun) as exc_info:
            await hooks.fire_before_run(base_ctx, timeout=0.01)

        assert exc_info.value.status_code == 504
        assert "timed out" in exc_info.value.message

    async def test_return_values_ignored(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        @hooks.before_run
        async def returns_stuff(ctx: RunContext) -> dict:
            return {"should": "be ignored"}

        # Should not raise
        await hooks.fire_before_run(base_ctx)

    async def test_no_hooks_is_noop(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        """Empty hook list doesn't error."""
        await hooks.fire_before_run(base_ctx)


# ---------------------------------------------------------------------------
# fire_after_run
# ---------------------------------------------------------------------------


class TestFireAfterRun:
    """Tests for fire_after_run behavior."""

    async def test_calls_hooks(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        called = AsyncMock()

        @hooks.after_run
        async def my_hook(ctx: RunContext) -> None:
            await called()

        await hooks.fire_after_run(base_ctx)
        called.assert_awaited_once()

    async def test_errors_logged_not_propagated(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        @hooks.after_run
        async def fails(ctx: RunContext) -> None:
            raise ValueError("boom")

        # Should not raise
        await hooks.fire_after_run(base_ctx)

    async def test_error_does_not_stop_subsequent_hooks(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        second_called = False

        @hooks.after_run
        async def fails(ctx: RunContext) -> None:
            raise ValueError("first hook fails")

        @hooks.after_run
        async def succeeds(ctx: RunContext) -> None:
            nonlocal second_called
            second_called = True

        await hooks.fire_after_run(base_ctx)
        assert second_called

    async def test_timeout_logged_not_propagated(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        @hooks.after_run
        async def slow(ctx: RunContext) -> None:
            await asyncio.sleep(10)

        # Should not raise
        await hooks.fire_after_run(base_ctx, timeout=0.01)


# ---------------------------------------------------------------------------
# fire_on_run_error
# ---------------------------------------------------------------------------


class TestFireOnRunError:
    """Tests for fire_on_run_error behavior."""

    async def test_calls_hooks(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        called = AsyncMock()

        @hooks.on_run_error
        async def my_hook(ctx: RunContext) -> None:
            await called()

        await hooks.fire_on_run_error(base_ctx)
        called.assert_awaited_once()

    async def test_errors_logged_not_propagated(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        @hooks.on_run_error
        async def fails(ctx: RunContext) -> None:
            raise RuntimeError("hook failed")

        # Should not raise
        await hooks.fire_on_run_error(base_ctx)

    async def test_catches_base_exception(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        """on_run_error catches BaseException (including CancelledError)."""

        @hooks.on_run_error
        async def raises_cancelled(ctx: RunContext) -> None:
            raise asyncio.CancelledError()

        # Should not propagate
        await hooks.fire_on_run_error(base_ctx)

    async def test_timeout_logged_not_propagated(self, hooks: RunHooks, base_ctx: RunContext) -> None:
        @hooks.on_run_error
        async def slow(ctx: RunContext) -> None:
            await asyncio.sleep(10)

        # Should not raise
        await hooks.fire_on_run_error(base_ctx, timeout=0.01)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """Tests for global singleton management."""

    def test_default_is_none(self) -> None:
        """Before set_hooks, get_hooks returns None."""
        # Reset to clean state
        from aegra_api.core import hooks as hooks_module

        original = hooks_module._hooks
        hooks_module._hooks = None
        try:
            assert get_hooks() is None
        finally:
            hooks_module._hooks = original

    def test_set_and_get(self) -> None:
        from aegra_api.core import hooks as hooks_module

        original_hooks = hooks_module._hooks
        original_timeout = hooks_module._hooks_timeout
        try:
            h = RunHooks()
            set_hooks(h, timeout=5.0)
            assert get_hooks() is h
            assert get_hooks_timeout() == 5.0
        finally:
            hooks_module._hooks = original_hooks
            hooks_module._hooks_timeout = original_timeout

    def test_default_timeout(self) -> None:
        from aegra_api.core import hooks as hooks_module

        original_hooks = hooks_module._hooks
        original_timeout = hooks_module._hooks_timeout
        try:
            set_hooks(RunHooks())
            assert get_hooks_timeout() == 10.0
        finally:
            hooks_module._hooks = original_hooks
            hooks_module._hooks_timeout = original_timeout


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class TestLoadHooks:
    """Tests for load_hooks()."""

    def test_invalid_format_no_colon(self) -> None:
        with pytest.raises(ValueError, match="Invalid hooks import path"):
            load_hooks("no_colon_here")

    def test_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_hooks("./nonexistent.py:hooks", base_dir=tmp_path)

    def test_missing_attribute(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.py"
        f.write_text("x = 1\n")
        with pytest.raises(AttributeError, match="no attribute"):
            load_hooks("./empty.py:hooks", base_dir=tmp_path)

    def test_wrong_type(self, tmp_path: Path) -> None:
        f = tmp_path / "wrong.py"
        f.write_text("hooks = 'not a RunHooks'\n")
        with pytest.raises(TypeError, match="Expected RunHooks"):
            load_hooks("./wrong.py:hooks", base_dir=tmp_path)

    def test_load_from_file(self, tmp_path: Path) -> None:
        f = tmp_path / "my_hooks.py"
        f.write_text(
            "from aegra_api.core.hooks import RunHooks\n"
            "hooks = RunHooks()\n"
            "@hooks.before_run\n"
            "async def my_hook(ctx):\n"
            "    pass\n"
        )
        loaded = load_hooks("./my_hooks.py:hooks", base_dir=tmp_path)
        assert isinstance(loaded, RunHooks)
        assert len(loaded._before_run) == 1

    def test_load_from_module(self) -> None:
        """Loading from an installed module path (aegra_api.core.hooks itself)."""
        # This tests the module-import branch. We ask it to load the
        # RejectRun class which is *not* a RunHooks, so it should raise
        # TypeError — proving the module-import path works.
        with pytest.raises(TypeError, match="Expected RunHooks"):
            load_hooks("aegra_api.core.hooks:RejectRun")

    def test_load_nonexistent_module(self) -> None:
        with pytest.raises(ModuleNotFoundError):
            load_hooks("nonexistent.module:hooks")


# ---------------------------------------------------------------------------
# HooksConfig (config.py additions)
# ---------------------------------------------------------------------------


class TestHooksConfig:
    """Tests for load_hooks_config in config.py."""

    def test_returns_none_when_no_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aegra_api.config import load_hooks_config

        monkeypatch.setattr("aegra_api.config.load_config", lambda: None)
        assert load_hooks_config() is None

    def test_returns_none_when_no_hooks_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aegra_api.config import load_hooks_config

        monkeypatch.setattr("aegra_api.config.load_config", lambda: {"graphs": {}})
        assert load_hooks_config() is None

    def test_returns_hooks_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aegra_api.config import load_hooks_config

        config = {"hooks": {"path": "./hooks.py:hooks", "timeout": 5}}
        monkeypatch.setattr("aegra_api.config.load_config", lambda: config)
        monkeypatch.setattr("aegra_api.config._resolve_config_path", lambda: Path("aegra.json"))
        result = load_hooks_config()
        assert result is not None
        assert result["path"] == "./hooks.py:hooks"
        assert result["timeout"] == 5


# ---------------------------------------------------------------------------
# Public re-export module
# ---------------------------------------------------------------------------


class TestPublicReexport:
    """Tests that aegra_api.hooks re-exports correctly."""

    def test_imports(self) -> None:
        from aegra_api.hooks import RejectRun as RR
        from aegra_api.hooks import RunContext as RC
        from aegra_api.hooks import RunHooks as RH

        assert RR is RejectRun
        assert RC is RunContext
        assert RH is RunHooks

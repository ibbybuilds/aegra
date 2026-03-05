"""Unit tests for SpanEnrichmentProcessor and set_trace_context."""

import asyncio
from unittest.mock import MagicMock

import pytest

from aegra_api.observability.span_enrichment import (
    SpanEnrichmentProcessor,
    _trace_attrs,
    make_run_trace_context,
    set_trace_context,
)


class TestSetTraceContext:
    """Tests for the set_trace_context() helper."""

    def setup_method(self) -> None:
        """Reset context var before each test."""
        _trace_attrs.set(None)

    def test_sets_all_attributes_when_all_provided(self) -> None:
        """All provided values appear in the context var under both naming schemes."""
        set_trace_context(user_id="user-1", session_id="thread-1", trace_name="my_graph")

        attrs = _trace_attrs.get()
        assert attrs["langfuse.user.id"] == "user-1"
        assert attrs["user.id"] == "user-1"
        assert attrs["langfuse.session.id"] == "thread-1"
        assert attrs["session.id"] == "thread-1"
        assert attrs["langfuse.trace.name"] == "my_graph"

    def test_skips_none_values(self) -> None:
        """None arguments are not stored; only provided values appear."""
        set_trace_context(user_id="user-1")

        attrs = _trace_attrs.get()
        assert "langfuse.user.id" in attrs
        assert "user.id" in attrs
        assert "langfuse.session.id" not in attrs
        assert "langfuse.trace.name" not in attrs

    def test_empty_call_stores_none(self) -> None:
        """Calling with no arguments resets the context var to None (no-op state)."""
        set_trace_context(user_id="previous")
        set_trace_context()

        assert _trace_attrs.get() is None

    def test_only_trace_name_set(self) -> None:
        """Only trace_name provided — only that key is stored."""
        set_trace_context(trace_name="matter_agent")

        attrs = _trace_attrs.get()
        assert attrs == {"langfuse.trace.name": "matter_agent"}

    def test_metadata_stored_with_langfuse_prefix(self) -> None:
        """metadata dict keys are stored as langfuse.trace.metadata.<key>."""
        set_trace_context(
            user_id="u1",
            metadata={"run_id": "run-abc", "graph_id": "matter_agent"},
        )

        attrs = _trace_attrs.get()
        assert attrs["langfuse.trace.metadata.run_id"] == "run-abc"
        assert attrs["langfuse.trace.metadata.graph_id"] == "matter_agent"
        # first-class attrs still present
        assert attrs["langfuse.user.id"] == "u1"

    def test_empty_metadata_dict_ignored(self) -> None:
        """Passing metadata={} produces no extra keys."""
        set_trace_context(trace_name="g", metadata={})

        attrs = _trace_attrs.get()
        assert attrs == {"langfuse.trace.name": "g"}

    def test_metadata_supports_non_string_values(self) -> None:
        """metadata values may be int, float, or bool — all valid OTEL attribute types."""
        set_trace_context(
            metadata={"retry_count": 3, "latency_ms": 1.5, "cached": True},
        )

        attrs = _trace_attrs.get()
        assert attrs["langfuse.trace.metadata.retry_count"] == 3
        assert attrs["langfuse.trace.metadata.latency_ms"] == 1.5
        assert attrs["langfuse.trace.metadata.cached"] is True

    @pytest.mark.asyncio
    async def test_context_var_isolation_between_tasks(self) -> None:
        """Context var changes in one asyncio Task are not visible in another."""

        async def task_a() -> dict[str, str]:
            set_trace_context(user_id="user-a")
            await asyncio.sleep(0)
            return _trace_attrs.get()

        async def task_b() -> dict[str, str]:
            set_trace_context(user_id="user-b")
            await asyncio.sleep(0)
            return _trace_attrs.get()

        t_a = asyncio.create_task(task_a())
        t_b = asyncio.create_task(task_b())
        attrs_a, attrs_b = await asyncio.gather(t_a, t_b)
        assert attrs_a.get("user.id") == "user-a"
        assert attrs_b.get("user.id") == "user-b"


class TestSpanEnrichmentProcessor:
    """Tests for SpanEnrichmentProcessor."""

    def setup_method(self) -> None:
        """Reset context var before each test."""
        _trace_attrs.set(None)

    def test_on_start_sets_span_attributes_on_root_span(self) -> None:
        """on_start() enriches a root span (parent=None) with all context var attrs."""
        set_trace_context(user_id="u1", session_id="s1", trace_name="graph_x")
        processor = SpanEnrichmentProcessor()
        mock_span = MagicMock()
        mock_span.parent = None  # root span

        processor.on_start(mock_span)

        calls = {call.args[0]: call.args[1] for call in mock_span.set_attribute.call_args_list}
        assert calls["langfuse.user.id"] == "u1"
        assert calls["user.id"] == "u1"
        assert calls["langfuse.session.id"] == "s1"
        assert calls["session.id"] == "s1"
        assert calls["langfuse.trace.name"] == "graph_x"

    def test_on_start_skips_local_child_spans(self) -> None:
        """on_start() does NOT enrich local child spans (valid, non-remote parent)."""
        set_trace_context(user_id="u1", session_id="s1", trace_name="graph_x")
        processor = SpanEnrichmentProcessor()
        mock_span = MagicMock()
        mock_span.parent = MagicMock()
        mock_span.parent.is_valid = True
        mock_span.parent.is_remote = False  # local child span

        processor.on_start(mock_span)

        mock_span.set_attribute.assert_not_called()

    def test_on_start_enriches_span_with_remote_parent(self) -> None:
        """on_start() enriches spans whose parent arrived via W3C traceparent.

        A span with a remote parent is the local root of a distributed trace
        and must be enriched so that Langfuse receives user/session metadata.
        """
        set_trace_context(user_id="u1", trace_name="graph_x")
        processor = SpanEnrichmentProcessor()
        mock_span = MagicMock()
        mock_span.parent = MagicMock()
        mock_span.parent.is_valid = True
        mock_span.parent.is_remote = True  # arrived via traceparent header

        processor.on_start(mock_span)

        mock_span.set_attribute.assert_called()

    def test_on_start_no_op_when_context_var_empty(self) -> None:
        """on_start() sets no attributes when the context var holds an empty dict."""
        processor = SpanEnrichmentProcessor()
        mock_span = MagicMock()
        mock_span.parent = None

        processor.on_start(mock_span)

        mock_span.set_attribute.assert_not_called()

    def test_on_start_accepts_parent_context_argument(self) -> None:
        """on_start() can be called with an explicit parent_context without error."""
        set_trace_context(user_id="u2")
        processor = SpanEnrichmentProcessor()
        mock_span = MagicMock()
        mock_span.parent = None
        mock_ctx = MagicMock()

        processor.on_start(mock_span, parent_context=mock_ctx)

        mock_span.set_attribute.assert_called()

    def test_on_end_is_no_op(self) -> None:
        """on_end() completes without raising."""
        processor = SpanEnrichmentProcessor()
        processor.on_end(MagicMock())  # Should not raise

    def test_force_flush_returns_true(self) -> None:
        """force_flush() returns True unconditionally."""
        assert SpanEnrichmentProcessor().force_flush() is True
        assert SpanEnrichmentProcessor().force_flush(timeout_millis=100) is True

    def test_shutdown_is_no_op(self) -> None:
        """shutdown() completes without raising."""
        SpanEnrichmentProcessor().shutdown()  # Should not raise


class TestMakeRunTraceContext:
    """Tests for make_run_trace_context()."""

    def setup_method(self) -> None:
        """Reset context var before each test."""
        _trace_attrs.set(None)

    def test_returned_context_contains_expected_attributes(self) -> None:
        """Returned context has all trace attributes pre-set."""
        ctx = make_run_trace_context("run-1", "thread-1", "my_graph", "user-1")

        attrs = ctx.run(_trace_attrs.get)
        assert attrs["langfuse.user.id"] == "user-1"
        assert attrs["langfuse.session.id"] == "thread-1"
        assert attrs["langfuse.trace.name"] == "my_graph"
        assert attrs["langfuse.trace.metadata.run_id"] == "run-1"
        assert attrs["langfuse.trace.metadata.thread_id"] == "thread-1"
        assert attrs["langfuse.trace.metadata.graph_id"] == "my_graph"

    def test_does_not_pollute_caller_context(self) -> None:
        """Calling make_run_trace_context() does not mutate the caller's context."""
        make_run_trace_context("run-1", "thread-1", "my_graph", "user-1")

        assert _trace_attrs.get() is None

    def test_anonymous_user_omits_user_attributes(self) -> None:
        """Passing user_identity=None omits user.id keys from the context."""
        ctx = make_run_trace_context("run-1", "thread-1", "my_graph", None)

        attrs = ctx.run(_trace_attrs.get)
        assert "langfuse.user.id" not in attrs
        assert "user.id" not in attrs
        assert attrs["langfuse.trace.name"] == "my_graph"

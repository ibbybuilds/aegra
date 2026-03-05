"""Per-request OTEL span enrichment via context variables.

Sets Langfuse-compatible span attributes (``langfuse.user.id``,
``langfuse.session.id``, ``langfuse.trace.name``) from per-request
context variables on the **root span only**, enabling trace enrichment
without requiring changes to graph code.

Also sets Phoenix/OpenInference-compatible aliases (``user.id``,
``session.id``) so that the same code works when ``OTEL_TARGETS``
includes ``PHOENIX``.

Usage::

    # Inside the asyncio task that runs graph execution:
    set_trace_context(
        user_id=user.identity,
        session_id=thread_id,
        trace_name=graph_id,
    )
    # The root OTEL span created in this task will carry the attributes.
"""

import contextvars

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor

# Per-request context variable holding span attributes to inject.
# None means no trace context is set; on_start() is a no-op in that case.
_trace_attrs: contextvars.ContextVar[dict[str, str | int | float | bool] | None] = contextvars.ContextVar(
    "aegra_otel_trace_attrs", default=None
)


class SpanEnrichmentProcessor(SpanProcessor):
    """Injects per-request trace attributes onto the root span of each trace.

    Reads from the ``aegra_otel_trace_attrs`` context variable and sets
    each key/value pair as a span attribute on the **root span** only.
    A span is considered a root if it has no parent OR if its parent is a
    remote span (i.e. arrived via W3C ``traceparent`` from an upstream
    service).  Langfuse reads trace-level properties (userId, sessionId,
    name) exclusively from the root span, so enriching local child spans
    is unnecessary and produces noise in per-observation metadata.

    Call :func:`set_trace_context` inside the asyncio Task that runs
    graph execution to populate the context variable before any spans
    are created.
    """

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        if span.parent is not None and span.parent.is_valid and not span.parent.is_remote:
            # Skip local child spans only — spans whose parent arrived via
            # a remote traceparent header are still local roots and must be enriched.
            return
        attrs = _trace_attrs.get()
        if not attrs:
            return
        for key, value in attrs.items():
            span.set_attribute(key, value)

    def on_end(self, span: ReadableSpan) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def set_trace_context(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    trace_name: str | None = None,
    metadata: dict[str, str | int | float | bool] | None = None,
) -> None:
    """Populate the per-request OTEL span attributes context variable.

    Must be called inside the asyncio Task that will run graph execution.
    The root OTEL span created in this task will have the specified
    attributes injected by :class:`SpanEnrichmentProcessor`.

    Sets Langfuse-native attributes (``langfuse.*``) and their
    Phoenix/OpenInference aliases (``user.id``, ``session.id``) so a
    single call works regardless of which backend is configured in
    ``OTEL_TARGETS``.

    Args:
        user_id: User identity string.  Sets ``langfuse.user.id``
            (Langfuse) and ``user.id`` (Phoenix).  Natively filterable
            in both backends as a first-class field.
        session_id: Session identifier (typically ``thread_id``).  Sets
            ``langfuse.session.id`` (Langfuse) and ``session.id``
            (Phoenix).
        trace_name: Human-readable trace name (typically the graph ID).
            Sets ``langfuse.trace.name``.
        metadata: Arbitrary key/value pairs to attach as filterable
            metadata.  Each key is stored as
            ``langfuse.trace.metadata.<key>`` so that Langfuse exposes
            it as a queryable field rather than burying it under
            ``metadata.attributes``.  Values may be ``str``, ``int``,
            ``float``, or ``bool`` — all valid OTEL attribute types.
    """
    attrs: dict[str, str | int | float | bool] = {}
    if user_id:
        attrs["langfuse.user.id"] = user_id
        attrs["user.id"] = user_id
    if session_id:
        attrs["langfuse.session.id"] = session_id
        attrs["session.id"] = session_id
    if trace_name:
        attrs["langfuse.trace.name"] = trace_name
    if metadata:
        for key, value in metadata.items():
            attrs[f"langfuse.trace.metadata.{key}"] = value
    _trace_attrs.set(attrs or None)


def make_run_trace_context(
    run_id: str,
    thread_id: str,
    graph_id: str,
    user_identity: str | None,
) -> contextvars.Context:
    """Return an isolated context copy with OTEL trace attributes pre-set for a run.

    Creates a copy of the current context and populates it with per-request
    span attributes.  Pass the returned context to ``asyncio.create_task(...,
    context=ctx)`` so the background task starts with the correct trace data.
    """
    ctx = contextvars.copy_context()
    ctx.run(
        set_trace_context,
        user_id=user_identity,
        session_id=thread_id,
        trace_name=graph_id,
        metadata={"run_id": run_id, "thread_id": thread_id, "graph_id": graph_id},
    )
    return ctx

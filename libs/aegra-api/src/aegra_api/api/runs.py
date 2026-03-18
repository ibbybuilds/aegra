"""Run endpoints for Agent Protocol"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from langgraph.types import Command, Send
from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from aegra_api.core.auth_ctx import with_auth_ctx
from aegra_api.core.auth_deps import auth_dependency, get_current_user
from aegra_api.core.auth_handlers import build_auth_context, handle_event
from aegra_api.core.orm import Assistant as AssistantORM
from aegra_api.core.orm import Run as RunORM
from aegra_api.core.orm import Thread as ThreadORM
from aegra_api.core.orm import _get_session_maker, get_session
from aegra_api.core.serializers import GeneralSerializer
from aegra_api.core.sse import create_end_event, get_sse_headers
from aegra_api.models import Run, RunCreate, RunStatus, User
from aegra_api.models.errors import CONFLICT, NOT_FOUND, SSE_RESPONSE
from aegra_api.observability.span_enrichment import make_run_trace_context
from aegra_api.services.broker import broker_manager
from aegra_api.services.graph_streaming import stream_graph_events
from aegra_api.services.langgraph_service import create_run_config, get_langgraph_service
from aegra_api.services.streaming_service import streaming_service
from aegra_api.utils.assistants import resolve_assistant_id
from aegra_api.utils.run_utils import (
    _merge_jsonb,
)
from aegra_api.utils.status_compat import validate_run_status

router = APIRouter(tags=["Thread Runs"], dependencies=auth_dependency)

logger = structlog.getLogger(__name__)
serializer = GeneralSerializer()


# NOTE: We keep only an in-memory task registry for asyncio.Task handles.
# All run metadata/state is persisted via ORM.
active_runs: dict[str, asyncio.Task] = {}

# Default stream modes for background run execution
DEFAULT_STREAM_MODES = ["values"]


def map_command_to_langgraph(cmd: dict[str, Any]) -> Command:
    """Convert API command to LangGraph Command"""
    goto = cmd.get("goto")
    if goto is not None and not isinstance(goto, list):
        goto = [goto]

    update = cmd.get("update")
    if isinstance(update, (tuple, list)) and all(
        isinstance(t, (tuple, list)) and len(t) == 2 and isinstance(t[0], str) for t in update
    ):
        update = [tuple(t) for t in update]

    return Command(
        update=update,
        goto=([it if isinstance(it, str) else Send(it["node"], it["input"]) for it in goto] if goto else None),
        resume=cmd.get("resume"),
    )


def _resolve_context(
    config: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Derive context from configurable if not explicitly provided.

    When the caller provides context, it is used as-is. Otherwise,
    context is derived from config.configurable for backward compat.
    Raises HTTPException(422) if configurable is not a mapping.
    """
    configurable = config.get("configurable", {})
    if not isinstance(configurable, dict):
        raise HTTPException(status_code=422, detail="`config.configurable` must be a mapping")
    if not context:
        return configurable.copy()
    return context


async def set_thread_status(session: AsyncSession, thread_id: str, status: str) -> None:
    """Update the status column of a thread.

    Status is validated to ensure it conforms to API specification.
    """
    # Validate status conforms to API specification
    from aegra_api.utils.status_compat import validate_thread_status

    validated_status = validate_thread_status(status)
    result = cast(
        CursorResult,
        await session.execute(
            update(ThreadORM)
            .where(ThreadORM.thread_id == thread_id)
            .values(status=validated_status, updated_at=datetime.now(UTC))
        ),
    )
    await session.commit()

    # Verify thread was updated (matching row exists)
    if result.rowcount == 0:
        raise HTTPException(404, f"Thread '{thread_id}' not found")


async def update_thread_metadata(
    session: AsyncSession,
    thread_id: str,
    assistant_id: str,
    graph_id: str,
    user_id: str | None = None,
) -> None:
    """Update thread metadata with assistant and graph information (dialect agnostic).

    If thread doesn't exist, auto-creates it.
    """
    # Read-modify-write to avoid DB-specific JSON concat operators
    thread = await session.scalar(select(ThreadORM).where(ThreadORM.thread_id == thread_id))

    if not thread:
        # Auto-create thread if it doesn't exist
        if not user_id:
            raise HTTPException(400, "Cannot auto-create thread: user_id is required")

        metadata = {
            "owner": user_id,
            "assistant_id": str(assistant_id),
            "graph_id": graph_id,
            "thread_name": "",
        }

        thread_orm = ThreadORM(
            thread_id=thread_id,
            status="idle",
            metadata_json=metadata,
            user_id=user_id,
        )
        session.add(thread_orm)
        await session.commit()
        return

    md = dict(getattr(thread, "metadata_json", {}) or {})
    md.update(
        {
            "assistant_id": str(assistant_id),
            "graph_id": graph_id,
        }
    )
    await session.execute(
        update(ThreadORM).where(ThreadORM.thread_id == thread_id).values(metadata_json=md, updated_at=datetime.now(UTC))
    )
    await session.commit()


async def _validate_resume_command(session: AsyncSession, thread_id: str, command: dict[str, Any] | None) -> None:
    """Validate resume command requirements."""
    if command and command.get("resume") is not None:
        # Check if thread exists and is in interrupted state
        thread_stmt = select(ThreadORM).where(ThreadORM.thread_id == thread_id)
        thread = await session.scalar(thread_stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")
        if thread.status != "interrupted":
            raise HTTPException(400, "Cannot resume: thread is not in interrupted state")


@router.post("/threads/{thread_id}/runs", response_model=Run, responses={**NOT_FOUND, **CONFLICT})
async def create_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """Create and execute a new run.

    Starts graph execution asynchronously and returns the run record
    immediately with status `pending`. Poll the run or use the stream
    endpoint to follow progress. Provide either `input` or `command` (for
    human-in-the-loop resumption) but not both.
    """
    # Authorization check (create_run action on threads resource)
    ctx = build_auth_context(user, "threads", "create_run")
    value = {**request.model_dump(), "thread_id": thread_id}
    filters = await handle_event(ctx, value)

    # If handler modified config/context, update request
    if filters:
        if "config" in filters and isinstance(filters["config"], dict):
            request.config = {**(request.config or {}), **filters["config"]}
        if "context" in filters and isinstance(filters["context"], dict):
            request.context = {**(request.context or {}), **filters["context"]}
    else:
        value_config = value.get("config")
        if isinstance(value_config, dict):
            request.config = {**(request.config or {}), **value_config}

        value_context = value.get("context")
        if isinstance(value_context, dict):
            request.context = {**(request.context or {}), **value_context}

    # Validate resume command requirements early
    await _validate_resume_command(session, thread_id, request.command)

    run_id = str(uuid4())

    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    logger.info(f"[create_run] scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}")

    # Validate assistant exists and get its graph_id. If a graph_id was provided
    # instead of an assistant UUID, map it deterministically and fall back to the
    # default assistant created at startup.
    requested_id = str(request.assistant_id)
    available_graphs = langgraph_service.list_graphs()
    resolved_assistant_id = resolve_assistant_id(requested_id, available_graphs)

    config = request.config or {}
    context = _resolve_context(config, request.context or {})

    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == resolved_assistant_id,
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")

    config = _merge_jsonb(assistant.config, config)
    context = _merge_jsonb(assistant.context, context)

    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(404, f"Graph '{assistant.graph_id}' not found for assistant")

    # Mark thread as busy and update metadata with assistant/graph info
    # update_thread_metadata will auto-create thread if it doesn't exist
    await update_thread_metadata(session, thread_id, assistant.assistant_id, assistant.graph_id, user.identity)
    await set_thread_status(session, thread_id, "busy")

    # Persist run record via ORM model in core.orm (Run table)
    now = datetime.now(UTC)
    run_orm = RunORM(
        run_id=run_id,  # explicitly set (DB can also default-generate if omitted)
        thread_id=thread_id,
        assistant_id=resolved_assistant_id,
        status="pending",
        input=request.input or {},
        config=config,
        context=context,
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )
    session.add(run_orm)
    await session.commit()

    # Build response from ORM -> Pydantic
    run = Run.model_validate(run_orm)

    # Start execution asynchronously.
    # Don't pass the session to avoid transaction conflicts.
    task = asyncio.create_task(
        execute_run_async(
            run_id,
            thread_id,
            assistant.graph_id,
            request.input or {},
            user,
            config,
            context,
            request.stream_mode,
            None,  # Don't pass session to avoid conflicts
            request.checkpoint,
            request.command,
            request.interrupt_before,
            request.interrupt_after,
            request.multitask_strategy,
            request.stream_subgraphs,
        ),
        context=make_run_trace_context(run_id, thread_id, assistant.graph_id, user.identity),
    )
    logger.info(f"[create_run] background task created task_id={id(task)} for run_id={run_id}")
    active_runs[run_id] = task

    return run


@router.post("/threads/{thread_id}/runs/stream", responses={**SSE_RESPONSE, **NOT_FOUND, **CONFLICT})
async def create_and_stream_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Create a new run and stream its execution via SSE.

    Returns a `text/event-stream` response with Server-Sent Events. Each
    event has a `type` field (e.g. `values`, `updates`, `messages`,
    `metadata`, `end`) and a JSON `data` payload.

    Set `on_disconnect` to `"continue"` if the run should keep executing
    after the client disconnects (default is `"cancel"`). Use `stream_mode`
    to control which event types are emitted.
    """

    # Validate resume command requirements early
    await _validate_resume_command(session, thread_id, request.command)

    run_id = str(uuid4())

    # Get LangGraph service
    langgraph_service = get_langgraph_service()
    logger.info(
        f"[create_and_stream_run] scheduling background task run_id={run_id} thread_id={thread_id} user={user.identity}"
    )

    # Validate assistant exists and get its graph_id. Allow passing a graph_id
    # by mapping it to a deterministic assistant ID.
    requested_id = str(request.assistant_id)
    available_graphs = langgraph_service.list_graphs()

    resolved_assistant_id = resolve_assistant_id(requested_id, available_graphs)

    config = request.config or {}
    context = _resolve_context(config, request.context or {})

    assistant_stmt = select(AssistantORM).where(
        AssistantORM.assistant_id == resolved_assistant_id,
    )
    assistant = await session.scalar(assistant_stmt)
    if not assistant:
        raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")

    config = _merge_jsonb(assistant.config, config)
    context = _merge_jsonb(assistant.context, context)

    # Validate the assistant's graph exists
    available_graphs = langgraph_service.list_graphs()
    if assistant.graph_id not in available_graphs:
        raise HTTPException(404, f"Graph '{assistant.graph_id}' not found for assistant")

    # Mark thread as busy and update metadata with assistant/graph info
    # update_thread_metadata will auto-create thread if it doesn't exist
    await update_thread_metadata(session, thread_id, assistant.assistant_id, assistant.graph_id, user.identity)
    await set_thread_status(session, thread_id, "busy")

    # Persist run record
    now = datetime.now(UTC)
    run_orm = RunORM(
        run_id=run_id,
        thread_id=thread_id,
        assistant_id=resolved_assistant_id,
        status="running",
        input=request.input or {},
        config=config,
        context=context,
        user_id=user.identity,
        created_at=now,
        updated_at=now,
        output=None,
        error_message=None,
    )
    session.add(run_orm)
    await session.commit()

    # Build response model for stream context
    run = Run.model_validate(run_orm)

    # Start background execution that will populate the broker.
    # Don't pass the session to avoid transaction conflicts.
    task = asyncio.create_task(
        execute_run_async(
            run_id,
            thread_id,
            assistant.graph_id,
            request.input or {},
            user,
            config,
            context,
            request.stream_mode,
            None,  # Don't pass session to avoid conflicts
            request.checkpoint,
            request.command,
            request.interrupt_before,
            request.interrupt_after,
            request.multitask_strategy,
            request.stream_subgraphs,
        ),
        context=make_run_trace_context(run_id, thread_id, assistant.graph_id, user.identity),
    )
    logger.info(f"[create_and_stream_run] background task created task_id={id(task)} for run_id={run_id}")
    active_runs[run_id] = task

    # Extract requested stream mode(s)
    stream_mode = request.stream_mode
    if not stream_mode and config and "stream_mode" in config:
        stream_mode = config["stream_mode"]

    # Stream immediately from broker (which will also include replay of any early events)
    # Default to cancel on disconnect - this matches user expectation that clicking
    # "Cancel" in the frontend will stop the backend task. Users can explicitly
    # set on_disconnect="continue" if they want the task to continue.
    cancel_on_disconnect = (request.on_disconnect or "cancel").lower() == "cancel"

    return StreamingResponse(
        streaming_service.stream_run_execution(
            run,
            None,
            cancel_on_disconnect=cancel_on_disconnect,
        ),
        media_type="text/event-stream",
        headers={
            **get_sse_headers(),
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        },
    )


@router.get("/threads/{thread_id}/runs/{run_id}", response_model=Run, responses={**NOT_FOUND})
async def get_run(
    thread_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """Get a run by its ID.

    Returns the current state of the run including its status, input, output,
    and error information.
    """
    # Authorization check (read action on runs resource)
    ctx = build_auth_context(user, "runs", "read")
    value = {"run_id": run_id, "thread_id": thread_id}
    await handle_event(ctx, value)

    stmt = select(RunORM).where(
        RunORM.run_id == str(run_id),
        RunORM.thread_id == thread_id,
        RunORM.user_id == user.identity,
    )
    logger.info(f"[get_run] querying DB run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(stmt)
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # Refresh to ensure we have the latest data (in case background task updated it)
    await session.refresh(run_orm)

    logger.info(
        f"[get_run] found run status={run_orm.status} user={user.identity} thread_id={thread_id} run_id={run_id}"
    )
    # Convert to Pydantic
    return Run.model_validate(run_orm)


@router.get("/threads/{thread_id}/runs", response_model=list[Run])
async def list_runs(
    thread_id: str,
    limit: int = Query(10, ge=1, description="Maximum number of runs to return"),
    offset: int = Query(0, ge=0, description="Number of runs to skip for pagination"),
    status: str | None = Query(
        None, description="Filter by run status (e.g. pending, running, success, error, interrupted)"
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Run]:
    """List runs for a thread.

    Returns runs ordered by creation time (newest first). Use `status` to
    filter and `limit`/`offset` to paginate.
    """
    stmt = (
        select(RunORM)
        .where(
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
            *([RunORM.status == status] if status else []),
        )
        .limit(limit)
        .offset(offset)
        .order_by(RunORM.created_at.desc())
    )
    logger.info(f"[list_runs] querying DB thread_id={thread_id} user={user.identity}")
    result = await session.scalars(stmt)
    rows = result.all()
    runs = [Run.model_validate(r) for r in rows]
    logger.info(f"[list_runs] total={len(runs)} user={user.identity} thread_id={thread_id}")
    return runs


@router.patch("/threads/{thread_id}/runs/{run_id}", response_model=Run, responses={**NOT_FOUND})
async def update_run(
    thread_id: str,
    run_id: str,
    request: RunStatus,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """Update a run's status.

    Primarily used to interrupt a running execution. Set `status` to
    `"interrupted"` to cooperatively stop the run.
    """
    logger.info(f"[update_run] fetch for update run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # Handle interruption/cancellation
    # Validate status conforms to API specification
    validated_status = validate_run_status(request.status)

    if validated_status == "interrupted":
        logger.info(f"[update_run] cancelling/interrupting run_id={run_id} user={user.identity} thread_id={thread_id}")
        # Handle interruption - use interrupt_run for cooperative interruption
        await streaming_service.interrupt_run(run_id)
        logger.info(f"[update_run] set DB status=interrupted run_id={run_id}")
        await session.execute(
            update(RunORM)
            .where(RunORM.run_id == str(run_id))
            .values(status="interrupted", updated_at=datetime.now(UTC))
        )
        await session.commit()
        logger.info(f"[update_run] commit done (interrupted) run_id={run_id}")

    # Return final run state
    run_orm = await session.scalar(select(RunORM).where(RunORM.run_id == run_id))
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")
    # Refresh to ensure we have the latest data after our own update
    await session.refresh(run_orm)
    return Run.model_validate(run_orm)


@router.get("/threads/{thread_id}/runs/{run_id}/join", responses={**NOT_FOUND})
async def join_run(
    thread_id: str,
    run_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Wait for a run to complete and return its output.

    If the run is already in a terminal state (success, error, interrupted),
    the output is returned immediately. Otherwise the server waits up to 30
    seconds for the background task to finish.

    Sessions are managed manually (not via Depends) to avoid holding a pool
    connection during the long wait, which would starve background tasks.
    """
    maker = _get_session_maker()

    # Short-lived session: validate run exists and check terminal state
    async with maker() as session:
        run_orm = await session.scalar(
            select(RunORM).where(
                RunORM.run_id == str(run_id),
                RunORM.thread_id == thread_id,
                RunORM.user_id == user.identity,
            )
        )
        if not run_orm:
            raise HTTPException(404, f"Run '{run_id}' not found")

        terminal_states = ["success", "error", "interrupted"]
        if run_orm.status in terminal_states:
            return getattr(run_orm, "output", None) or {}

    # No pool connection held during the wait.
    # asyncio.shield prevents wait_for from cancelling the background task on timeout.
    task = active_runs.get(run_id)
    if task:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=30.0)
        except TimeoutError:
            pass
        except asyncio.CancelledError:
            pass

    # Short-lived session: read final output
    async with maker() as session:
        run_orm = await session.scalar(
            select(RunORM).where(
                RunORM.run_id == run_id,
                RunORM.thread_id == thread_id,
                RunORM.user_id == user.identity,
            )
        )
        if not run_orm:
            raise HTTPException(404, f"Run '{run_id}' not found")
        return run_orm.output or {}


@router.post("/threads/{thread_id}/runs/wait", responses={**NOT_FOUND, **CONFLICT})
async def wait_for_run(
    thread_id: str,
    request: RunCreate,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a run, execute it, and wait for completion.

    Combines run creation and execution with synchronous waiting. Returns the
    final output directly (not the Run object). The server waits up to 5
    minutes for the run to finish. If the run times out, the current output
    (which may be empty) is returned.

    Sessions are managed manually (not via Depends) to avoid holding a pool
    connection during the long wait, which would starve background tasks.
    """
    maker = _get_session_maker()

    # Session block 1: all pre-execution DB work (validate, create run, commit)
    async with maker() as session:
        # Validate resume command requirements early
        await _validate_resume_command(session, thread_id, request.command)

        run_id = str(uuid4())

        # Get LangGraph service
        langgraph_service = get_langgraph_service()
        logger.info(f"[wait_for_run] creating run run_id={run_id} thread_id={thread_id} user={user.identity}")

        # Validate assistant exists and get its graph_id
        requested_id = str(request.assistant_id)
        available_graphs = langgraph_service.list_graphs()
        resolved_assistant_id = resolve_assistant_id(requested_id, available_graphs)

        config = request.config or {}
        context = _resolve_context(config, request.context or {})

        assistant_stmt = select(AssistantORM).where(
            AssistantORM.assistant_id == resolved_assistant_id,
        )
        assistant = await session.scalar(assistant_stmt)
        if not assistant:
            raise HTTPException(404, f"Assistant '{request.assistant_id}' not found")

        config = _merge_jsonb(assistant.config, config)
        context = _merge_jsonb(assistant.context, context)

        # Validate the assistant's graph exists
        available_graphs = langgraph_service.list_graphs()
        if assistant.graph_id not in available_graphs:
            raise HTTPException(404, f"Graph '{assistant.graph_id}' not found for assistant")

        # Mark thread as busy and update metadata with assistant/graph info
        # update_thread_metadata will auto-create thread if it doesn't exist
        await update_thread_metadata(session, thread_id, assistant.assistant_id, assistant.graph_id, user.identity)
        await set_thread_status(session, thread_id, "busy")

        # Persist run record
        now = datetime.now(UTC)
        run_orm = RunORM(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id=resolved_assistant_id,
            status="pending",
            input=request.input or {},
            config=config,
            context=context,
            user_id=user.identity,
            created_at=now,
            updated_at=now,
            output=None,
            error_message=None,
        )
        session.add(run_orm)
        await session.commit()

        # Capture values needed after session closes
        graph_id = assistant.graph_id

    # No pool connection held from here — safe for long waits

    # Start execution asynchronously.
    task = asyncio.create_task(
        execute_run_async(
            run_id,
            thread_id,
            graph_id,
            request.input or {},
            user,
            config,
            context,
            request.stream_mode,
            None,  # Don't pass session to avoid conflicts
            request.checkpoint,
            request.command,
            request.interrupt_before,
            request.interrupt_after,
            request.multitask_strategy,
            request.stream_subgraphs,
        ),
        context=make_run_trace_context(run_id, thread_id, graph_id, user.identity),
    )
    logger.info(f"[wait_for_run] background task created task_id={id(task)} for run_id={run_id}")
    active_runs[run_id] = task

    # Wait for task to complete with timeout
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=300.0)  # 5 minute timeout
    except TimeoutError:
        logger.warning(f"[wait_for_run] timeout waiting for run_id={run_id}")
    except asyncio.CancelledError:
        logger.info(f"[wait_for_run] cancelled run_id={run_id}")
    except Exception:
        logger.exception(f"[wait_for_run] unexpected exception in run_id={run_id}")

    # Session block 2: read final output
    async with maker() as session:
        run_orm = await session.scalar(
            select(RunORM).where(
                RunORM.run_id == run_id,
                RunORM.thread_id == thread_id,
                RunORM.user_id == user.identity,
            )
        )
        if not run_orm:
            raise HTTPException(500, f"Run '{run_id}' disappeared during execution")

        if run_orm.status == "error":
            logger.error(f"[wait_for_run] run failed run_id={run_id} error={run_orm.error_message}")

        return run_orm.output or {}


# TODO: check if this method is actually required because the implementation doesn't seem correct.
@router.get("/threads/{thread_id}/runs/{run_id}/stream", responses={**SSE_RESPONSE, **NOT_FOUND})
async def stream_run(
    thread_id: str,
    run_id: str,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    _stream_mode: str | None = Query(None, description="Override the stream mode for this connection."),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """Stream an existing run's execution via SSE.

    Attach to a run that was created without streaming (e.g. via the create
    endpoint) to receive its events in real time. If the run has already
    finished, a single `end` event is emitted. Use the `Last-Event-ID`
    header to resume from a specific event after a disconnect.
    """
    logger.info(f"[stream_run] fetch for stream run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    logger.info(f"[stream_run] status={run_orm.status} user={user.identity} thread_id={thread_id} run_id={run_id}")
    # If already terminal, emit a final end event
    terminal_states = ["success", "error", "interrupted"]
    if run_orm.status in terminal_states:

        async def generate_final() -> AsyncIterator[str]:
            yield create_end_event()

        logger.info(f"[stream_run] starting terminal stream run_id={run_id} status={run_orm.status}")
        return StreamingResponse(
            generate_final(),
            media_type="text/event-stream",
            headers={
                **get_sse_headers(),
                "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
                "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
            },
        )

    # Stream active or pending runs via broker

    # Build a lightweight Pydantic Run from ORM for streaming context (IDs already strings)
    run_model = Run.model_validate(run_orm)

    return StreamingResponse(
        streaming_service.stream_run_execution(run_model, last_event_id, cancel_on_disconnect=False),
        media_type="text/event-stream",
        headers={
            **get_sse_headers(),
            "Location": f"/threads/{thread_id}/runs/{run_id}/stream",
            "Content-Location": f"/threads/{thread_id}/runs/{run_id}",
        },
    )


@router.post(
    "/threads/{thread_id}/runs/{run_id}/cancel",
    response_model=Run,
    responses={**NOT_FOUND},
)
async def cancel_run_endpoint(
    thread_id: str,
    run_id: str,
    wait: int = Query(0, ge=0, le=1, description="Set to 1 to wait for the run task to settle before returning."),
    action: str = Query(
        "cancel",
        pattern="^(cancel|interrupt)$",
        description="Cancellation strategy: 'cancel' for hard cancel, 'interrupt' for cooperative interrupt.",
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    """Cancel or interrupt a running execution.

    Use `action=cancel` to hard-cancel the run immediately, or
    `action=interrupt` to cooperatively interrupt (the graph can handle the
    interrupt and save partial state). Set `wait=1` to block until the
    background task has fully settled before returning the updated run.
    """
    logger.info(f"[cancel_run] fetch run run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    if action == "interrupt":
        logger.info(f"[cancel_run] interrupt run_id={run_id} user={user.identity} thread_id={thread_id}")
        await streaming_service.interrupt_run(run_id)
        # Persist status as interrupted
        await session.execute(
            update(RunORM)
            .where(RunORM.run_id == str(run_id))
            .values(status="interrupted", updated_at=datetime.now(UTC))
        )
        await session.commit()
    else:
        logger.info(f"[cancel_run] cancel run_id={run_id} user={user.identity} thread_id={thread_id}")
        await streaming_service.cancel_run(run_id)
        # Persist status as interrupted
        await session.execute(
            update(RunORM)
            .where(RunORM.run_id == str(run_id))
            .values(status="interrupted", updated_at=datetime.now(UTC))
        )
        await session.commit()

    # Optionally wait for background task
    if wait:
        task = active_runs.get(run_id)
        if task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # Reload and return updated Run (do NOT delete here; deletion is a separate endpoint)
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == run_id,
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found after cancellation")
    return Run.model_validate(run_orm)


async def execute_run_async(
    run_id: str,
    thread_id: str,
    graph_id: str,
    input_data: dict,
    user: User,
    config: dict | None = None,
    context: dict | None = None,
    stream_mode: str | list[str] | None = None,
    session: AsyncSession | None = None,
    checkpoint: dict | None = None,
    command: dict[str, Any] | None = None,
    interrupt_before: str | list[str] | None = None,
    interrupt_after: str | list[str] | None = None,
    _multitask_strategy: str | None = None,
    subgraphs: bool | None = False,
) -> None:
    """Execute run asynchronously in background using streaming to capture all events."""
    owns_session = session is None
    if session is None:
        maker = _get_session_maker()
        session = maker()

    try:
        # Update status
        await update_run_status(run_id, "running", session=session)

        # Get graph and execute
        langgraph_service = get_langgraph_service()

        run_config = create_run_config(run_id, thread_id, user, config or {}, checkpoint)

        # Handle human-in-the-loop fields
        if interrupt_before is not None:
            run_config["interrupt_before"] = (
                interrupt_before if isinstance(interrupt_before, list) else [interrupt_before]
            )
        if interrupt_after is not None:
            run_config["interrupt_after"] = interrupt_after if isinstance(interrupt_after, list) else [interrupt_after]

        # Note: multitask_strategy is handled at the run creation level, not execution level
        # It controls concurrent run behavior, not graph execution behavior

        # Determine input for execution (either input_data or command)
        if command is not None:
            # When command is provided, it replaces input entirely
            execution_input = map_command_to_langgraph(command)
        else:
            # No command, use regular input
            execution_input = input_data

        # Execute using streaming to capture events for later replay
        event_counter = 0
        final_output = None
        has_interrupt = False

        # Prepare stream modes for execution
        if stream_mode is None:
            stream_mode_list = DEFAULT_STREAM_MODES.copy()
        elif isinstance(stream_mode, str):
            stream_mode_list = [stream_mode]
        else:
            stream_mode_list = stream_mode.copy()

        async with (
            langgraph_service.get_graph(
                graph_id,
                config=run_config,
                access_context="threads.create_run",
                user=user,
                context=context,
            ) as graph,
            with_auth_ctx(user, []),
        ):
            # Stream events using the graph_streaming service
            try:
                async for event_type, event_data in stream_graph_events(
                    graph=graph,
                    input_data=execution_input,
                    config=run_config,
                    stream_mode=stream_mode_list,
                    context=context,
                    subgraphs=subgraphs,
                    on_checkpoint=lambda _: None,  # Can add checkpoint handling if needed
                    on_task_result=lambda _: None,  # Can add task result handling if needed
                ):
                    try:
                        # Increment event counter
                        event_counter += 1
                        event_id = f"{run_id}_event_{event_counter}"

                        # Create event tuple for broker/storage
                        event_tuple = (event_type, event_data)

                        # Forward to broker for live consumers (already filtered by graph_streaming)
                        await streaming_service.put_to_broker(run_id, event_id, event_tuple)

                        # Store for replay (already filtered by graph_streaming)
                        await streaming_service.store_event_from_raw(run_id, event_id, event_tuple)

                        # Check for interrupt
                        if isinstance(event_data, dict) and "__interrupt__" in event_data:
                            has_interrupt = True

                        # Track final output from values events (handles both "values" and "values|namespace")
                        if event_type.startswith("values"):
                            final_output = event_data

                    except Exception as event_error:
                        # Error processing individual event - send error to frontend immediately
                        logger.error(f"[execute_run_async] error processing event for run_id={run_id}: {event_error}")
                        error_type = type(event_error).__name__
                        await streaming_service.signal_run_error(run_id, str(event_error), error_type)
                        raise

            except Exception as stream_error:
                # Error during streaming (e.g., graph execution error)
                # Send error to frontend before re-raising
                logger.error(f"[execute_run_async] streaming error for run_id={run_id}: {stream_error}")
                error_type = type(stream_error).__name__
                await streaming_service.signal_run_error(run_id, str(stream_error), error_type)
                raise

        if has_interrupt:
            await update_run_status(run_id, "interrupted", output=final_output or {}, session=session)
            if not session:
                raise RuntimeError(f"No database session available to update thread {thread_id} status")
            await set_thread_status(session, thread_id, "interrupted")

        else:
            # Update with results - use standard status
            await update_run_status(run_id, "success", output=final_output or {}, session=session)
            # Mark thread back to idle
            if not session:
                raise RuntimeError(f"No database session available to update thread {thread_id} status")
            await set_thread_status(session, thread_id, "idle")

    except asyncio.CancelledError:
        # Store empty output to avoid JSON serialization issues - use standard status
        await update_run_status(run_id, "interrupted", output={}, session=session)
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status") from None
        await set_thread_status(session, thread_id, "idle")
        # Signal cancellation to broker
        await streaming_service.signal_run_cancelled(run_id)
        raise
    except Exception as e:
        # Log with full traceback so bugs are visible in logs
        logger.exception(f"[execute_run_async] run failed run_id={run_id}")
        # Store empty output to avoid JSON serialization issues - use standard status
        await update_run_status(run_id, "error", output={}, error=str(e), session=session)
        if not session:
            raise RuntimeError(f"No database session available to update thread {thread_id} status") from None
        # Set thread status to "error" when run fails (matches API specification)
        await set_thread_status(session, thread_id, "error")
        # Note: Error event already sent to broker in inner exception handler
        # Only signal if broker still exists (cleanup not yet called)
        broker = broker_manager.get_broker(run_id)
        if broker and not broker.is_finished():
            error_type = type(e).__name__
            await streaming_service.signal_run_error(run_id, str(e), error_type)
        # Don't re-raise: this runs as a background task (asyncio.create_task),
        # so re-raising causes "Task exception was never retrieved" warnings.
        # The error is already fully handled (run status, thread status, broker).
    finally:
        # Clean up broker
        await streaming_service.cleanup_run(run_id)
        active_runs.pop(run_id, None)
        if owns_session:
            await session.close()


async def update_run_status(
    run_id: str,
    status: str,
    output: Any = None,
    error: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Update run status in database (persisted). If session not provided, opens a short-lived session.

    Status is validated to ensure it conforms to API specification.
    """
    # Validate status conforms to API specification
    validated_status = validate_run_status(status)

    owns_session = False
    if session is None:
        maker = _get_session_maker()
        session = maker()  # type: ignore[assignment]
        owns_session = True
    try:
        values = {"status": validated_status, "updated_at": datetime.now(UTC)}
        if output is not None:
            # Serialize output to ensure JSON compatibility
            try:
                serialized_output = serializer.serialize(output)
                values["output"] = serialized_output
            except Exception as e:
                logger.warning(f"Failed to serialize output for run {run_id}: {e}")
                values["output"] = {
                    "error": "Output serialization failed",
                    "original_type": str(type(output)),
                }
        if error is not None:
            values["error_message"] = error
        logger.info(f"[update_run_status] updating DB run_id={run_id} status={validated_status}")
        await session.execute(update(RunORM).where(RunORM.run_id == str(run_id)).values(**values))  # type: ignore[arg-type]
        await session.commit()
        logger.info(f"[update_run_status] commit done run_id={run_id}")
    finally:
        # Close only if we created it here
        if owns_session:
            await session.close()  # type: ignore[func-returns-value]


@router.delete(
    "/threads/{thread_id}/runs/{run_id}",
    status_code=204,
    responses={**NOT_FOUND, **CONFLICT},
)
async def delete_run(
    thread_id: str,
    run_id: str,
    force: int = Query(0, ge=0, le=1, description="Set to 1 to cancel an active run before deleting it."),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a run record.

    If the run is active (pending or running) and `force=0`, returns 409
    Conflict. Set `force=1` to cancel the run first (best-effort) and then
    delete it. Returns 204 No Content on success.
    """
    # Authorization check (delete action on runs resource)
    ctx = build_auth_context(user, "runs", "delete")
    value = {"run_id": run_id, "thread_id": thread_id}
    await handle_event(ctx, value)
    logger.info(f"[delete_run] fetch run run_id={run_id} thread_id={thread_id} user={user.identity}")
    run_orm = await session.scalar(
        select(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    if not run_orm:
        raise HTTPException(404, f"Run '{run_id}' not found")

    # If active and not forcing, reject deletion
    if run_orm.status in ["pending", "running"] and not force:
        raise HTTPException(
            status_code=409,
            detail="Run is active. Retry with force=1 to cancel and delete.",
        )

    # If forcing and active, cancel first
    if force and run_orm.status in ["pending", "running"]:
        logger.info(f"[delete_run] force-cancelling active run run_id={run_id}")
        await streaming_service.cancel_run(run_id)
        # Best-effort: wait for bg task to settle
        task = active_runs.get(run_id)
        if task:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # Delete the record
    await session.execute(
        delete(RunORM).where(
            RunORM.run_id == str(run_id),
            RunORM.thread_id == thread_id,
            RunORM.user_id == user.identity,
        )
    )
    await session.commit()

    # Clean up active task if exists
    task = active_runs.pop(run_id, None)
    if task and not task.done():
        task.cancel()

    # 204 No Content
    return

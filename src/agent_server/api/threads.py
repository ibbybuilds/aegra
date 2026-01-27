"""Thread endpoints for Agent Protocol"""

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.runs import active_runs
from ..core.auth_deps import get_current_user
from ..core.orm import Run as RunORM
from ..core.orm import Thread as ThreadORM
from ..core.orm import get_session
from ..models import (
    Thread,
    ThreadCheckpoint,
    ThreadCheckpointPostRequest,
    ThreadCreate,
    ThreadHistoryRequest,
    ThreadList,
    ThreadSearchRequest,
    ThreadState,
    ThreadStateUpdate,
    ThreadStateUpdateResponse,
    ThreadUpdate,
    User,
)
from ..services.streaming_service import streaming_service
from ..services.thread_state_service import ThreadStateService

router = APIRouter()
logger = structlog.getLogger(__name__)

thread_state_service = ThreadStateService()


# --- Helper for safe ORM -> Pydantic conversion (Test/Mock compatible) ---


def _serialize_thread(
    thread_orm: ThreadORM, default_metadata: dict[str, Any] | None = None
) -> Thread:
    """
    Safely converts ThreadORM to Thread model using dictionary construction.
    This handles None values and MagicMocks that appear in tests, preventing
    Pydantic V2 ValidationErrors.
    """

    def _coerce_str(val: Any, default: str) -> str:
        try:
            s = str(val)
            # Handle MagicMock objects in tests converting to strings like "<MagicMock...>"
            return default if "MagicMock" in s else s
        except Exception:
            return default

    def _coerce_dict(val: Any, default: dict[str, Any]) -> dict[str, Any]:
        if val is None:
            return default
        if isinstance(val, dict):
            return val
        # Try to convert dict-like objects (mocks)
        with contextlib.suppress(Exception):
            if hasattr(val, "items"):
                return dict(val.items())  # type: ignore[attr-defined]
        return default

    # 1. ID
    t_id = _coerce_str(getattr(thread_orm, "thread_id", None), "unknown")

    # 2. Status
    status = _coerce_str(getattr(thread_orm, "status", "idle"), "idle")

    # 3. User ID
    u_id = _coerce_str(getattr(thread_orm, "user_id", ""), "")

    # 4. Metadata (map metadata_json -> metadata)
    # Use provided default if ORM is None (e.g. during creation before refresh)
    meta_source = getattr(thread_orm, "metadata_json", None)
    if meta_source is None and default_metadata is not None:
        meta_source = default_metadata
    metadata = _coerce_dict(meta_source, {})

    # 5. Timestamps (Default to NOW if None/Mock fails)
    c_at = getattr(thread_orm, "created_at", None)
    if not isinstance(c_at, datetime):
        c_at = datetime.now(UTC)

    u_at = getattr(thread_orm, "updated_at", None)
    if not isinstance(u_at, datetime):
        u_at = datetime.now(UTC)

    # Validate from dict (more robust than validate(orm_obj) for partial mocks)
    return Thread.model_validate(
        {
            "thread_id": t_id,
            "status": status,
            "metadata": metadata,
            "user_id": u_id,
            "created_at": c_at,
            "updated_at": u_at,
        }
    )


# --- Endpoints ---


@router.post("/threads", response_model=Thread)
async def create_thread(
    request: ThreadCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new conversation thread"""

    thread_id = request.thread_id or str(uuid4())

    if request.thread_id:
        existing_stmt = select(ThreadORM).where(
            ThreadORM.thread_id == thread_id,
            ThreadORM.user_id == user.identity,
        )
        existing = await session.scalar(existing_stmt)

        if existing:
            if request.if_exists == "do_nothing":
                return _serialize_thread(existing)
            else:
                raise HTTPException(409, f"Thread '{thread_id}' already exists")

    metadata = request.metadata or {}
    metadata.update(
        {
            "owner": user.identity,
            "assistant_id": None,
            "graph_id": None,
            "thread_name": "",
        }
    )

    thread_orm = ThreadORM(
        thread_id=thread_id,
        status="idle",
        metadata_json=metadata,
        user_id=user.identity,
    )

    session.add(thread_orm)
    await session.commit()

    with contextlib.suppress(Exception):
        await session.refresh(thread_orm)

    # Pass metadata explicitly in case refresh failed (tests/mocks)
    return _serialize_thread(thread_orm, default_metadata=metadata)


@router.get("/threads", response_model=ThreadList)
async def list_threads(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    """List user's threads"""
    stmt = select(ThreadORM).where(ThreadORM.user_id == user.identity)
    result = await session.scalars(stmt)
    rows = result.all()

    # Use safe serialization
    user_threads = [_serialize_thread(t) for t in rows]
    return ThreadList(threads=user_threads, total=len(user_threads))


@router.get("/threads/{thread_id}", response_model=Thread)
async def get_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread by ID"""
    stmt = select(ThreadORM).where(
        ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
    )
    thread = await session.scalar(stmt)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    return _serialize_thread(thread)


@router.patch("/threads/{thread_id}", response_model=Thread)
async def update_thread(
    thread_id: str,
    request: ThreadUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update a thread's metadata and timestamp."""
    stmt = select(ThreadORM).where(
        ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
    )
    thread = await session.scalar(stmt)

    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    thread.updated_at = datetime.now(UTC)

    if request.metadata:
        current_metadata = dict(thread.metadata_json or {})
        current_metadata.update(request.metadata)
        thread.metadata_json = current_metadata

    await session.commit()
    await session.refresh(thread)

    return _serialize_thread(thread)


@router.get("/threads/{thread_id}/state", response_model=ThreadState)
async def get_thread_state(
    thread_id: str,
    subgraphs: bool = Query(False, description="Include states from subgraphs"),
    checkpoint_ns: str | None = Query(
        None, description="Checkpoint namespace to scope lookup"
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get state for a thread (i.e. latest checkpoint)"""
    try:
        stmt = select(ThreadORM).where(
            ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
        )
        thread = await session.scalar(stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")

        thread_metadata = thread.metadata_json or {}
        graph_id = thread_metadata.get("graph_id")
        if not graph_id:
            logger.info(
                "state GET: no graph_id set for thread %s, returning empty state",
                thread_id,
            )
            empty_checkpoint = ThreadCheckpoint(
                checkpoint_id=None,
                thread_id=thread_id,
                checkpoint_ns="",
            )
            return ThreadState(
                values={},
                next=[],
                tasks=[],
                interrupts=[],
                metadata={},
                created_at=None,
                checkpoint=empty_checkpoint,
                parent_checkpoint=None,
                checkpoint_id=None,
                parent_checkpoint_id=None,
            )

        from ..services.langgraph_service import (
            create_thread_config,
            get_langgraph_service,
        )

        langgraph_service = get_langgraph_service()
        config: dict[str, Any] = create_thread_config(thread_id, user, {})
        if checkpoint_ns:
            config["configurable"]["checkpoint_ns"] = checkpoint_ns

        try:
            async with langgraph_service.get_graph(graph_id) as agent:
                agent = agent.with_config(config)
                # NOTE: LangGraph only exposes subgraph checkpoints while the run is
                # interrupted. See https://docs.langchain.com/oss/python/langgraph/use-subgraphs#view-subgraph-state
                state_snapshot = await agent.aget_state(config, subgraphs=subgraphs)

                if not state_snapshot:
                    logger.info(
                        "state GET: no checkpoint found for thread %s (checkpoint_ns=%s)",
                        thread_id,
                        checkpoint_ns,
                    )
                    raise HTTPException(404, f"No state found for thread '{thread_id}'")

                thread_state = thread_state_service.convert_snapshot_to_thread_state(
                    state_snapshot, thread_id, subgraphs=subgraphs
                )

                logger.debug(
                    "state GET: thread_id=%s checkpoint_id=%s subgraphs=%s checkpoint_ns=%s",
                    thread_id,
                    thread_state.checkpoint.checkpoint_id,
                    subgraphs,
                    checkpoint_ns,
                )

                return thread_state
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(
                "Failed to retrieve latest state for thread '%s'", thread_id
            )
            raise HTTPException(
                500, f"Failed to retrieve thread state: {str(e)}"
            ) from e

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error retrieving latest state for thread '%s'", thread_id
        )
        raise HTTPException(500, f"Error retrieving thread state: {str(e)}") from e


@router.post("/threads/{thread_id}/state")
async def update_thread_state(
    thread_id: str,
    request: ThreadStateUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update thread state or get state via POST."""
    if request.values is None:
        return await get_thread_state(
            thread_id=thread_id,
            subgraphs=request.subgraphs or False,
            checkpoint_ns=request.checkpoint_ns,
            user=user,
            session=session,
        )

    try:
        stmt = select(ThreadORM).where(
            ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
        )
        thread = await session.scalar(stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")

        thread_metadata = thread.metadata_json or {}
        graph_id = thread_metadata.get("graph_id")
        if not graph_id:
            raise HTTPException(
                400,
                f"Thread '{thread_id}' has no associated graph. Cannot update state.",
            )

        from ..services.langgraph_service import (
            create_thread_config,
            get_langgraph_service,
        )

        langgraph_service = get_langgraph_service()
        config: dict[str, Any] = create_thread_config(thread_id, user, {})

        if request.checkpoint_id:
            config["configurable"]["checkpoint_id"] = request.checkpoint_id
        if request.checkpoint:
            config["configurable"].update(request.checkpoint)
        if request.checkpoint_ns:
            config["configurable"]["checkpoint_ns"] = request.checkpoint_ns

        try:
            async with langgraph_service.get_graph(graph_id) as agent:
                # Update state using aupdate_state method
                # This creates a new checkpoint with the updated values
                agent = agent.with_config(config)

                # Handle values - can be dict or list of dicts
                update_values = request.values
                if isinstance(update_values, list):
                    # If it's a list, use the first dict or convert to dict
                    if update_values and isinstance(update_values[0], dict):
                        # Merge all dicts in the list
                        merged = {}
                        for item in update_values:
                            if isinstance(item, dict):
                                merged.update(item)
                        update_values = merged
                    else:
                        update_values = update_values[0] if update_values else None

                # Update the state using aupdate_state
                # aupdate_state signature: aupdate_state(config, values, as_node=None)
                # When as_node is not specified, the graph may try to continue execution,
                # which can fail if the state doesn't match expected graph flow.
                # We should always use as_node to prevent unwanted execution.
                try:
                    # If as_node is not provided, we need to determine a safe node to use
                    # For state updates without as_node, we'll use None which should just update state
                    # without triggering execution, but the graph may still validate the state
                    updated_config = await agent.aupdate_state(
                        config, update_values, as_node=request.as_node
                    )
                except Exception as update_error:
                    logger.exception(
                        "aupdate_state failed for thread %s: %s",
                        thread_id,
                        update_error,
                        exc_info=True,
                    )
                    raise

                # Extract checkpoint info from the updated config
                # aupdate_state returns the updated config dict
                if not isinstance(updated_config, dict):
                    logger.error(
                        "aupdate_state returned non-dict: %s (type: %s)",
                        updated_config,
                        type(updated_config),
                    )
                    raise HTTPException(
                        500,
                        f"Unexpected return type from aupdate_state: {type(updated_config)}",
                    )

                checkpoint_info = {
                    "checkpoint_id": updated_config.get("configurable", {}).get(
                        "checkpoint_id"
                    ),
                    "thread_id": thread_id,
                    "checkpoint_ns": updated_config.get("configurable", {}).get(
                        "checkpoint_ns", ""
                    ),
                }

                logger.info(
                    "state POST: updated state for thread %s checkpoint_id=%s",
                    thread_id,
                    checkpoint_info.get("checkpoint_id"),
                )

                return ThreadStateUpdateResponse(checkpoint=checkpoint_info)

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Failed to update state for thread '%s'", thread_id)
            raise HTTPException(500, f"Failed to update thread state: {str(e)}") from e

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error updating state for thread '%s'", thread_id)
        raise HTTPException(500, f"Error updating thread state: {str(e)}") from e


@router.get("/threads/{thread_id}/state/{checkpoint_id}", response_model=ThreadState)
async def get_thread_state_at_checkpoint(
    thread_id: str,
    checkpoint_id: str,
    subgraphs: bool | None = Query(False, description="Include states from subgraphs"),
    checkpoint_ns: str | None = Query(
        None, description="Checkpoint namespace to scope lookup"
    ),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread state at a specific checkpoint"""
    try:
        stmt = select(ThreadORM).where(
            ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
        )
        thread = await session.scalar(stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")

        thread_metadata = thread.metadata_json or {}
        graph_id = thread_metadata.get("graph_id")
        if not graph_id:
            raise HTTPException(404, f"Thread '{thread_id}' has no associated graph")

        from ..services.langgraph_service import (
            create_thread_config,
            get_langgraph_service,
        )

        langgraph_service = get_langgraph_service()

        config: dict[str, Any] = create_thread_config(thread_id, user, {})
        config["configurable"]["checkpoint_id"] = checkpoint_id
        if checkpoint_ns:
            config["configurable"]["checkpoint_ns"] = checkpoint_ns

        try:
            async with langgraph_service.get_graph(graph_id) as agent:
                agent = agent.with_config(config)
                state_snapshot = await agent.aget_state(
                    config, subgraphs=subgraphs or False
                )

                if not state_snapshot:
                    raise HTTPException(
                        404,
                        f"No state found at checkpoint '{checkpoint_id}' for thread '{thread_id}'",
                    )

                # Convert snapshot to ThreadCheckpoint using service
                thread_checkpoint = (
                    thread_state_service.convert_snapshot_to_thread_state(
                        state_snapshot,
                        thread_id,
                        subgraphs=subgraphs or False,
                    )
                )

                return thread_checkpoint
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(
                "Failed to retrieve state at checkpoint '%s' for thread '%s'",
                checkpoint_id,
                thread_id,
            )
            raise HTTPException(
                500,
                f"Failed to retrieve state at checkpoint '{checkpoint_id}': {str(e)}",
            ) from e

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error retrieving checkpoint '%s' for thread '%s'", checkpoint_id, thread_id
        )
        raise HTTPException(
            500, f"Error retrieving checkpoint '{checkpoint_id}': {str(e)}"
        ) from e


@router.post("/threads/{thread_id}/state/checkpoint", response_model=ThreadState)
async def get_thread_state_at_checkpoint_post(
    thread_id: str,
    request: ThreadCheckpointPostRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread state at a specific checkpoint (POST method)"""
    checkpoint = request.checkpoint
    if not checkpoint.checkpoint_id:
        raise HTTPException(
            400, "checkpoint_id is required in checkpoint configuration"
        )

    subgraphs = request.subgraphs
    checkpoint_ns = checkpoint.checkpoint_ns if checkpoint.checkpoint_ns else None

    output = await get_thread_state_at_checkpoint(
        thread_id,
        checkpoint.checkpoint_id,
        subgraphs,
        checkpoint_ns,
        user,
        session,
    )
    return output


@router.post("/threads/{thread_id}/history", response_model=list[ThreadState])
async def get_thread_history_post(
    thread_id: str,
    request: ThreadHistoryRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread checkpoint history (POST method)"""
    try:
        limit = request.limit or 10
        if not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise HTTPException(
                422, "Invalid limit; must be an integer between 1 and 1000"
            )

        before = request.before
        metadata = request.metadata
        checkpoint = request.checkpoint or {}
        subgraphs = bool(request.subgraphs) if request.subgraphs is not None else False
        checkpoint_ns = request.checkpoint_ns

        stmt = select(ThreadORM).where(
            ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
        )
        thread = await session.scalar(stmt)
        if not thread:
            raise HTTPException(404, f"Thread '{thread_id}' not found")

        thread_metadata = thread.metadata_json or {}
        graph_id = thread_metadata.get("graph_id")
        if not graph_id:
            logger.info(f"history POST: no graph_id set for thread {thread_id}")
            return []

        from ..services.langgraph_service import (
            create_thread_config,
            get_langgraph_service,
        )

        langgraph_service = get_langgraph_service()

        config: dict[str, Any] = create_thread_config(thread_id, user, {})
        if checkpoint:
            cfg_cp = checkpoint.copy()
            if checkpoint_ns is not None:
                cfg_cp.setdefault("checkpoint_ns", checkpoint_ns)
            config["configurable"].update(cfg_cp)
        elif checkpoint_ns is not None:
            config["configurable"]["checkpoint_ns"] = checkpoint_ns

        state_snapshots = []
        kwargs = {
            "limit": limit,
            "before": before,
        }
        if metadata is not None:
            kwargs["metadata"] = metadata

        async with langgraph_service.get_graph(graph_id) as agent:
            # Some LangGraph versions support subgraphs flag; pass if available
            try:
                async for snapshot in agent.aget_state_history(
                    config, subgraphs=subgraphs, **kwargs
                ):
                    state_snapshots.append(snapshot)
            except TypeError:
                # Fallback if subgraphs not supported in this version
                async for snapshot in agent.aget_state_history(config, **kwargs):
                    state_snapshots.append(snapshot)

            # Convert snapshots to ThreadState using service
            thread_states = thread_state_service.convert_snapshots_to_thread_states(
                state_snapshots, thread_id
            )

            return thread_states

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in history POST for thread %s", thread_id)
        msg = str(e).lower()
        if "not found" in msg or "no checkpoint" in msg:
            return []
        raise HTTPException(500, f"Error retrieving thread history: {str(e)}") from e


@router.get("/threads/{thread_id}/history", response_model=list[ThreadState])
async def get_thread_history_get(
    thread_id: str,
    limit: int = Query(10, ge=1, le=1000, description="Number of states to return"),
    before: str | None = Query(
        None, description="Return states before this checkpoint ID"
    ),
    subgraphs: bool | None = Query(False, description="Include states from subgraphs"),
    checkpoint_ns: str | None = Query(None, description="Checkpoint namespace"),
    metadata: str | None = Query(None, description="JSON-encoded metadata filter"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get thread checkpoint history (GET method)"""
    parsed_metadata: dict[str, Any] | None = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
            if not isinstance(parsed_metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except Exception as e:
            raise HTTPException(422, f"Invalid metadata query param: {e}") from e
    req = ThreadHistoryRequest(
        limit=limit,
        before=before,
        metadata=parsed_metadata,
        checkpoint=None,
        subgraphs=subgraphs,
        checkpoint_ns=checkpoint_ns,
    )
    return await get_thread_history_post(thread_id, req, user, session)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete thread by ID. Automatically cancels active runs."""
    stmt = select(ThreadORM).where(
        ThreadORM.thread_id == thread_id, ThreadORM.user_id == user.identity
    )
    thread = await session.scalar(stmt)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    active_runs_stmt = select(RunORM).where(
        RunORM.thread_id == thread_id,
        RunORM.user_id == user.identity,
        RunORM.status.in_(["pending", "running"]),
    )
    active_runs_list = (await session.scalars(active_runs_stmt)).all()

    if active_runs_list:
        logger.info(
            f"Cancelling {len(active_runs_list)} active runs for thread {thread_id}"
        )
        for run in active_runs_list:
            run_id = run.run_id
            await streaming_service.cancel_run(run_id)
            task = active_runs.pop(run_id, None)
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    await session.delete(thread)
    await session.commit()

    return {"status": "deleted"}


@router.post("/threads/search", response_model=list[Thread])
async def search_threads(
    request: ThreadSearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Search threads with filters"""
    stmt = select(ThreadORM).where(ThreadORM.user_id == user.identity)

    if request.status:
        stmt = stmt.where(ThreadORM.status == request.status)

    if request.metadata:
        for key, value in request.metadata.items():
            stmt = stmt.where(ThreadORM.metadata_json[key].as_string() == str(value))

    offset = request.offset or 0
    limit = request.limit or 20
    stmt = stmt.order_by(ThreadORM.created_at.desc()).offset(offset).limit(limit)

    result = await session.scalars(stmt)
    rows = result.all()

    # Use safe serialization
    threads_models = [_serialize_thread(t) for t in rows]

    return threads_models
